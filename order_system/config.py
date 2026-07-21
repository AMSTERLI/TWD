import os
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("TWD_DATA_DIR", APP_ROOT)).resolve()
DATA_DIR = DATA_ROOT / "data"
IMAGES_DIR = DATA_ROOT / "images"
DB_PATH = DATA_DIR / "orders.db"
TMP_DIR = DATA_ROOT / "tmp"
OUTPUT_DIR = DATA_ROOT / "output"
OUTPUT_PDF_DIR = OUTPUT_DIR / "pdf"
PDF_TEMPLATE_PATH = APP_ROOT / "order_temp.pdf"
LOGIN_PASSWORD = "123456"
LOGIN_USERS = {
    "admin": "all",
    "yewu": "business",
    "caiwu": "finance",
    "waifa": "outsource",
    "chejian": "workshop",
}
BUNDLED_PYTHON_PATH = Path(
    r"C:\Users\LBL99\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

