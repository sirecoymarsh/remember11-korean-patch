#!/usr/bin/env python3
"""Build swappable etc-en.afs variants at several font weights.

Only the glyph bitmaps differ between variants. The carrier index and CP932
code assignment is read back from the shipped carrier-map.json, so every
variant stays valid against the scenario that is already installed -- swap the
file, restart the game, and nothing else has to change.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r11_font import HEADER, INK_BOX, Fitter, encode_image
from r11_tools import AfsArchive, decode_wrapped, encode_wrapped

ROOT = Path(__file__).resolve().parents[1]
BASE_FOP = ROOT / 'extracted/etc-en/decoded/0000__FNT2626.FOP'


def bake(carrier_map: dict, font: Path, weight: int) -> tuple[bytes, dict]:
    data = bytearray(BASE_FOP.read_bytes())
    _, metaoff, _, glyphoff, _, blocksize, _, w, h, _ = HEADER.unpack_from(data)
    if (metaoff, glyphoff, blocksize, w, h) != (0x1e, 0x5000, 0x240, 48, 48):
        raise ValueError('unexpected PC FOP header')
    hangul = ''.join(c for c in carrier_map if 0xAC00 <= ord(c) <= 0xD7A3)
    f = Fitter(font, weight, hangul, INK_BOX)
    ink = 0
    for ch, info in carrier_map.items():
        im = f.render(ch)
        i = info['index']
        block = encode_image(im)
        data[glyphoff + i * blocksize: glyphoff + (i + 1) * blocksize] = block
        data[metaoff + i * 2: metaoff + i * 2 + 2] = bytes((0, 17))
        # Count ink the way the engine sees it: after quantisation to the four
        # opacity levels, so the number is comparable to the original font's.
        ink += sum(1 for bt in block for s in (6, 2, 4, 0) if (bt >> s) & 3)
    return bytes(data), {'weight': weight, 'fitted_size': f.size,
                         'width_scale': f.width_scale, 'median_ink': list(f.median),
                         'ink_per_glyph': round(ink / len(carrier_map))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', default='gestalt', choices=('gestalt', 'final'))
    ap.add_argument('--weights', default='700,800,900')
    ap.add_argument('--font', type=Path, default=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'))
    ap.add_argument('--out', type=Path, default=ROOT / 'runtime-test' / 'font-variants')
    a = ap.parse_args()

    work = ROOT / 'build' / a.build
    cmap = json.loads((work / 'carrier-map.json').read_text(encoding='utf-8'))
    src = AfsArchive(work / 'archives' / 'etc-en.afs')
    a.out.mkdir(parents=True, exist_ok=True)

    report = {}
    for weight in (int(w) for w in a.weights.split(',')):
        fop, stats = bake(cmap, a.font, weight)
        out = a.out / f'etc-en-w{weight}.afs'
        info = src.rebuild(out, replacements={0: encode_wrapped(fop)})
        if decode_wrapped(AfsArchive(out).raw(0)) != fop:
            raise ValueError(f'w{weight}: repacked font failed to decode back')
        report[weight] = {**stats, 'file': out.name, 'size': info['size'],
                          'sha256': info['sha256'][:16]}
        print(f'w{weight}: size={stats["fitted_size"]} xscale={stats["width_scale"]} '
              f'ink/glyph={stats["ink_per_glyph"]}px -> {out.name}', flush=True)

    (a.out / 'variants.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                         encoding='utf-8')
    readme = (
        '# 대사 폰트 굵기 변형본\n\n'
        f'`{a.build}` 빌드의 캐리어 배정을 그대로 쓰므로, 이미 설치된 시나리오와 100% 호환됩니다.\n'
        '글리프 비트맵만 다릅니다.\n\n'
        '## 바꾸는 법\n\n'
        '원하는 파일을 게임 폴더의 `FILE\\etc-en.afs` 자리에 덮어쓰고 게임을 다시 켜면 됩니다.\n'
        '세이브 데이터에는 영향이 없습니다.\n\n'
        '| 파일 | 굵기 | 글자당 잉크 |\n|---|---|---|\n'
        + ''.join(f'| `{v["file"]}` | {k} | {v["ink_per_glyph"]}px |\n'
                  for k, v in sorted(report.items()))
        + '\n원본 일본어 폰트의 글자당 잉크는 598px입니다.\n'
    )
    (a.out / 'README-KO.md').write_text(readme, encoding='utf-8')
    print('\nwrote', a.out)


if __name__ == '__main__':
    main()
