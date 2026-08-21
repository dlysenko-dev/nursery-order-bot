"""Сборка коллажа для экрана «Каталог растений» из обложек категорий.

Сетка 4×2 (ландшафт, удобно в чате): 7 обложек категорий + приветственная.
Результат: media/covers/catalog.jpg
Запуск из корня проекта: venv/Scripts/python scripts/build_catalog_collage.py
"""
from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

COVERS = PROJECT_ROOT / "media" / "covers"
CELL_W, CELL_H = 600, 900
COLS, ROWS = 4, 2

# Только 7 категорий каталога, ничего лишнего
ORDER = ["pion", "lily", "phlox", "hosta", "hydrangea", "chrysanthemum", "allium"]


def main() -> None:
    collage = Image.new("RGB", (CELL_W * COLS, CELL_H * ROWS), "#0E1F14")
    paths = [COVERS / f"{name}.jpg" for name in ORDER]
    for idx, path in enumerate(paths):
        img = Image.open(path).convert("RGB")
        # cover-фит: заполнить ячейку без искажения пропорций
        scale = max(CELL_W / img.width, CELL_H / img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        left = (img.width - CELL_W) // 2
        top = (img.height - CELL_H) // 2
        img = img.crop((left, top, left + CELL_W, top + CELL_H))
        x = (idx % COLS) * CELL_W
        y = (idx // COLS) * CELL_H
        collage.paste(img, (x, y))
    out = COVERS / "catalog.jpg"
    collage.save(out, quality=88)
    print(f"OK: {out} ({collage.width}x{collage.height}, {out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
