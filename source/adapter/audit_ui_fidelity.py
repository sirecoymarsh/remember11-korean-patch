from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from build_ui import KEEP_LABELS, full_type2, load_etc_jobs, load_image_translations
from r11_images import parse


def normalize_blocks(blocks: list[dict], width: int, height: int) -> list[dict]:
    result = []
    for block in blocks:
        x0, y0, x1, y1 = map(int, block["bbox"])
        result.append({
            **block,
            "bbox": [
                max(0, min(width, x0)),
                max(0, min(height, y0)),
                max(0, min(width, x1)),
                max(0, min(height, y1)),
            ],
        })
    return result


def compare_asset(label: str, source: Image.Image, output: Image.Image, blocks: list[dict]) -> dict:
    source = source.convert("RGBA")
    output = output.convert("RGBA")
    assert output.size == source.size, (label, source.size, output.size)
    a = np.asarray(source)
    b = np.asarray(output)
    changed = np.any(a != b, axis=2)
    allowed = np.zeros(changed.shape, dtype=bool)
    translated_blocks = 0
    unchanged_blocks = 0
    block_rows = []
    for block in normalize_blocks(blocks, source.width, source.height):
        x0, y0, x1, y1 = block["bbox"]
        skip = block["source_jp"] in KEEP_LABELS or block["target_ko"] == block["source_jp"]
        if skip:
            unchanged_blocks += 1
            block_rows.append({"bbox": block["bbox"], "status": "preserved", "changed_pixels": 0})
            continue
        assert x1 > x0 and y1 > y0, (label, block)
        translated_blocks += 1
        allowed[y0:y1, x0:x1] = True
        count = int(changed[y0:y1, x0:x1].sum())
        assert count > 0, (label, block)
        block_rows.append({"bbox": block["bbox"], "status": "recreated", "changed_pixels": count})
    outside = int((changed & ~allowed).sum())
    assert outside == 0, (label, outside)
    return {
        "asset": label,
        "canvas": list(source.size),
        "translated_blocks": translated_blocks,
        "preserved_blocks": unchanged_blocks,
        "changed_pixels": int(changed.sum()),
        "changed_pixels_outside_annotated_boxes": outside,
        "blocks": block_rows,
    }


def audit(root: Path) -> dict:
    rendered = root / "ui" / "rendered"
    rows = []

    for src, asset in load_etc_jobs(root):
        source = Image.open(src)
        rel = src.relative_to(root / "ui" / "etc-jp")
        output = Image.open(rendered / "etc-components" / rel)
        rows.append(compare_asset(f"etc:{rel}", source, output, asset["blocks"]))

    translations = load_image_translations(root)
    for filename, asset in sorted(translations.items()):
        if not asset["blocks"]:
            continue
        kind, index_text, _ = filename.split("-", 2)
        index = int(index_text)
        raw = next((root / "extracted" / f"{kind}-jp" / "raw").glob(f"{index:04d}__*"))
        source, _ = full_type2(parse(raw.read_bytes()))
        output = Image.open(rendered / "image-canvases" / filename.replace("-jp.png", "-ko.png"))
        rows.append(compare_asset(f"{kind}:{index:04d}", source, output, asset["blocks"]))

    result = {
        "schema": "remember11.ko-ui-fidelity-qa.v1",
        "ok": True,
        "rule": "Source glyphs are removed and Korean is recreated only inside the original annotated bounding boxes; canvas dimensions and all pixels outside those boxes are preserved.",
        "assets": len(rows),
        "translated_blocks": sum(x["translated_blocks"] for x in rows),
        "preserved_blocks": sum(x["preserved_blocks"] for x in rows),
        "changed_pixels_outside_annotated_boxes": sum(x["changed_pixels_outside_annotated_boxes"] for x in rows),
        "rows": rows,
    }
    out = root / "audit" / "ui-fidelity-qa.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "ok", "assets", "translated_blocks", "preserved_blocks",
        "changed_pixels_outside_annotated_boxes"
    )}, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    audit(args.root)


if __name__ == "__main__":
    main()
