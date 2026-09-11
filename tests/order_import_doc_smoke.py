from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

import order_system.order_import as order_import  # noqa: E402


root = Path(tempfile.mkdtemp(prefix="twd-import-doc-"))

spreadsheet_path = root / "structured-order.xlsx"
spreadsheet = Workbook()
sheet = spreadsheet.active
sheet.title = "Sheet1"
sheet.merge_cells("A1:H1")
sheet["A1"] = "测试订单"
sheet["A5"] = "产品品名"
sheet["C5"] = "描述"
sheet["A6"] = "证章"
sheet["C6"] = "低温锌合金，最大尺寸20mm，电镀镍，三面抛，不入色，配件蝴夹x1pc"
sheet["A11"] = "备注"
sheet["H11"] = "测试"
spreadsheet.save(spreadsheet_path)

text = order_import.extract_document_text(spreadsheet_path)
assert "测试订单" in text
assert "低温锌合金" in text
assert "配件蝴夹x1pc" in text

legacy_doc = root / "customer-order.doc"
legacy_doc.write_bytes(b"legacy-word-placeholder")
try:
    order_import.extract_document_text(legacy_doc)
except order_import.OrderImportError as exc:
    assert "暂不支持旧版 .doc 客单" in str(exc)
else:
    raise AssertionError(".doc uploads should not invoke LibreOffice conversion")

assert ".doc" not in order_import.SUPPORTED_DOCUMENT_SUFFIXES

original_urlopen = order_import.urllib.request.urlopen
original_render = order_import._render_layout_document_pages
captured_body: dict = {}


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {"choices": [{"message": {"content": json.dumps({"product_name": "AI test"})}}]},
            ensure_ascii=False,
        ).encode("utf-8")


def fake_urlopen(request, timeout=120):
    parsed = urlparse(request.full_url)
    assert parsed.path.endswith("/chat/completions")
    captured_body.update(json.loads(request.data.decode("utf-8")))
    return FakeResponse()


def fail_layout_render(*args, **kwargs):
    raise AssertionError("document AI import should use text extraction, not page rendering")


try:
    order_import.urllib.request.urlopen = fake_urlopen
    order_import._render_layout_document_pages = fail_layout_render
    order_import.analyze_order_document(
        spreadsheet_path,
        "test-api-key",
        {
            "order_type": [],
            "surface_crafts": [],
            "base_materials": [],
            "plating": [],
            "accessories": [],
            "polishing": [],
            "resin": [],
            "packaging": [],
            "coloring": [],
            "back_mode": [],
            "quantity_unit": [],
        },
        "仅识别第1款产品",
    )
finally:
    order_import.urllib.request.urlopen = original_urlopen
    order_import._render_layout_document_pages = original_render

user_content = captured_body["messages"][1]["content"]
assert isinstance(user_content, str)
assert "低温锌合金" in user_content
assert "仅识别第1款产品" in user_content

print(f"order import doc smoke ok: {root}")
