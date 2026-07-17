import re
import shutil
from datetime import datetime
from pathlib import Path


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
    return cleaned or "order"


def copy_images(order_no: str, selected_paths: list[str], target_dir: Path) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    safe_order_no = sanitize_filename(order_no)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    for index, source in enumerate(selected_paths, start=1):
        source_path = Path(source)
        extension = source_path.suffix.lower() or ".jpg"
        filename = f"{safe_order_no}_{timestamp}_{index}{extension}"
        destination = target_dir / filename
        shutil.copy2(source_path, destination)
        saved_paths.append(destination.name)
    return saved_paths
