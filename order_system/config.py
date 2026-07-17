from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
IMAGES_DIR = APP_ROOT / "images"
DB_PATH = DATA_DIR / "orders.db"
TMP_DIR = APP_ROOT / "tmp"
OUTPUT_DIR = APP_ROOT / "output"
OUTPUT_PDF_DIR = OUTPUT_DIR / "pdf"
PDF_TEMPLATE_PATH = APP_ROOT / "order_temp.pdf"
LOGIN_PASSWORD = "123456"
LOGIN_USERS = {
    "admin": "all",
    "yewu": "business",
    "caiwu": "finance",
    "waifa": "outsource",
}
BUNDLED_PYTHON_PATH = Path(
    r"C:\Users\LBL99\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
