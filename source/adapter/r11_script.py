"""Remember11 PC scenario text catalog and reinsertion helpers.

The PC scripts are bytecode blobs with CP932 NUL-terminated strings.  A normal
message ends in ``%K%P``.  No pointer table has been observed in the PC data;
replacement is therefore performed from the last span to the first so that the
opaque bytecode and trailer are preserved byte-for-byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


MESSAGE_END = b"%K%P\x00"
CONTROL_RE = re.compile(r"%(?:TS\d{3}|T\d+|X\d{3}|C[0-9A-Fa-f]+|LC|FS|FE|TE|N|K|P)")


def _valid_text(text: str) -> bool:
    if not text or not text.endswith("%K%P"):
        return False
    for ch in text:
        n = ord(ch)
        if n < 0x20 and ch not in "\t\r\n":
            return False
        if 0x7F <= n < 0xA0:
            return False
    return True


def find_message_spans(data: bytes) -> list[dict]:
    """Return the CP932 message spans without interpreting surrounding code."""
    result: list[dict] = []
    search_from = 0
    while True:
        marker = data.find(MESSAGE_END, search_from)
        if marker < 0:
            break
        end = marker + len(MESSAGE_END) - 1  # exclude the terminating NUL
        base = data.rfind(b"\x00", 0, marker) + 1
        chosen = None
        # Script text pools start on an 8-byte boundary.  The first message can
        # directly follow a few non-NUL bytecode bytes, so prefer that boundary.
        if not result:
            aligned = (base + 7) & ~7
            if aligned <= marker:
                try:
                    aligned_text = data[aligned:end].decode("cp932", errors="strict")
                except UnicodeDecodeError:
                    aligned_text = ""
                if _valid_text(aligned_text):
                    chosen = (aligned, aligned_text)
        # Otherwise prefer the earliest printable strict-CP932 suffix.
        for start in range(base, min(marker + 1, base + 128)):
            if chosen is not None:
                break
            try:
                text = data[start:end].decode("cp932", errors="strict")
            except UnicodeDecodeError:
                continue
            if _valid_text(text):
                chosen = (start, text)
                break
        if chosen is None:
            raise ValueError(f"cannot isolate CP932 message ending at 0x{marker:X}")
        start, text = chosen
        result.append({"start": start, "end": end, "text": text})
        search_from = marker + len(MESSAGE_END)
    return result


def split_speaker(text: str) -> tuple[str, str]:
    visible = CONTROL_RE.sub("", text.removesuffix("%K%P"))
    for quote in ("「", "『"):
        pos = visible.find(quote)
        if 0 < pos <= 16:
            return visible[:pos], visible[pos:]
    return "", visible


def control_signature(text: str) -> list[str]:
    return CONTROL_RE.findall(text)


def catalog_file(path: Path, entry_index: int) -> list[dict]:
    data = path.read_bytes()
    spans = find_message_spans(data)
    rows = []
    for i, span in enumerate(spans):
        source = span["text"]
        speaker, visible = split_speaker(source)
        rows.append({
            "key": f"mac.afs::{entry_index:04d}::{i:04d}",
            "entry": entry_index,
            "message_index": i,
            "offset": span["start"],
            "end": span["end"],
            "source_jp": source,
            "speaker_jp": speaker,
            "visible_jp": visible,
            "controls": control_signature(source),
            "source_sha1": hashlib.sha1(source.encode("cp932")).hexdigest(),
        })
    for i, row in enumerate(rows):
        row["previous_jp"] = rows[i - 1]["source_jp"] if i else ""
        row["next_jp"] = rows[i + 1]["source_jp"] if i + 1 < len(rows) else ""
    return rows


def build_catalog(decoded_dir: Path, out_jsonl: Path, stats_path: Path | None = None) -> dict:
    rows: list[dict] = []
    for path in sorted(decoded_dir.glob("*.bin")):
        entry = int(path.name.split("__", 1)[0])
        rows.extend(catalog_file(path, entry))
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter(row["source_jp"] for row in rows)
    stats = {
        "messages": len(rows),
        "unique_exact_messages": len(counts),
        "entries_with_messages": len({row["entry"] for row in rows}),
        "duplicate_message_instances": sum(n - 1 for n in counts.values()),
    }
    if stats_path:
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def apply_translations(data: bytes, rows: Iterable[dict], translations: dict[str, str],
                       encode_text) -> bytes:
    replacements = []
    for row in rows:
        key = row["key"]
        if key not in translations:
            raise KeyError(f"missing translation: {key}")
        target = translations[key]
        if control_signature(target) != row["controls"]:
            raise ValueError(f"control mismatch: {key}")
        replacements.append((row["offset"], row["end"], encode_text(target), key))
    out = bytearray(data)
    for start, end, payload, _ in sorted(replacements, reverse=True):
        out[start:end] = payload
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    cat = sub.add_parser("catalog")
    cat.add_argument("decoded_dir", type=Path)
    cat.add_argument("out_jsonl", type=Path)
    cat.add_argument("--stats", type=Path)
    args = ap.parse_args()
    if args.cmd == "catalog":
        print(json.dumps(build_catalog(args.decoded_dir, args.out_jsonl, args.stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
