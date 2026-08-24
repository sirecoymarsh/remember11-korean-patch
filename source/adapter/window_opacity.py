#!/usr/bin/env python3
"""Make the dialogue window less transparent by raising bg_filt2's alpha.

The message window is a black plate with a white veil (`bg_filt2.tm2`, a 32x32
solid-white tile whose alpha runs 2..93 out of the engine's opaque value 128)
composited over the scene, so the box brightness swings with whatever is behind
it and text contrast swings with it. Raising that alpha pins the box.

GAME.BIP's last record is not a PNGFILE3 image, so the project's generic image
rebuilder cannot round-trip this container. Instead the replacement PNG is
padded with a tEXt chunk to the exact byte length of the original, which leaves
every offset, length field and trailing blob untouched.
"""
from __future__ import annotations
import argparse, io, struct, sys, zlib
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from r11_tools import AfsArchive, decode_wrapped, encode_wrapped

ROOT = Path(__file__).resolve().parents[1]
ETC_ENTRY = 15          # GAME.BIP
TILE = 'bg_filt2.tm2'
OPAQUE = 128            # engine's fully-opaque alpha


def align(n, a=16):
    return (n + a - 1) & ~(a - 1)


def locate(data: bytes, want: str):
    count = struct.unpack_from('<I', data, 0)[0]
    base = align((count + 1) * 4)
    for i in range(count):
        off = struct.unpack_from('<I', data, 4 + i * 4)[0]
        pos = base + off * 16
        if data[pos:pos + 4] != b'TIM2' or data[pos + 64:pos + 72] != b'PNGFILE3':
            continue
        name = data[pos + 92:pos + 156].split(b'\0', 1)[0].decode('cp932', 'replace')
        if name == want:
            part = struct.unpack_from('<I', data, pos + 88)[0]
            return i, pos + 188, part - 124
    raise ValueError(f'{want} not found')


def pad_png(png: bytes, target: int) -> bytes:
    """Pad a PNG to an exact byte length using a tEXt chunk before IEND."""
    end = png.rfind(b'IEND') - 4
    if end < 0:
        raise ValueError('malformed PNG')
    head, tail = png[:end], png[end:]
    need = target - len(png)
    if need < 0:
        raise ValueError(f'replacement is {-need} bytes too large to pad')
    if need == 0:
        return png
    if need < 12:
        raise ValueError(f'cannot pad by {need} bytes (chunk overhead is 12)')
    payload = b'pad\0' + b'.' * (need - 12 - 4)
    chunk = struct.pack('>I', len(payload)) + b'tEXt' + payload
    chunk += struct.pack('>I', zlib.crc32(b'tEXt' + payload) & 0xFFFFFFFF)
    out = head + chunk + tail
    if len(out) != target:
        raise ValueError(f'padding landed at {len(out)}, wanted {target}')
    return out


def build(alpha: int, src_afs: Path, out_afs: Path, tile: str = TILE) -> dict:
    arc = AfsArchive(src_afs)
    game = bytearray(decode_wrapped(arc.raw(ETC_ENTRY)))
    idx, png_off, png_len = locate(bytes(game), tile)
    old = bytes(game[png_off:png_off + png_len])

    im = Image.open(io.BytesIO(old)).convert('RGBA')
    px = im.load()
    before = []
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            before.append(a)
            px[x, y] = (r, g, b, alpha)
    buf = io.BytesIO()
    im.save(buf, format='PNG', optimize=True)
    new = pad_png(buf.getvalue(), png_len)

    game[png_off:png_off + png_len] = new
    res = arc.rebuild(out_afs, replacements={ETC_ENTRY: encode_wrapped(bytes(game))})

    # prove the container still parses and the tile really changed
    check = decode_wrapped(AfsArchive(out_afs).raw(ETC_ENTRY))
    i2, o2, l2 = locate(check, tile)
    got = Image.open(io.BytesIO(check[o2:o2 + l2])).convert('RGBA')
    seen = {p[3] for p in got.get_flattened_data()}
    if seen != {alpha}:
        raise ValueError(f'alpha did not take: {sorted(seen)[:6]}')
    if len(check) != len(bytes(game)):
        raise ValueError('container length drift')
    return {'tile_index': idx, 'png_bytes': png_len, 'alpha': alpha,
            'alpha_before': f'{min(before)}..{max(before)} (mean {sum(before)/len(before):.0f})',
            'out': str(out_afs), 'sha256': res['sha256'][:16]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--alphas', default='96,112,128')
    ap.add_argument('--tile', default=TILE, help='which GAME.BIP tile to re-alpha')
    ap.add_argument('--src', type=Path,
                    default=ROOT / 'release/Remember11-Korean-Gestalt/FILE/etc-en.afs')
    ap.add_argument('--out', type=Path, default=ROOT / 'runtime-test' / 'window-variants')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    tag = a.tile.split('.')[0]
    for al in (int(x) for x in a.alphas.split(',')):
        info = build(al, a.src, a.out / f'etc-en-{tag}{al}.afs', a.tile)
        print(f"{a.tile} alpha {al:3} (was {info['alpha_before']}) -> {Path(info['out']).name}  "
              f"png={info['png_bytes']}B  sha={info['sha256']}", flush=True)


if __name__ == '__main__':
    main()
