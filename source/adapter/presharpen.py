#!/usr/bin/env python3
"""Pre-compensate the glyphs for the engine's known downscale.

At 800x600 the engine draws the 34px ink box into roughly 24 screen pixels with
bilinear filtering (established by correlating live captures against candidate
filters: bilinear 47.5 RMSE vs nearest 53.3). That resample is a known linear
operator, so instead of storing a glyph that merely looks right at 34px, store
the one whose *downscaled* image best matches a crisp 24px target.

Gradient descent on S with the adjoint of the resampler, then quantised to the
font's four opacity levels. Only worth it while the game runs at 800x600 -- at
1280x960 the same box lands on ~38 pixels and is upscaled instead, so the plain
build is already optimal there.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from r11_font import HEADER, INK_BOX, Fitter, encode_image
from r11_tools import AfsArchive, decode_wrapped, encode_wrapped

ROOT = Path(__file__).resolve().parents[1]
BASE_FOP = ROOT / 'extracted/etc-en/decoded/0000__FNT2626.FOP'
SS = 4
BOX_W = INK_BOX[2] - INK_BOX[0]      # 34
BOX_H = INK_BOX[3] - INK_BOX[1]      # 34


def to_list(im):
    return [p / 255 for p in im.get_flattened_data()]


def down(vals, w, h, tw, th):
    im = Image.new('F', (w, h))
    im.putdata(vals)
    return list(im.resize((tw, th), Image.Resampling.BILINEAR).getdata())


def up(vals, w, h, tw, th):
    im = Image.new('F', (w, h))
    im.putdata(vals)
    return list(im.resize((tw, th), Image.Resampling.BILINEAR).getdata())


def optimise(target, w0, iters, gain, target_px):
    """S starts at the plain render; step against the downscale residual.

    The upsample used as the adjoint carries a scale of (BOX/target)^2, so the
    step is normalised by it -- otherwise the iteration overshoots and the
    glyph blows out into a solid blob.
    """
    norm = (BOX_W / target_px) ** 2
    s = list(w0)
    for _ in range(iters):
        d = down(s, BOX_W, BOX_H, target_px, target_px)
        err = [t - v for t, v in zip(target, d)]
        grad = up(err, target_px, target_px, BOX_W, BOX_H)
        s = [min(1.0, max(0.0, a + gain * g / norm)) for a, g in zip(s, grad)]
    return s


def supersampled(fitter, ch):
    """The glyph at SS resolution, in the same geometry Fitter.render uses."""
    big = Image.new('L', (48 * SS, 48 * SS), 255)
    ImageDraw.Draw(big).text((fitter.dx, fitter.dy), ch, font=fitter.font, fill=0, anchor='ls')
    if fitter.width_scale != 1.0:
        big = big.resize((round(48 * SS * fitter.width_scale), 48 * SS), Image.Resampling.LANCZOS)
        out = Image.new('L', (48 * SS, 48 * SS), 255)
        out.paste(big, (0, 0))
        big = out
    return big.crop((INK_BOX[0] * SS, INK_BOX[1] * SS, INK_BOX[2] * SS, INK_BOX[3] * SS))


def build(carrier_map, font, weight, target_px, iters, gain):
    data = bytearray(BASE_FOP.read_bytes())
    _, metaoff, _, glyphoff, _, blocksize, _, w, h, _ = HEADER.unpack_from(data)
    hangul = ''.join(c for c in carrier_map if 0xAC00 <= ord(c) <= 0xD7A3)
    fitter = Fitter(font, weight, hangul, INK_BOX)

    improved = 0
    rms_before = rms_after = 0.0
    for ch, info in carrier_map.items():
        big = supersampled(fitter, ch)
        # ideal on-screen image: the same glyph resolved straight to target_px
        target = [1 - v for v in to_list(big.resize((target_px, target_px), Image.Resampling.BOX))]
        w0 = [1 - v for v in to_list(big.resize((BOX_W, BOX_H), Image.Resampling.BOX))]
        s = optimise(target, w0, iters, gain, target_px)

        before = sum((t - v) ** 2 for t, v in zip(target, down(w0, BOX_W, BOX_H, target_px, target_px)))
        after = sum((t - v) ** 2 for t, v in zip(target, down(s, BOX_W, BOX_H, target_px, target_px)))
        rms_before += before
        rms_after += after
        if after < before:
            improved += 1

        cell = Image.new('L', (48, 48), 255)
        ink = Image.new('L', (BOX_W, BOX_H))
        ink.putdata([round(255 * (1 - v)) for v in s])
        cell.paste(ink, (INK_BOX[0], INK_BOX[1]))
        idx = info['index']
        data[glyphoff + idx * blocksize: glyphoff + (idx + 1) * blocksize] = encode_image(cell)
        data[metaoff + idx * 2: metaoff + idx * 2 + 2] = bytes((0, 17))
    n = len(carrier_map)
    return bytes(data), {'glyphs': n, 'improved': improved,
                         'residual_before': round((rms_before / n) ** 0.5, 4),
                         'residual_after': round((rms_after / n) ** 0.5, 4),
                         'target_px': target_px, 'iters': iters, 'gain': gain,
                         'weight': weight, 'fitted_size': fitter.size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', default='gestalt')
    ap.add_argument('--font', type=Path, default=Path(r'C:\Windows\Fonts\NotoSansKR-VF.ttf'))
    ap.add_argument('--weight', type=int, default=700)
    ap.add_argument('--target-px', type=int, default=24)
    ap.add_argument('--iters', type=int, default=24)
    ap.add_argument('--gain', type=float, default=0.9)
    ap.add_argument('--out', type=Path, default=ROOT / 'runtime-test' / 'font-variants')
    a = ap.parse_args()

    work = ROOT / 'build' / a.build
    cmap = json.loads((work / 'carrier-map.json').read_text(encoding='utf-8'))
    fop, stats = build(cmap, a.font, a.weight, a.target_px, a.iters, a.gain)
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f'etc-en-sharp{a.target_px}.afs'
    src = AfsArchive(work / 'archives' / 'etc-en.afs')
    info = src.rebuild(out, replacements={0: encode_wrapped(fop)})
    if decode_wrapped(AfsArchive(out).raw(0)) != fop:
        raise ValueError('repacked font failed to decode back')
    print(json.dumps({**stats, 'out': out.name, 'sha256': info['sha256'][:16]},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
