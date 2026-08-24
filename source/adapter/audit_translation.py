from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

CONTROL_RE = re.compile(
    r"%(?:TS\d{3}|TE|FS|FE|LC|LL|LR|T\d+|X[0-9A-Fa-f]{3}|"
    r"C[0-9A-Fa-f]{4}|K|P|N|p|O|V)"
)
JP_VISIBLE_RE = re.compile(r"[\u3040-\u30FA\u30FC-\u30FF\u3400-\u9FFF]")
KANA_RE = re.compile(r"[\u3040-\u30FA\u30FC-\u30FF]")
QUESTION_RUN_RE = re.compile(r"[?\uff1f]{2,}")


def load_catalog(root: Path) -> dict[str, dict]:
    path = root / "catalog" / "script-pool-ja.jsonl"
    return {row["key"]: row for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def load_translations(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((root / "translations" / "script-pool").glob("packet-*.json")):
        if path.name.endswith(".ok.json"):
            continue
        for row in json.loads(path.read_text(encoding="utf-8"))["translations"]:
            key = row["key"]
            if key in result:
                raise ValueError(f"duplicate translation key: {key}")
            result[key] = row["target_ko"]
    manual = root / "translations" / "manual-overrides.json"
    if manual.exists():
        for row in json.loads(manual.read_text(encoding="utf-8"))["translations"]:
            key = row["key"]
            if key in result:
                raise ValueError(f"manual override collides with packet translation: {key}")
            result[key] = row["target_ko"]
    return result


def normalized_question_runs(text: str) -> list[int]:
    return [len(m.group(0)) for m in QUESTION_RUN_RE.finditer(text.replace("\uff1f", "?"))]


def audit(root: Path) -> dict:
    catalog = load_catalog(root)
    translations = load_translations(root)
    translated_keys = set(translations)
    catalog_keys = set(catalog)
    missing = sorted(catalog_keys - translated_keys)
    extra = sorted(translated_keys - catalog_keys)
    missing_visible = [
        {"key": key, "source_jp": catalog[key]["source_jp"]}
        for key in missing
        if JP_VISIBLE_RE.search(catalog[key]["source_jp"])
    ]

    issues: list[dict] = []
    info = Counter()
    inherited_question_rows: list[dict] = []

    for key in sorted(translations):
        source = catalog[key]["source_jp"]
        target = translations[key]
        flags: list[str] = []

        source_controls = CONTROL_RE.findall(source)
        target_controls = CONTROL_RE.findall(target)
        if source_controls != target_controls:
            flags.append("control_sequence_mismatch")

        source_without_controls = CONTROL_RE.sub("", source)
        target_without_controls = CONTROL_RE.sub("", target)
        unknown_source_percent = "%" in source_without_controls
        unknown_target_percent = "%" in target_without_controls
        if unknown_target_percent and "\uff05" not in source and not unknown_source_percent:
            flags.append("unexpected_literal_percent")

        if not target:
            flags.append("empty_target")
        if "\ufffd" in target:
            flags.append("replacement_character")
        if KANA_RE.search(target):
            flags.append("japanese_kana_residue")
        if target == source and JP_VISIBLE_RE.search(source):
            flags.append("untranslated_japanese")
        if "\x00" in target:
            flags.append("embedded_nul")

        source_color = [x for x in source_controls if x.startswith("%C")]
        target_color = [x for x in target_controls if x.startswith("%C")]
        if target_color != source_color:
            flags.append("added_or_changed_color_control")
        if any(x in target for x in ("%CFFFF", "%C000F", "%C222F")) and not any(
            x in source for x in ("%CFFFF", "%C000F", "%C222F")
        ):
            flags.append("synthetic_color_control")

        source_q = normalized_question_runs(source)
        target_q = normalized_question_runs(target)
        if target_q:
            if max(target_q) >= 4 and (not source_q or max(source_q) < max(target_q)):
                flags.append("expanded_question_run")
            elif source_q:
                inherited_question_rows.append(
                    {"key": key, "source_jp": source, "target_ko": target}
                )

        if flags:
            issues.append(
                {
                    "key": key,
                    "flags": flags,
                    "source_jp": source,
                    "target_ko": target,
                    "source_controls": source_controls,
                    "target_controls": target_controls,
                }
            )

        info["translated"] += 1
        info["with_controls"] += bool(target_controls)
        info["with_inherited_question_runs"] += bool(source_q and target_q)
        info["with_literal_percent"] += unknown_target_percent
        info["with_source_color_controls"] += bool(source_color)

    errors = {
        "extra_translation_keys": extra,
        "missing_visible_japanese_keys": missing_visible,
        "translation_issues": issues,
    }
    ok = not extra and not missing_visible and not issues
    result = {
        "schema": "remember11.ko-translation-static-qa.v2",
        "ok": ok,
        "semantic_source": "Japanese catalog only",
        "catalog_entries": len(catalog),
        "translated_entries": len(translations),
        "untranslated_technical_entries": len(missing),
        "untranslated_visible_japanese_entries": len(missing_visible),
        "counts": dict(info),
        "inherited_question_run_rows": inherited_question_rows,
        "errors": errors,
    }
    out = root / "audit" / "translation-static-qa.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "ok", "catalog_entries", "translated_entries",
        "untranslated_technical_entries", "untranslated_visible_japanese_entries"
    )}, ensure_ascii=False))
    if not ok:
        raise SystemExit(1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    audit(args.root)


if __name__ == "__main__":
    main()
