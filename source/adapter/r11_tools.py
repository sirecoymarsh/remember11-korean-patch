#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ALIGN = 0x800


def align_up(n: int, a: int = ALIGN) -> int:
    return (n + a - 1) & ~(a - 1)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lzss_decompress(src: bytes) -> bytes:
    # Okumura LZSS used by Remember11 (N=4096, F=18, threshold=2).
    ring = bytearray(4096 + 18 - 1)
    r = 4096 - 18
    out = bytearray()
    flags = 0
    p = 0
    while True:
        flags >>= 1
        if (flags & 0x100) == 0:
            if p >= len(src):
                break
            flags = src[p] | 0xFF00
            p += 1
        if flags & 1:
            if p >= len(src):
                break
            c = src[p]
            p += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & 4095
        else:
            if p + 1 >= len(src):
                break
            i, j = src[p], src[p + 1]
            p += 2
            i |= (j & 0xF0) << 4
            length = (j & 0x0F) + 3
            for k in range(length):
                c = ring[(i + k) & 4095]
                out.append(c)
                ring[r] = c
                r = (r + 1) & 4095
    return bytes(out)


def lzss_store(src: bytes) -> bytes:
    # Deterministic valid LZSS stream containing literals only. Changed payloads
    # are intentionally recreated instead of being painted over or edited in place.
    out = bytearray()
    for p in range(0, len(src), 8):
        chunk = src[p:p + 8]
        out.append((1 << len(chunk)) - 1)
        out.extend(chunk)
    return bytes(out)


def decode_wrapped(raw: bytes) -> bytes:
    if len(raw) < 4:
        raise ValueError('wrapped payload too small')
    expected = struct.unpack_from('<I', raw, 0)[0]
    decoded = lzss_decompress(raw[4:])
    if len(decoded) != expected:
        raise ValueError(f'LZSS size mismatch: expected={expected}, actual={len(decoded)}')
    return decoded


def encode_wrapped(decoded: bytes) -> bytes:
    return struct.pack('<I', len(decoded)) + lzss_store(decoded)


@dataclass(frozen=True)
class AfsEntry:
    index: int
    offset: int
    size: int
    name: str


class AfsArchive:
    def __init__(self, path: Path, names_from: Path | None = None):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if self.data[:4] != b'AFS\0':
            raise ValueError(f'not AFS: {self.path}')
        self.count = struct.unpack_from('<I', self.data, 4)[0]
        pairs = [struct.unpack_from('<II', self.data, 8 + i * 8) for i in range(self.count)]
        self.index_offset, self.index_size = struct.unpack_from('<II', self.data, 8 + self.count * 8)
        names = self._read_names(self.data, self.count, self.index_offset, self.index_size)
        if not names and names_from:
            donor = AfsArchive(Path(names_from))
            if donor.count == self.count:
                names = [e.name for e in donor.entries]
        if not names:
            names = [f'{i:04d}.bin' for i in range(self.count)]
        self.entries = [AfsEntry(i, off, size, names[i]) for i, (off, size) in enumerate(pairs)]

    @staticmethod
    def _read_names(data: bytes, count: int, off: int, size: int) -> list[str]:
        if off <= 0 or size < count * 48 or off + size > len(data):
            return []
        names = []
        for i in range(count):
            raw = data[off + i * 48:off + i * 48 + 32].split(b'\0', 1)[0]
            names.append(raw.decode('cp932', 'replace') or f'{i:04d}.bin')
        return names

    def raw(self, index: int) -> bytes:
        e = self.entries[index]
        return self.data[e.offset:e.offset + e.size]

    def extract(self, out_dir: Path, decode_lzss: bool = False) -> dict:
        out_dir = Path(out_dir)
        raw_dir = out_dir / 'raw'
        dec_dir = out_dir / 'decoded'
        raw_dir.mkdir(parents=True, exist_ok=True)
        if decode_lzss:
            dec_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for e in self.entries:
            safe = re.sub(r'[^0-9A-Za-z._-]+', '_', e.name)
            rel = f'{e.index:04d}__{safe}'
            raw = self.raw(e.index)
            (raw_dir / rel).write_bytes(raw)
            decoded_ok = False
            decoded_sha = None
            decoded_size = None
            if decode_lzss:
                try:
                    decoded = decode_wrapped(raw)
                    (dec_dir / rel).write_bytes(decoded)
                    decoded_ok = True
                    decoded_sha = sha256(decoded)
                    decoded_size = len(decoded)
                except Exception:
                    pass
            items.append({
                'index': e.index, 'name': e.name, 'offset': e.offset, 'raw_size': len(raw),
                'raw_sha256': sha256(raw), 'decoded': decoded_ok,
                'decoded_size': decoded_size, 'decoded_sha256': decoded_sha,
            })
        manifest = {
            'archive': str(self.path), 'archive_sha256': sha256(self.data),
            'count': self.count, 'first_data_offset': self.entries[0].offset if self.entries else 0,
            'index_offset': self.index_offset, 'index_size': self.index_size, 'entries': items,
        }
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return manifest

    def rebuild(self, output: Path, replacements: dict[int, bytes] | None = None,
                preserve_index: bool = True) -> dict:
        replacements = replacements or {}
        payloads = [replacements.get(i, self.raw(i)) for i in range(self.count)]
        first = self.entries[0].offset if self.entries else align_up(16 + self.count * 8)
        min_first = align_up(16 + self.count * 8)
        first = max(first, min_first)
        offsets = []
        cursor = first
        for payload in payloads:
            cursor = align_up(cursor)
            offsets.append(cursor)
            cursor += len(payload)
        index_blob = b''
        index_offset = 0
        index_size = 0
        if preserve_index and self.index_offset and self.index_size:
            index_blob = self.data[self.index_offset:self.index_offset + self.index_size]
            index_offset = align_up(cursor)
            index_size = len(index_blob)
            cursor = index_offset + index_size
        final_size = align_up(cursor)
        out = bytearray(final_size)
        out[:4] = b'AFS\0'
        struct.pack_into('<I', out, 4, self.count)
        for i, payload in enumerate(payloads):
            struct.pack_into('<II', out, 8 + i * 8, offsets[i], len(payload))
            out[offsets[i]:offsets[i] + len(payload)] = payload
        struct.pack_into('<II', out, 8 + self.count * 8, index_offset, index_size)
        if index_blob:
            out[index_offset:index_offset + len(index_blob)] = index_blob
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(out)
        return {
            'output': str(output), 'sha256': sha256(out), 'size': len(out),
            'changed_entries': sorted(replacements), 'count': self.count,
        }


def cmd_extract(args):
    arc = AfsArchive(Path(args.archive), Path(args.names_from) if args.names_from else None)
    print(json.dumps(arc.extract(Path(args.output), args.decode_lzss), ensure_ascii=False, indent=2))


def cmd_roundtrip(args):
    arc = AfsArchive(Path(args.archive), Path(args.names_from) if args.names_from else None)
    result = arc.rebuild(Path(args.output))
    rebuilt = AfsArchive(Path(args.output), Path(args.names_from) if args.names_from else None)
    logical = all(arc.raw(i) == rebuilt.raw(i) for i in range(arc.count))
    result.update({'logical_payloads_identical': logical, 'byte_identical': arc.data == rebuilt.data})
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    ex = sp.add_parser('extract')
    ex.add_argument('archive'); ex.add_argument('output'); ex.add_argument('--names-from'); ex.add_argument('--decode-lzss', action='store_true'); ex.set_defaults(func=cmd_extract)
    rt = sp.add_parser('roundtrip')
    rt.add_argument('archive'); rt.add_argument('output'); rt.add_argument('--names-from'); rt.set_defaults(func=cmd_roundtrip)
    args = ap.parse_args(); args.func(args)

if __name__ == '__main__':
    main()
