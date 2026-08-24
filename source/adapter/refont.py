#!/usr/bin/env python3
"""Re-render the Hangul carrier glyphs in FNT2626.FOP and repack etc-en.afs.

The published build wrote every Hangul glyph through an inverted opacity table,
so the engine drew each stroke as a pale body with a hard black fringe, and it
centred each glyph in the 48px storage cell instead of the 34px advance box the
metadata declares. This rebuilds only the glyph bitmaps. The carrier index and
CP932 code assignment is read back from the shipped carrier-map.json, so every
already-encoded scenario string, TIPS page and init.rp pointer stays valid and
no scenario rebuild is required.
"""
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r11_font import HEADER, INK_BOX, Fitter, encode_image, decode_block
from r11_tools import AfsArchive, decode_wrapped, encode_wrapped, sha256

ROOT = Path(__file__).resolve().parents[1]
BASE_FOP = ROOT / 'extracted/etc-en/decoded/0000__FNT2626.FOP'
BUILDS = {'final': 'Remember11-Korean', 'gestalt': 'Remember11-Korean-Gestalt'}


def rebuild_fop(base: Path, carrier_map: dict, font: Path, weight: int) -> tuple[bytes, dict]:
    data = bytearray(base.read_bytes())
    _, metaoff, _, glyphoff, _, blocksize, _, w, h, _ = HEADER.unpack_from(data)
    if (metaoff, glyphoff, blocksize, w, h) != (0x1e, 0x5000, 0x240, 48, 48):
        raise ValueError('unexpected PC FOP header')
    hangul = ''.join(c for c in carrier_map if 0xAC00 <= ord(c) <= 0xD7A3)
    fitter = Fitter(font, weight, hangul, INK_BOX)
    for ch, info in carrier_map.items():
        idx = info['index']
        data[glyphoff + idx * blocksize: glyphoff + (idx + 1) * blocksize] = encode_image(fitter.render(ch))
        data[metaoff + idx * 2: metaoff + idx * 2 + 2] = bytes((0, 17))
    return bytes(data), {'glyphs': len(carrier_map), 'font': str(font), 'weight': weight,
                         'fitted_size': fitter.size, 'union_ink': fitter.union, 'ink_box': list(INK_BOX)}


def level_profile(data: bytes, idxs) -> dict:
    """Distribution of the engine's 4 opacity levels over inked pixels."""
    from collections import Counter
    _, _, _, glyphoff, _, blocksize, *_ = HEADER.unpack_from(data)
    c = Counter()
    for i in idxs:
        block = data[glyphoff + i * blocksize: glyphoff + (i + 1) * blocksize]
        for bt in block:
            for shift in (6, 2, 4, 0):
                c[(bt >> shift) & 3] += 1
    ink = sum(v for k, v in c.items() if k)
    return {f'level{k}': round(100 * c[k] / ink, 1) for k in (1, 2, 3)} if ink else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--font', type=Path, default=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'))
    ap.add_argument('--weight', type=int, default=500)
    ap.add_argument('--builds', default='final,gestalt')
    ap.add_argument('--no-deploy', action='store_true', help='write build/ only, leave release/ alone')
    args = ap.parse_args()

    report = {}
    for name in args.builds.split(','):
        work = ROOT / 'build' / name
        cmap = json.loads((work / 'carrier-map.json').read_text(encoding='utf-8'))
        old = (work / 'FNT2626.FOP').read_bytes()
        new, stats = rebuild_fop(BASE_FOP, cmap, args.font, args.weight)

        # Nothing outside the carrier slots may move: same size, same header,
        # same metadata, and every non-carrier glyph byte-identical to before.
        _, metaoff, _, glyphoff, glyphsize, blocksize, *_ = HEADER.unpack_from(new)
        if len(new) != len(old):
            raise ValueError('size drift')
        carriers = {v['index'] for v in cmap.values()}
        changed = {i for i in range(glyphsize // blocksize)
                   if new[glyphoff + i * blocksize: glyphoff + (i + 1) * blocksize]
                   != old[glyphoff + i * blocksize: glyphoff + (i + 1) * blocksize]}
        stray = changed - carriers
        if stray:
            raise ValueError(f'{len(stray)} non-carrier glyphs changed: {sorted(stray)[:10]}')
        if new[:glyphoff] != old[:glyphoff]:
            raise ValueError('header/metadata drift')
        stats.update(
            carriers=len(carriers), reskinned=len(changed),
            untouched_glyphs=glyphsize // blocksize - len(carriers),
            levels_before=level_profile(old, sorted(carriers)),
            levels_after=level_profile(new, sorted(carriers)),
            levels_original_jp=level_profile(
                (ROOT / 'extracted/etc-jp/decoded/0000__FNT2626.FOP').read_bytes(), range(1200, 1700)),
        )
        (work / 'FNT2626.FOP').write_bytes(new)

        arc_path = work / 'archives' / 'etc-en.afs'
        arc = AfsArchive(arc_path)
        if decode_wrapped(arc.raw(0)) != old:
            raise ValueError(f'{arc_path} entry 0 is not the build font')
        res = arc.rebuild(arc_path, replacements={0: encode_wrapped(new)})
        if decode_wrapped(AfsArchive(arc_path).raw(0)) != new:
            raise ValueError('repacked font failed to decode back')
        stats['etc_en_afs'] = {'size': res['size'], 'sha256': res['sha256']}

        if not args.no_deploy:
            rel = ROOT / 'release' / BUILDS[name]
            shutil.copy2(arc_path, rel / 'FILE' / 'etc-en.afs')
            man_path = rel / 'patch-manifest.json'
            man = json.loads(man_path.read_text(encoding='utf-8'))
            man['font'] = {**man.get('font', {}), **{k: stats[k] for k in
                           ('font', 'weight', 'fitted_size', 'union_ink', 'ink_box', 'carriers')},
                           'revision': 'glyph-opacity-and-advance-fix'}
            if isinstance(man.get('archives'), dict) and 'etc-en.afs' in man['archives']:
                man['archives']['etc-en.afs'] = stats['etc_en_afs']
            man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding='utf-8')
            stats['deployed'] = str(rel / 'FILE' / 'etc-en.afs')
        report[name] = stats

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
