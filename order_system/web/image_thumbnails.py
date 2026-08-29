from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps


THUMBNAIL_SIZE = (72, 54)
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def thumbnail_path(image_path: Path, thumbnail_dir: Path) -> Path:
    return thumbnail_dir / f"{image_path.name}.thumb.jpg"


def cached_thumbnail_path(image_path: Path, thumbnail_dir: Path) -> Path | None:
    target = thumbnail_path(image_path, thumbnail_dir)
    if not target.is_file() or target.stat().st_size <= 0:
        return None
    if target.stat().st_mtime < image_path.stat().st_mtime:
        return None
    return target


def create_image_thumbnail(image_path: Path, thumbnail_dir: Path) -> Path | None:
    if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return None
    cached = cached_thumbnail_path(image_path, thumbnail_dir)
    if cached:
        return cached
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    target = thumbnail_path(image_path, thumbnail_dir)
    temporary = thumbnail_dir / f".{target.name}.{uuid4().hex}.tmp"
    try:
        with Image.open(image_path) as source:
            if source.format == "JPEG":
                source.draft("RGB", THUMBNAIL_SIZE)
            image = ImageOps.exif_transpose(source)
            image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS, reducing_gap=3.0)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")
            image.save(temporary, format="JPEG", quality=78, optimize=True)
        os.replace(temporary, target)
        return target
    except (OSError, ValueError):
        temporary.unlink(missing_ok=True)
        return None


def remove_image_thumbnail(image_path: Path, thumbnail_dir: Path) -> None:
    thumbnail_path(image_path, thumbnail_dir).unlink(missing_ok=True)


def order_image_names(db_path: Path) -> set[str]:
    names: set[str] = set()
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT image_paths_json FROM orders").fetchall()
    for (raw_value,) in rows:
        try:
            values = json.loads(raw_value or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        for value in values if isinstance(values, list) else []:
            name = Path(str(value or "")).name
            if name and name == str(value) and Path(name).suffix.lower() in SUPPORTED_SUFFIXES:
                names.add(name)
    return names


def backfill_order_thumbnails(db_path: Path, images_dir: Path, thumbnail_dir: Path) -> dict[str, int]:
    names = order_image_names(db_path)
    stats = {"referenced": len(names), "created": 0, "existing": 0, "missing": 0, "failed": 0}
    for name in sorted(names):
        image_path = images_dir / name
        if not image_path.is_file():
            stats["missing"] += 1
            continue
        if cached_thumbnail_path(image_path, thumbnail_dir):
            stats["existing"] += 1
            continue
        if create_image_thumbnail(image_path, thumbnail_dir):
            stats["created"] += 1
        else:
            stats["failed"] += 1
    return stats


def main() -> None:
    from .settings import DB_PATH, IMAGES_DIR, THUMBNAILS_DIR, ensure_directories

    parser = argparse.ArgumentParser(description="Backfill cached thumbnails for existing order images.")
    parser.parse_args()
    ensure_directories()
    print(json.dumps(backfill_order_thumbnails(DB_PATH, IMAGES_DIR, THUMBNAILS_DIR), sort_keys=True))


if __name__ == "__main__":
    main()
