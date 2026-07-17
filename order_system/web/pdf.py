from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter

from order_system.pdf_template_worker import _build_overlay
from order_system.web.settings import TEMPLATE_PATH


def render_order_pdf(record: dict) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"未找到 PDF 模板：{TEMPLATE_PATH}")
    template_reader = PdfReader(str(TEMPLATE_PATH))
    overlay_reader = PdfReader(BytesIO(_build_overlay(record)))
    page = template_reader.pages[0]
    page.merge_page(overlay_reader.pages[0])
    writer = PdfWriter()
    writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()

def merge_order_pdfs(records: list[dict]) -> bytes:
    writer = PdfWriter()
    for record in records:
        reader = PdfReader(BytesIO(render_order_pdf(record)))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
