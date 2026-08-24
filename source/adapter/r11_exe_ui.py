from __future__ import annotations

import hashlib
import json
import shutil
import struct
from pathlib import Path

import pefile

from r11_font import encode_target


RESOURCE_LANGUAGE = 1041
MENU_REPLACEMENTS = {
    "&File": "파일(&F)",
    "&Quit": "게임 종료(&X)",
    "&Display": "화면(&D)",
    "&Window Mode": "창 모드(&W)",
    "&Fullscreen Mode": "전체 화면(&F)",
    "&Config": "설정(&C)",
    "&Key Config": "입력 설정(&I)",
}
DIALOG_REPLACEMENTS = {
    103: {
        "Version Info": "버전 정보",
        "OK": "확인",
    },
    1112: {
        "Key Config": "입력 설정",
        "Defaults": "초기 설정",
        "OK": "확인",
        "Cancel": "취소",
        "○ Button": "○ 버튼",
        "× Button": "× 버튼",
        "△ Button": "△ 버튼",
        "□ Button": "□ 버튼",
        "L1 Button": "L1 버튼",
        "L2 Button": "L2 버튼",
        "R1 Button": "R1 버튼",
        "R2 Button": "R2 버튼",
        "R3 Button": "R3 버튼",
        "↑ Key": "↑ 키",
        "↓ Key": "↓ 키",
        "← Key": "← 키",
        "→ Key": "→ 키",
        # Gestalt 1.3.0 replaces button names with clear action descriptions.
        "Advance, Auto": "진행·자동",
        "Cancel, Textbox": "취소·대사창",
        "Backlog": "백로그",
        "Menu": "메뉴",
        "Select TIP": "TIP 선택",
        "Up": "위",
        "Down": "아래",
        "Left": "왼쪽",
        "Right": "오른쪽",
        "Skip (Toggle)": "스킵 전환",
        "Quick Save": "빠른 저장",
        "Skip All ": "전체 스킵",
        "Skip (Hold)": "누르는 동안 스킵",
    },
}
FONT_REPLACEMENTS = {
    "MS UI Gothic": "맑은 고딕",
    "ＭＳ Ｐゴシック": "맑은 고딕",
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_catalog(path: Path) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema") != "remember11.exe-ui.ko.v1":
        raise ValueError("unexpected executable UI catalog schema")
    return catalog


def target_texts(catalog: dict) -> list[str]:
    return [entry["target_ko"] for entry in catalog["entries"]]


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _pad(out: bytearray, alignment: int = 4) -> None:
    out.extend(b"\0" * (_align(len(out), alignment) - len(out)))


def _read_u16z(data: bytes, pos: int) -> tuple[str, int]:
    start = pos
    while pos + 1 < len(data) and data[pos : pos + 2] != b"\0\0":
        pos += 2
    if pos + 1 >= len(data):
        raise ValueError("unterminated UTF-16 resource string")
    return data[start:pos].decode("utf-16le"), pos + 2


def _write_u16z(out: bytearray, value: str) -> None:
    out.extend(value.encode("utf-16le") + b"\0\0")


def _read_res_name(data: bytes, pos: int) -> tuple[tuple[str, object], int]:
    word = struct.unpack_from("<H", data, pos)[0]
    if word == 0:
        return ("none", None), pos + 2
    if word == 0xFFFF:
        return ("ordinal", struct.unpack_from("<H", data, pos + 2)[0]), pos + 4
    value, pos = _read_u16z(data, pos)
    return ("string", value), pos


def _write_res_name(out: bytearray, value: tuple[str, object]) -> None:
    kind, payload = value
    if kind == "none":
        out.extend(struct.pack("<H", 0))
    elif kind == "ordinal":
        out.extend(struct.pack("<HH", 0xFFFF, int(payload)))
    elif kind == "string":
        _write_u16z(out, str(payload))
    else:
        raise ValueError(f"unknown resource name kind {kind}")


def _replace_res_name(value: tuple[str, object], replacements: dict[str, str]) -> tuple[str, object]:
    if value[0] == "string" and value[1] in replacements:
        return "string", replacements[str(value[1])]
    return value


def _parse_menu(data: bytes) -> tuple[int, bytes, list[dict]]:
    version, header_size = struct.unpack_from("<HH", data, 0)
    if version != 0:
        raise ValueError(f"unsupported extended MENU version {version}")
    extra = data[4 : 4 + header_size]
    pos = 4 + header_size

    def parse_level() -> list[dict]:
        nonlocal pos
        nodes = []
        while True:
            option = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            popup = bool(option & 0x10)
            item_id = None
            if not popup:
                item_id = struct.unpack_from("<H", data, pos)[0]
                pos += 2
            text, pos = _read_u16z(data, pos)
            children = parse_level() if popup else []
            nodes.append({"option": option, "id": item_id, "text": text, "children": children})
            if option & 0x80:
                return nodes

    nodes = parse_level()
    if pos != len(data):
        raise ValueError(f"MENU trailing bytes: {len(data) - pos}")
    return version, extra, nodes


def _build_menu(data: bytes, replacements: dict[str, str]) -> tuple[bytes, int]:
    version, extra, nodes = _parse_menu(data)
    changed = 0
    out = bytearray(struct.pack("<HH", version, len(extra)) + extra)

    def emit(items: list[dict]) -> None:
        nonlocal changed
        for item in items:
            out.extend(struct.pack("<H", item["option"]))
            if item["id"] is not None:
                out.extend(struct.pack("<H", item["id"]))
            text = replacements.get(item["text"], item["text"])
            changed += text != item["text"]
            _write_u16z(out, text)
            if item["children"]:
                emit(item["children"])

    emit(nodes)
    rebuilt = bytes(out)
    _parse_menu(rebuilt)
    return rebuilt, changed


def _parse_dialog(data: bytes) -> dict:
    extended = struct.unpack_from("<HH", data, 0) == (1, 0xFFFF)
    if extended:
        fixed = struct.unpack_from("<HHIIIHhhhh", data, 0)
        style, count, pos = fixed[4], fixed[5], 26
    else:
        fixed = struct.unpack_from("<IIHhhhh", data, 0)
        style, count, pos = fixed[0], fixed[2], 18
    menu, pos = _read_res_name(data, pos)
    window_class, pos = _read_res_name(data, pos)
    title, pos = _read_res_name(data, pos)
    font = None
    if style & 0x40:  # DS_SETFONT
        if extended:
            font_fixed = struct.unpack_from("<HHBB", data, pos)
            pos += 6
        else:
            font_fixed = struct.unpack_from("<H", data, pos)
            pos += 2
        face, pos = _read_u16z(data, pos)
        font = {"fixed": font_fixed, "face": face}
    items = []
    for _ in range(count):
        pos = _align(pos)
        if extended:
            item_fixed = struct.unpack_from("<IIIhhhhI", data, pos)
            pos += 24
        else:
            item_fixed = struct.unpack_from("<IIhhhhH", data, pos)
            pos += 18
        item_class, pos = _read_res_name(data, pos)
        item_title, pos = _read_res_name(data, pos)
        extra_size = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        extra = data[pos : pos + extra_size]
        pos += extra_size
        items.append({"fixed": item_fixed, "class": item_class, "title": item_title, "extra": extra})
    if pos != len(data):
        trailing = data[pos:]
        # Gestalt 1.3.0 leaves six non-zero bytes after the declared key-config
        # item list. Windows ignores bytes beyond the item count; accept only a
        # tiny tail and rebuild it away instead of copying stale overlap bytes.
        if any(trailing) and len(trailing) > 16:
            raise ValueError(f"DIALOG trailing non-zero bytes: {len(data) - pos}")
    return {
        "extended": extended,
        "fixed": fixed,
        "menu": menu,
        "class": window_class,
        "title": title,
        "font": font,
        "items": items,
    }


def _build_dialog(data: bytes, replacements: dict[str, str]) -> tuple[bytes, int]:
    dialog = _parse_dialog(data)
    out = bytearray()
    changed = 0
    if dialog["extended"]:
        out.extend(struct.pack("<HHIIIHhhhh", *dialog["fixed"]))
    else:
        out.extend(struct.pack("<IIHhhhh", *dialog["fixed"]))
    _write_res_name(out, dialog["menu"])
    _write_res_name(out, dialog["class"])
    new_title = _replace_res_name(dialog["title"], replacements)
    changed += new_title != dialog["title"]
    _write_res_name(out, new_title)
    if dialog["font"]:
        if dialog["extended"]:
            out.extend(struct.pack("<HHBB", *dialog["font"]["fixed"]))
        else:
            out.extend(struct.pack("<H", *dialog["font"]["fixed"]))
        old_face = dialog["font"]["face"]
        new_face = FONT_REPLACEMENTS.get(old_face, old_face)
        changed += new_face != old_face
        _write_u16z(out, new_face)
    for item in dialog["items"]:
        _pad(out)
        if dialog["extended"]:
            out.extend(struct.pack("<IIIhhhhI", *item["fixed"]))
        else:
            out.extend(struct.pack("<IIhhhhH", *item["fixed"]))
        _write_res_name(out, item["class"])
        new_item_title = _replace_res_name(item["title"], replacements)
        changed += new_item_title != item["title"]
        _write_res_name(out, new_item_title)
        out.extend(struct.pack("<H", len(item["extra"])))
        out.extend(item["extra"])
    rebuilt = bytes(out)
    parsed = _parse_dialog(rebuilt)
    if len(parsed["items"]) != len(dialog["items"]):
        raise ValueError("dialog item count changed")
    return rebuilt, changed


def _resource_slot(pe: pefile.PE, type_id: int, name_id: int, language: int) -> dict:
    for type_entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if type_entry.name is not None or type_entry.struct.Id != type_id:
            continue
        for name_entry in type_entry.directory.entries:
            if name_entry.name is not None or name_entry.struct.Id != name_id:
                continue
            for lang_entry in name_entry.directory.entries:
                if lang_entry.struct.Id != language:
                    continue
                info = lang_entry.data.struct
                raw_offset = pe.get_offset_from_rva(info.OffsetToData)
                # Some community builds keep a stale resource Size that overlaps
                # the next leaf after a longer dialog was recompiled. Never treat
                # bytes owned by that following resource as writable capacity.
                next_offsets = []
                for other_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                    for other_name in other_type.directory.entries:
                        for other_lang in other_name.directory.entries:
                            other = other_lang.data.struct
                            other_raw = pe.get_offset_from_rva(other.OffsetToData)
                            if other_raw > raw_offset:
                                next_offsets.append(other_raw)
                physical_capacity = min(next_offsets) - raw_offset if next_offsets else info.Size
                capacity = min(info.Size, physical_capacity)
                return {
                    "blob": pe.get_data(info.OffsetToData, capacity),
                    "raw_offset": raw_offset,
                    "capacity": capacity,
                    "declared_size": info.Size,
                    "data_entry_offset": info.get_file_offset(),
                }
    raise KeyError(f"resource {type_id}/{name_id}/{language} not found")


def _resource_blob(pe: pefile.PE, type_id: int, name_id: int, language: int) -> bytes:
    return _resource_slot(pe, type_id, name_id, language)["blob"]


def _patch_native_resources(path: Path) -> dict:
    pe = pefile.PE(str(path), fast_load=False)
    menu_slot = _resource_slot(pe, 4, 111, RESOURCE_LANGUAGE)
    menu, menu_changed = _build_menu(menu_slot["blob"], MENU_REPLACEMENTS)
    updates = [(menu_slot, menu)]
    dialog_changed = 0
    for dialog_id, replacements in DIALOG_REPLACEMENTS.items():
        slot = _resource_slot(pe, 5, dialog_id, RESOURCE_LANGUAGE)
        blob, changed = _build_dialog(slot["blob"], replacements)
        updates.append((slot, blob))
        dialog_changed += changed
    data = bytearray(path.read_bytes())
    for slot, blob in updates:
        if len(blob) > slot["capacity"]:
            raise ValueError("rebuilt native resource exceeds its bound source slot")
        start = slot["raw_offset"]
        data[start : start + slot["capacity"]] = blob + b"\0" * (slot["capacity"] - len(blob))
        struct.pack_into("<I", data, slot["data_entry_offset"] + 4, len(blob))
    pe.close()
    path.write_bytes(data)
    # Parse every emitted template from the patched executable independently.
    checked = pefile.PE(str(path), fast_load=False)
    _parse_menu(_resource_blob(checked, 4, 111, RESOURCE_LANGUAGE))
    for dialog_id in DIALOG_REPLACEMENTS:
        _parse_dialog(_resource_blob(checked, 5, dialog_id, RESOURCE_LANGUAGE))
    return {
        "resources": len(updates),
        "menu_strings": menu_changed,
        "dialog_and_font_strings": dialog_changed,
    }

def patch_executable(source: Path, output: Path, mapping: dict, catalog_path: Path) -> dict:
    catalog = load_catalog(catalog_path)
    source_data = source.read_bytes()
    expected_hash = catalog["source_hashes"]["R11-English.exe"]
    if sha_bytes(source_data) != expected_hash:
        raise ValueError("R11-English.exe hash does not match the bound baseline")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    native_stats = _patch_native_resources(output)

    pe = pefile.PE(str(output), fast_load=False)
    section_name = catalog["pool"]["section"]
    section = next(
        (s for s in pe.sections if s.Name.rstrip(b"\0").decode("ascii", "replace") == section_name),
        None,
    )
    if section is None:
        raise ValueError(f"missing executable pool section {section_name}")
    section_raw = section.PointerToRawData
    section_end = section_raw + section.SizeOfRawData
    pool_start = section_raw + int(catalog["pool"]["offset_in_section"])
    image_base = pe.OPTIONAL_HEADER.ImageBase
    pe.close()
    data = bytearray(output.read_bytes())

    encoded_by_text: dict[str, bytes] = {}
    for entry in catalog["entries"]:
        encoded_by_text.setdefault(entry["target_ko"], encode_target(entry["target_ko"], mapping))
    # Several UI routines do not keep a pointer to a C string. Instead they
    # copy a fixed-size label with a series of absolute reads from offsets
    # inside the source string. Keep every translated string in a zero-padded
    # slot large enough for those interior reads; otherwise a short Korean
    # label can make the final read spill into the next pool string.
    reserved_by_text = {text: len(encoded) + 1 for text, encoded in encoded_by_text.items()}
    for entry in catalog["entries"]:
        text = entry["target_ko"]
        for reference in entry["references"]:
            delta = int(reference.get("target_delta", 0))
            if delta < 0:
                raise ValueError(f"negative executable UI target delta for {entry['key']}")
            reserved_by_text[text] = max(reserved_by_text[text], delta + 4)
    cursor = pool_start
    pool_locations: dict[str, tuple[int, int, int]] = {}
    for text, encoded in encoded_by_text.items():
        cursor = _align(cursor, 4)
        reserved = reserved_by_text[text]
        end = cursor + reserved
        if end > section_end:
            raise ValueError("localized executable UI pool does not fit in .rdata2")
        if any(data[cursor:end]):
            raise ValueError(f"localized executable UI pool is not empty at {cursor:#x}")
        data[cursor : cursor + len(encoded)] = encoded
        data[cursor + len(encoded) : end] = b"\0" * (reserved - len(encoded))
        rva = section.VirtualAddress + (cursor - section_raw)
        pool_locations[text] = (cursor, image_base + rva, reserved)
        cursor = end

    patched_refs = 0
    for entry in catalog["entries"]:
        _, target_va, _ = pool_locations[entry["target_ko"]]
        for reference in entry["references"]:
            offset = int(reference["offset"])
            expected_value = int(reference["value"])
            if struct.unpack_from("<I", data, offset)[0] != expected_value:
                raise ValueError(f"pointer source mismatch at {offset:#x}")
            struct.pack_into("<I", data, offset, target_va + int(reference.get("target_delta", 0)))
            patched_refs += 1

    # Refresh the PE checksum after both UpdateResource and direct pointer/pool writes.
    checksum_pe = pefile.PE(data=bytes(data), fast_load=False)
    checksum_offset = checksum_pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum")
    struct.pack_into("<I", data, checksum_offset, checksum_pe.generate_checksum())
    output.write_bytes(data)

    result = {
        "source_sha256": expected_hash,
        "output_sha256": sha_bytes(bytes(data)),
        "catalog_entries": len(catalog["entries"]),
        "unique_pool_strings": len(encoded_by_text),
        "patched_references": patched_refs,
        "pool_section": section_name,
        "pool_rva": section.VirtualAddress + (pool_start - section_raw),
        "pool_size": cursor - pool_start,
        "native_resources": native_stats,
    }
    return result


def validate_executable(output: Path, mapping: dict, catalog_path: Path) -> dict:
    catalog = load_catalog(catalog_path)
    pe = pefile.PE(str(output), fast_load=False)
    data = output.read_bytes()
    image_base = pe.OPTIONAL_HEADER.ImageBase
    validated_refs = 0
    targets = set()
    for entry in catalog["entries"]:
        expected = encode_target(entry["target_ko"], mapping)
        entry_targets = set()
        for reference in entry["references"]:
            target_va = struct.unpack_from("<I", data, int(reference["offset"]))[0]
            entry_targets.add(target_va - int(reference.get("target_delta", 0)))
            validated_refs += 1
        if len(entry_targets) != 1:
            raise ValueError(f"localized executable reference base mismatch for {entry['key']}")
        base_target_va = entry_targets.pop()
        raw = pe.get_offset_from_rva(base_target_va - image_base)
        actual = data[raw : raw + len(expected)]
        if actual != expected or data[raw + len(expected)] != 0:
            raise ValueError(f"localized executable string mismatch for {entry['key']}")
        targets.add(base_target_va)
    menu = _resource_blob(pe, 4, 111, RESOURCE_LANGUAGE)
    _, _, nodes = _parse_menu(menu)
    menu_texts = []

    def collect(items: list[dict]) -> None:
        for item in items:
            menu_texts.append(item["text"])
            collect(item["children"])

    collect(nodes)
    for target in MENU_REPLACEMENTS.values():
        if target not in menu_texts:
            raise ValueError(f"missing native menu translation {target}")
    for dialog_id, replacements in DIALOG_REPLACEMENTS.items():
        dialog = _parse_dialog(_resource_blob(pe, 5, dialog_id, RESOURCE_LANGUAGE))
        values = []
        if dialog["title"][0] == "string":
            values.append(dialog["title"][1])
        if dialog["font"]:
            values.append(dialog["font"]["face"])
        for item in dialog["items"]:
            if item["title"][0] == "string":
                values.append(item["title"][1])
        # Retail and Gestalt use mutually exclusive labels for the same keys.
        # Reject any surviving source label and require the shared controls.
        for source in replacements:
            if source in values:
                raise ValueError(f"unpatched native dialog source {source}")
        required_sources = ("Version Info", "OK") if dialog_id == 103 else ("Key Config", "Defaults", "OK", "Cancel")
        for source in required_sources:
            target = replacements[source]
            if target not in values:
                raise ValueError(f"missing native dialog translation {target}")
        if "맑은 고딕" not in values:
            raise ValueError(f"Korean native dialog font missing from dialog {dialog_id}")
    return {
        "validated_references": validated_refs,
        "validated_unique_targets": len(targets),
        "native_menu_strings": len(MENU_REPLACEMENTS),
        "native_dialog_strings": sum(len(x) for x in DIALOG_REPLACEMENTS.values()),
    }
