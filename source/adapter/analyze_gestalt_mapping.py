from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path


CONTROL_RE = re.compile(
    r"%(?:TS\d{3}|TE|FS|FE|LC|LL|LR|T\d+|X\d{3}|C[0-9A-Fa-f]{4}|K|P|N|p|O|V|s|n|S|d|W)"
)
JP_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
SCENE_RE = re.compile(r"^(?:PR|CO\d|COEP|SA\d|SAEP)_\d+$")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_translations(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted((root / "translations" / "script-pool").glob("packet-*.json")):
        if path.name.endswith(".ok.json"):
            continue
        for row in json.loads(path.read_text(encoding="utf-8"))["translations"]:
            out[row["key"]] = row["target_ko"]
    return out


def normalize_en(text: str) -> str:
    text = unicodedata.normalize("NFKC", CONTROL_RE.sub("", text))
    if "\u300c" in text:
        text = text.split("\u300c", 1)[1].replace("\u300d", "")
    text = text.casefold()
    return "".join(ch for ch in text if ch.isalnum())


def normalize_jp(text: str) -> str:
    text = unicodedata.normalize("NFKC", CONTROL_RE.sub("", text))
    return "".join(ch for ch in text if ch.isalnum() or JP_RE.match(ch))


def parse_chapter(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text)
    rows: list[dict] = []
    for block_no, block in enumerate(blocks):
        lines = block.splitlines()
        if len(lines) < 2 or not JP_RE.search(lines[0]):
            continue
        rows.append(
            {
                "block": block_no,
                "jp": lines[0],
                "en": lines[1],
                "jp_norm": normalize_jp(lines[0]),
                "en_norm": normalize_en(lines[1]),
            }
        )
    return rows


def exact_sequence_map(left: list[str], right: list[str]) -> dict[int, int]:
    left_pairs = [(i, value) for i, value in enumerate(left) if value]
    right_pairs = [(i, value) for i, value in enumerate(right) if value]
    matcher = difflib.SequenceMatcher(
        None,
        [value for _, value in left_pairs],
        [value for _, value in right_pairs],
        autojunk=False,
    )
    out: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for delta in range(block.size):
            out[left_pairs[block.a + delta][0]] = right_pairs[block.b + delta][0]
    return out


def load_scene_names(root: Path, parse_script) -> list[str]:
    path = next((root / "extracted" / "mac-jp" / "decoded").glob("0169__*"))
    obj = parse_script(path.read_bytes())
    names = []
    for item in obj["items"]:
        value = unicodedata.normalize("NFKC", item["text"])
        if SCENE_RE.fullmatch(value):
            names.append(value)
    # The PC scene selector exposes CO2_09 as one item, while the PSP/Gestalt
    # script stores its two consecutive physical chapters separately.
    split_index = names.index("CO2_09")
    names[split_index : split_index + 1] = ["CO2_09A", "CO2_09B"]
    if len(names) != 155 or names[0] != "PR_01" or names[-1] != "SAEP_06":
        raise ValueError(f"unexpected scene list: {len(names)} {names[:1]} {names[-1:]}")
    return names


def raw_strings(decoded: bytes, find_pointer_table) -> list[bytes]:
    info = find_pointer_table(decoded)
    if not info:
        raise ValueError("no script pointer table")
    pos = info["text_offset"]
    end = len(decoded)
    out: list[bytes] = []
    while pos < end:
        zero = decoded.find(b"\0", pos, end)
        if zero < 0:
            raise ValueError("unterminated Gestalt text pool")
        out.append(decoded[pos:zero])
        pos = zero + 1
    if pos != end:
        raise ValueError("Gestalt text pool end mismatch")
    return out


def make_tolerant_decoder(bytes_to_codes: dict):
    def decode(raw: bytes) -> tuple[str, int]:
        chars: list[str] = []
        unknown = 0
        pos = 0
        while pos < len(raw):
            byte = raw[pos]
            if 0x20 <= byte <= 0x7E or byte in (9, 10):
                chars.append(chr(byte))
                pos += 1
                continue
            one = raw[pos : pos + 1]
            if one in bytes_to_codes:
                chars.append(bytes_to_codes[one][2])
                pos += 1
                continue
            two = raw[pos : pos + 2]
            if len(two) == 2 and two in bytes_to_codes:
                chars.append(bytes_to_codes[two][2])
                pos += 2
                continue
            chars.append("\ufffd")
            unknown += 1
            pos += 2 if byte >= 0x80 and pos + 1 < len(raw) else 1
        return "".join(chars), unknown

    return decode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "adapter"))
    from r11_script_pool import find_pointer_table, parse as parse_script
    from r11_tools import AfsArchive, decode_wrapped

    psp = root / "gestalt-analysis" / "sources" / "Infinity-PSP-TL"
    sys.path.insert(0, str(psp / "py-src"))
    import r11

    _, _, bytes_to_codes = r11._init_r11_charset("en")
    decode_en = make_tolerant_decoder(bytes_to_codes)
    scenes = load_scene_names(root, parse_script)
    chapters = {scene: parse_chapter(psp / "text" / "chapters-psp-r11" / f"{scene}.txt") for scene in scenes}

    catalog = read_jsonl(root / "catalog" / "script-pool-ja.jsonl")
    translations = load_translations(root)
    base_by_entry: dict[int, list[dict]] = collections.defaultdict(list)
    for row in catalog:
        if row["entry"] <= 154:
            base_by_entry[row["entry"]].append(row)

    gestalt_path = (
        root
        / "gestalt-analysis"
        / "extracted"
        / "R11-Gestalt-v1.3.0"
        / "v1.3.0"
        / "FILE"
        / "mac-en.afs"
    )
    arc = AfsArchive(gestalt_path)
    summary = collections.Counter()
    scene_reports: list[dict] = []
    samples: list[dict] = []

    for entry, scene in enumerate(scenes):
        decoded = decode_wrapped(arc.raw(entry))
        raws = raw_strings(decoded, find_pointer_table)
        strings = []
        unknown = 0
        for raw in raws:
            text, count = decode_en(raw)
            unknown += count
            strings.append(text)

        psp_rows = chapters[scene]
        g_to_psp = exact_sequence_map([normalize_en(text) for text in strings], [row["en_norm"] for row in psp_rows])

        base_rows = base_by_entry[entry]
        psp_to_base = exact_sequence_map(
            [row["jp_norm"] for row in psp_rows],
            [normalize_jp(row["source_jp"]) for row in base_rows],
        )

        reused = 0
        psp_only = 0
        for g_index, psp_index in g_to_psp.items():
            base_index = psp_to_base.get(psp_index)
            if base_index is None:
                psp_only += 1
                if len(samples) < 100:
                    samples.append(
                        {
                            "entry": entry,
                            "scene": scene,
                            "gestalt_index": g_index,
                            "psp_block": psp_rows[psp_index]["block"],
                            "jp": psp_rows[psp_index]["jp"],
                            "en": psp_rows[psp_index]["en"],
                        }
                    )
            else:
                key = base_rows[base_index]["key"]
                if key in translations:
                    reused += 1

        summary["gestalt_strings"] += len(strings)
        summary["psp_rows"] += len(psp_rows)
        summary["gestalt_to_psp_exact"] += len(g_to_psp)
        summary["psp_to_base_exact"] += len(psp_to_base)
        summary["gestalt_reused_korean"] += reused
        summary["gestalt_psp_only"] += psp_only
        summary["decode_unknown_units"] += unknown
        scene_reports.append(
            {
                "entry": entry,
                "scene": scene,
                "gestalt_strings": len(strings),
                "psp_rows": len(psp_rows),
                "gestalt_to_psp_exact": len(g_to_psp),
                "psp_to_base_exact": len(psp_to_base),
                "reused_korean": reused,
                "psp_only": psp_only,
                "decode_unknown_units": unknown,
            }
        )

    report = {
        "schema": "remember11.gestalt-mapping-analysis.v1",
        "scene_count": len(scenes),
        "first_scene": scenes[0],
        "last_scene": scenes[-1],
        "summary": dict(summary),
        "scenes": scene_reports,
        "psp_only_samples": samples,
    }
    out = root / "gestalt-analysis" / "mapping-analysis.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=True, indent=2))
    print(out)


if __name__ == "__main__":
    main()
