from __future__ import annotations

import os
import secrets
from pathlib import Path

from order_system.config import APP_ROOT


DATA_ROOT = Path(os.environ.get("TWD_DATA_DIR", APP_ROOT)).resolve()
DATA_DIR = DATA_ROOT / "data"
DB_PATH = DATA_DIR / "orders.db"
IMAGES_DIR = DATA_ROOT / "images"
TMP_DIR = DATA_ROOT / "tmp" / "web"
OUTPUT_DIR = DATA_ROOT / "output" / "pdf"
TEMPLATE_PATH = APP_ROOT / "order_temp.pdf"
WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_ROOT / "templates"
STATIC_DIR = WEB_ROOT / "static"
MAX_UPLOAD_BYTES = int(os.environ.get("TWD_MAX_UPLOAD_MB", "10")) * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
SESSION_HTTPS_ONLY = os.environ.get("TWD_COOKIE_HTTPS_ONLY", "0") == "1"


def ensure_directories() -> None:
    for path in (DATA_DIR, IMAGES_DIR, TMP_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def session_secret() -> str:
    configured = os.environ.get("TWD_SESSION_SECRET", "").strip()
    if configured:
        return configured
    ensure_directories()
    secret_path = DATA_DIR / ".session_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    secret_path.write_text(value, encoding="utf-8")
    return value

