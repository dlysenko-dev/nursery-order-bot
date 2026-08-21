"""Подготовка фото товаров и обложек для веба (Mini App / сайт).

Исходники — из папки ../цветы/ (тот же маппинг файл -> photo_number,
что в scripts/seed_catalog.py: sorted() по имени файла).

Результат:
- web/static/photos/<slug>_<photo_number>.jpg       — полная версия (max 1280px)
- web/static/photos/thumbs/<slug>_<photo_number>.jpg — превью для сетки (max 480px)
- web/static/covers/                                 — копия media/covers

Идемпотентно: уже готовые файлы пропускаются.
Запуск из корня проекта: venv/Scripts/python scripts/prepare_web_photos.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys

from PIL import Image

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FLOWERS_DIR = PROJECT_ROOT.parent / "цветы"
STATIC_DIR = PROJECT_ROOT / "web" / "static"
PHOTOS_DIR = STATIC_DIR / "photos"
THUMBS_DIR = PHOTOS_DIR / "thumbs"
COVERS_SRC = PROJECT_ROOT / "media" / "covers"
COVERS_DIR = STATIC_DIR / "covers"

FOLDER_TO_SLUG = {
    "пионы": "pion",
    "лилии": "lily",
    "флоксы": "phlox",
    "хосты": "hosta",
    "гортензия_метельчатая": "hydrangea",
    "хризантемы": "chrysanthemum",
    "лук_декоративный": "allium",
}

FULL_MAX = 1280
THUMB_MAX = 480
QUALITY = 82


def save_resized(src: pathlib.Path, dst: pathlib.Path, max_side: int) -> None:
    if dst.exists():
        return
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)


def main() -> None:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)

    done = skipped = 0
    for folder, slug in FOLDER_TO_SLUG.items():
        folder_path = FLOWERS_DIR / folder
        if not folder_path.is_dir():
            print(f"!! {folder}: папка не найдена, пропуск")
            continue
        photos = sorted(p for p in folder_path.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        for i, photo_path in enumerate(photos, start=1):
            full_dst = PHOTOS_DIR / f"{slug}_{i}.jpg"
            thumb_dst = THUMBS_DIR / f"{slug}_{i}.jpg"
            if full_dst.exists() and thumb_dst.exists():
                skipped += 1
                continue
            save_resized(photo_path, full_dst, FULL_MAX)
            save_resized(photo_path, thumb_dst, THUMB_MAX)
            done += 1
        print(f"== {slug}: {len(photos)} фото обработано")

    covers = 0
    if COVERS_SRC.is_dir():
        for cover in COVERS_SRC.iterdir():
            if cover.is_file() and cover.suffix.lower() in (".jpg", ".jpeg", ".png"):
                dst = COVERS_DIR / cover.name
                if not dst.exists():
                    shutil.copy2(cover, dst)
                    covers += 1
    print(f"\nГотово: {done} фото создано, {skipped} пропущено, {covers} обложек скопировано")
    print(f"Каталог: {STATIC_DIR}")


if __name__ == "__main__":
    main()
