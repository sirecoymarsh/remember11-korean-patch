#!/usr/bin/env python3
"""Repackage the two release folders and refresh their .sha256 sidecars."""
from __future__ import annotations
import hashlib, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'release'
NAMES = sys.argv[1:] or ['Remember11-Korean', 'Remember11-Korean-Gestalt']

for name in NAMES:
    src = ROOT / name
    dst = ROOT / f'{name}.zip'
    tmp = ROOT / f'{name}.zip.new'
    files = sorted(p for p in src.rglob('*') if p.is_file())
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for p in files:
            z.write(p, f'{name}/{p.relative_to(src).as_posix()}')
    h = hashlib.sha256()
    with tmp.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    tmp.replace(dst)
    (ROOT / f'{name}.zip.sha256').write_text(f'{h.hexdigest()}  {name}.zip\n', encoding='utf-8')
    print(f'{name}.zip  {dst.stat().st_size} bytes  sha256={h.hexdigest()}', flush=True)
