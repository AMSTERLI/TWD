import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from order_system.config import (
    APP_ROOT,
    BUNDLED_PYTHON_PATH,
    OUTPUT_PDF_DIR,
    PDF_TEMPLATE_PATH,
    TMP_DIR,
)


class OrderPreviewError(RuntimeError):
    """Raised when the filled PDF preview cannot be generated."""


@dataclass
class PreviewArtifacts:
    pdf_path: Path
    page_images: list[Path]


def generate_order_preview_artifacts(record: dict) -> PreviewArtifacts:
    if not PDF_TEMPLATE_PATH.exists():
        raise OrderPreviewError(f"未找到 PDF 模板：{PDF_TEMPLATE_PATH}")

    OUTPUT_PDF_DIR.mkdir(parents=True, exist_ok=True)
    preview_dir = TMP_DIR / "pdf_preview" / f"order_{record.get('id', 'temp')}"
    preview_dir.mkdir(parents=True, exist_ok=True)

    for image_path in preview_dir.glob("page-*.png"):
        image_path.unlink()

    record_json_path = preview_dir / "record.json"
    record_json_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    pdf_filename = f"{_safe_name(record.get('order_no') or 'order')}_{record.get('id', 'preview')}.pdf"
    pdf_path = OUTPUT_PDF_DIR / pdf_filename

    _run_subprocess(
        [
            str(_python_executable()),
            "-m",
            "order_system.pdf_template_worker",
            str(record_json_path),
            str(PDF_TEMPLATE_PATH),
            str(pdf_path),
        ]
    )

    prefix = preview_dir / "page"
    _run_subprocess(["pdftoppm", "-png", str(pdf_path), str(prefix)])

    page_images = sorted(preview_dir.glob("page-*.png"))
    if not page_images:
        raise OrderPreviewError("PDF 已生成，但未能渲染出预览图片。")

    return PreviewArtifacts(pdf_path=pdf_path, page_images=page_images)


def _python_executable() -> Path:
    if BUNDLED_PYTHON_PATH.exists():
        return BUNDLED_PYTHON_PATH
    return Path(sys.executable)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
    return cleaned or "order"


def _run_subprocess(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=APP_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise OrderPreviewError(stderr or f"命令执行失败：{' '.join(command)}")
