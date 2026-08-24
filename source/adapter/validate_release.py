from __future__ import annotations
import argparse, hashlib, json, struct, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from r11_tools import AfsArchive, decode_wrapped
from r11_script_pool import find_pointer_table, parse as parse_script, choice_string_indices
from r11_images import parse as parse_image
from r11_font import HEADER, encode_target
from r11_exe_ui import validate_executable
from r11_init import load_targets as load_init_targets
from build_release import translations, style_dialogue
from audit_translation import audit as audit_translations
from audit_ui_fidelity import audit as audit_ui_fidelity


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_image_offsets(data: bytes) -> int:
    obj = parse_image(data)
    base = len(obj['header'])
    if obj['kind'] == 'type3':
        for item in obj['items']:
            assert (item['offset'] - base) % 16 == 0
            got = struct.unpack_from('<I', data, 4 + item['index'] * 4)[0]
            assert got == (item['offset'] - base) // 16
    else:
        assert struct.unpack_from('<I', data, 20)[0] == len(data)
        for item in obj['items']:
            got = struct.unpack_from('<I', data, 0xA4 + item['index'] * 0x1C)[0]
            assert got == item['offset'] - base
    return obj['count']


def validate(root: Path, game: Path) -> dict:
    translation_qa = audit_translations(root)
    assert translation_qa['ok']
    ui_fidelity = audit_ui_fidelity(root)
    assert ui_fidelity['ok'] and ui_fidelity['changed_pixels_outside_annotated_boxes'] == 0
    release = root / 'release' / 'Remember11-Korean'
    file_dir = release / 'FILE'
    manifest = json.loads((release / 'patch-manifest.json').read_text(encoding='utf-8'))
    assert manifest['translations']['expected'] == manifest['translations']['built'] == len(translations(root))
    def iter_strings(value):
        if isinstance(value, dict):
            for child in value.values(): yield from iter_strings(child)
        elif isinstance(value, list):
            for child in value: yield from iter_strings(child)
        elif isinstance(value, str): yield value
    assert not any(len(x)>2 and x[1:3] == ':\\' for x in iter_strings(manifest))
    expected_files = {'mac-en.afs', 'etc-en.afs', 'bg-en.afs', 'ev-en.afs', 'bgmpc-en.afs', 'init.rp'}
    actual_files = {p.name for p in file_dir.iterdir() if p.is_file()}
    assert actual_files == expected_files, (actual_files, expected_files)
    assert not any((file_dir / x).exists() for x in ('mac.afs', 'etc.afs', 'bg.afs', 'ev.afs', 'bgmpc.afs'))
    assert sha(release / 'R11-Korean.exe') != sha(game / 'R11-English.exe')
    assert sha(file_dir / 'bgmpc-en.afs') == sha(game / 'FILE' / 'bgmpc.afs')

    # Verify every append-only init.rp pointer against the same final carrier map.
    init_source = decode_wrapped((game / 'FILE' / 'init.rp').read_bytes())
    init_output = decode_wrapped((file_dir / 'init.rp').read_bytes())
    init_targets = load_init_targets(root / 'gestalt-analysis', 'base')
    init_kinds = {}
    for site, row in init_targets.items():
        assert struct.unpack_from('<I', init_source, site)[0] == (row.get('pointer') or struct.unpack_from('<I', init_source, site)[0])
        ptr = struct.unpack_from('<I', init_output, site)[0]
        expected = b'\x90' * row['padding_90'] + encode_target(row['target_ko'], json.loads((root / 'build' / 'final' / 'carrier-map.json').read_text(encoding='utf-8')))
        assert init_output[ptr:ptr+len(expected)] == expected and init_output[ptr+len(expected)] == 0
        init_kinds[row['kind']] = init_kinds.get(row['kind'], 0) + 1
    assert init_kinds == {'tips': 265}, init_kinds

    source = game / 'FILE'
    arcs = {}
    for name in ('mac', 'etc', 'bg', 'ev'):
        src = AfsArchive(source / f'{name}.afs')
        out = AfsArchive(file_dir / f'{name}-en.afs')
        assert out.count == src.count
        arcs[name] = {'count': out.count, 'size': (file_dir / f'{name}-en.afs').stat().st_size}

    mapping = json.loads((root / 'build' / 'final' / 'carrier-map.json').read_text(encoding='utf-8'))
    exe_ui = validate_executable(release / 'R11-Korean.exe', mapping, root / 'catalog' / 'exe-ui-ko.json')
    assert manifest['executable_ui']['output_sha256'] == sha(release / 'R11-Korean.exe')
    trans = translations(root)
    mac = AfsArchive(file_dir / 'mac-en.afs')
    decoded = decode_wrapped(mac.raw(0))
    assert b'%CFFFF' not in decoded
    assert b'%C000F' in decoded
    assert b'%C222F' not in decoded
    info = find_pointer_table(decoded)
    key = 'mac.afs::0000::0001'
    assert info and info['refs'].get(1)
    ptr = info['refs'][1][0][1]
    raw = decoded[ptr:decoded.index(b'\0', ptr)]
    assert raw == encode_target(style_dialogue(trans[key], 0, True), mapping)

    # Verify every aligned physical-string pointer, including choice tables that
    # do not use the standard 73-opcode dialogue reference form.
    source_mac = AfsArchive(source / 'mac.afs')
    relocated_pointer_sites = 0
    relocated_choice_and_aux_pointers = 0
    black_styled_strings = 0
    black_styled_choice_strings = 0
    validated_choice_strings = 0
    for entry in source_mac.entries:
        source_decoded = decode_wrapped(source_mac.raw(entry.index))
        source_script = parse_script(source_decoded)
        if not source_script or source_script['mode'] != 'relocatable':
            continue
        choice_indices = choice_string_indices(source_decoded, source_script)
        output_decoded = decode_wrapped(mac.raw(entry.index))
        output_info = find_pointer_table(output_decoded)
        assert output_info and output_info['text_offset'] == source_script['text_offset']
        new_starts = []
        pos = output_info['text_offset']
        end = len(output_decoded) - 12
        while pos < end:
            stop = output_decoded.find(b'\0', pos, end)
            assert stop >= 0
            new_starts.append(pos)
            pos = stop + 1
        assert len(new_starts) == len(source_script['items'])
        for item, new_start in zip(source_script['items'], new_starts):
            key = f'mac.afs::{entry.index:04d}::{item["index"]:04d}'
            target = trans.get(key, item['text'])
            is_choice = item['index'] in choice_indices
            styled = style_dialogue(target, entry.index, bool(source_script['refs'].get(item['index'])) and not is_choice)
            stop = output_decoded.index(b'\0', new_start)
            output_raw = output_decoded[new_start:stop]
            assert output_raw == encode_target(styled, mapping), key
            if is_choice:
                validated_choice_strings += 1
                assert b'%' not in output_raw, (key, output_raw)
            if styled.startswith('%C000F'):
                black_styled_strings += 1
                if is_choice:
                    black_styled_choice_strings += 1
        old_to_new = {item['offset']: new for item, new in zip(source_script['items'], new_starts)}
        standard_sites = {q + 2 for refs in source_script['refs'].values() for q, _ in refs}
        for q in range(0, source_script['text_offset'] - 1, 2):
            old_ptr = struct.unpack_from('<H', source_decoded, q)[0]
            if old_ptr not in old_to_new:
                continue
            assert struct.unpack_from('<H', output_decoded, q)[0] == old_to_new[old_ptr]
            relocated_pointer_sites += 1
            relocated_choice_and_aux_pointers += q not in standard_sites
    assert relocated_choice_and_aux_pointers > 0
    assert black_styled_strings > 30000
    assert black_styled_choice_strings == 0
    assert validated_choice_strings == 336, validated_choice_strings

    etc = AfsArchive(file_dir / 'etc-en.afs')
    built_font = root / 'build' / 'final' / 'FNT2626.FOP'
    assert hashlib.sha256(decode_wrapped(etc.raw(0))).hexdigest() == sha(built_font)
    # Preserve all 188 English technical-carrier glyphs used by transient text.
    english_font = (root / 'extracted' / 'etc-en' / 'decoded' / '0000__FNT2626.FOP').read_bytes()
    japanese_font = (root / 'extracted' / 'etc-jp' / 'decoded' / '0000__FNT2626.FOP').read_bytes()
    korean_font = built_font.read_bytes()
    _, metaoff, metasize, glyphoff, glyphsize, blocksize, *_ = HEADER.unpack_from(english_font)
    protected_glyphs = []
    for idx in range(glyphsize // blocksize):
        a = glyphoff + idx * blocksize
        b = a + blocksize
        if (english_font[a:b] != japanese_font[a:b] or
                english_font[metaoff+idx*2:metaoff+idx*2+2] != japanese_font[metaoff+idx*2:metaoff+idx*2+2]):
            protected_glyphs.append(idx)
            assert korean_font[a:b] == english_font[a:b]
            assert korean_font[metaoff+idx*2:metaoff+idx*2+2] == english_font[metaoff+idx*2:metaoff+idx*2+2]
    assert protected_glyphs == list(range(940, 1128)), protected_glyphs
    audit = json.loads((root / 'ui' / 'rendered' / 'ui-build-audit.json').read_text(encoding='utf-8'))
    checked_ui = 0
    for entry in sorted({int(Path(x['source']).parts[0].split('__')[0]) for x in audit['etc']}):
        checked_ui += bool(validate_image_offsets(decode_wrapped(etc.raw(entry))))
    bg_arc = AfsArchive(file_dir / 'bg-en.afs')
    ev_arc = AfsArchive(file_dir / 'ev-en.afs')
    for x in audit['bg']:
        checked_ui += bool(validate_image_offsets(bg_arc.raw(x['index'])))
    for x in audit['ev']:
        checked_ui += bool(validate_image_offsets(ev_arc.raw(x['index'])))
    assert checked_ui == 40, checked_ui

    zip_path = root / 'release' / 'Remember11-Korean.zip'
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        assert 'Remember11-Korean/R11-Korean.exe' in names
        assert all(f'Remember11-Korean/FILE/{x}' in names for x in expected_files)
        assert z.testzip() is None

    result = {
        'ok': True,
        'translations': len(trans),
        'translation_static_qa': {'ok': translation_qa['ok'], 'visible_japanese_remaining': translation_qa['untranslated_visible_japanese_entries']},
        'ui_fidelity_qa': {'ok': ui_fidelity['ok'], 'assets': ui_fidelity['assets'], 'outside_box_changes': ui_fidelity['changed_pixels_outside_annotated_boxes']},
        'carrier_glyphs': len(mapping),
        'protected_english_carrier_glyphs': len(protected_glyphs),
        'validated_ui_containers': checked_ui,
        'relocated_script_pointer_sites': relocated_pointer_sites,
        'relocated_choice_and_aux_pointers': relocated_choice_and_aux_pointers,
        'black_styled_strings': black_styled_strings,
        'black_styled_choice_strings': black_styled_choice_strings,
        'validated_choice_strings_without_controls': validated_choice_strings,
        'validated_init_pointer_sites': len(init_targets),
        'validated_init_by_kind': init_kinds,
        'executable_ui': exe_ui,
        'archives': arcs,
        'release': str(release),
        'zip': str(zip_path),
        'zip_size': zip_path.stat().st_size,
    }
    out = root / 'build' / 'final' / 'release-validation.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--game', type=Path, required=True)
    a = ap.parse_args()
    validate(a.root, a.game)


if __name__ == '__main__':
    main()

