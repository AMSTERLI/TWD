from __future__ import annotations

import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import order_system.order_import as order_import  # noqa: E402


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01\xf6"
    b"\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


root = Path(tempfile.mkdtemp(prefix="twd-import-doc-"))
legacy_doc = root / "customer-order.doc"
legacy_doc.write_bytes(b"legacy-word-placeholder")

original_convert = order_import._convert_with_libreoffice
original_contains_images = order_import._docx_contains_images
original_extract_docx = order_import._extract_docx
original_render = order_import._render_doc_pages


def placeholder_docx(output_dir: Path) -> Path:
    target = output_dir / "customer-order.docx"
    target.write_bytes(b"docx-placeholder")
    return target


try:
    def fake_text_convert(source_path: Path, output_format: str, output_dir: Path) -> Path:
        assert source_path == legacy_doc
        assert output_format == "docx"
        return placeholder_docx(output_dir)

    order_import._convert_with_libreoffice = fake_text_convert
    order_import._extract_docx = lambda path: "产品：钥匙扣\n[表格1]\n数量 | 100"
    text_content = order_import._legacy_doc_user_content(legacy_doc, "数量以表格为准")
    assert isinstance(text_content, str)
    assert "产品：钥匙扣" in text_content
    assert "数量 | 100" in text_content
    assert "数量以表格为准" in text_content

    def fake_image_convert(source_path: Path, output_format: str, output_dir: Path) -> Path:
        assert output_format == "docx"
        return placeholder_docx(output_dir)

    def fake_render(source_path: Path, output_dir: Path) -> list[Path]:
        image_path = output_dir / "doc-page-1.png"
        image_path.write_bytes(PNG_BYTES)
        return [image_path]

    order_import._convert_with_libreoffice = fake_image_convert
    order_import._extract_docx = lambda path: ""
    order_import._docx_contains_images = lambda path: True
    order_import._render_doc_pages = fake_render
    visual_content = order_import._legacy_doc_user_content(legacy_doc, "")
    assert isinstance(visual_content, list)
    assert visual_content[0]["type"] == "text"
    assert visual_content[1]["type"] == "image_url"
    assert visual_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
finally:
    order_import._convert_with_libreoffice = original_convert
    order_import._docx_contains_images = original_contains_images
    order_import._extract_docx = original_extract_docx
    order_import._render_doc_pages = original_render

assert ".doc" in order_import.SUPPORTED_DOCUMENT_SUFFIXES

if shutil.which("libreoffice") and shutil.which("pdftoppm"):
    from docx import Document

    real_root = root / "real-conversion"
    real_root.mkdir()
    source_docx = real_root / "real-order.docx"
    source = Document()
    source.add_paragraph("产品：钥匙扣")
    table = source.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "数量"
    table.cell(0, 1).text = "100"
    source.save(source_docx)

    legacy_path = order_import._convert_with_libreoffice(source_docx, "doc", real_root / "to-doc")
    extracted = order_import.extract_document_text(legacy_path)
    assert "产品：钥匙扣" in extracted
    assert "数量" in extracted
    assert "100" in extracted

    page_paths = order_import._render_doc_pages(legacy_path, real_root / "rendered")
    assert page_paths and all(path.stat().st_size > 0 for path in page_paths)

print(f"order import doc smoke ok: {root}")
