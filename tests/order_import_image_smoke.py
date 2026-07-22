from __future__ import annotations

import json
import sys
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

captured: dict[str, object] = {}


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": json.dumps({
                "product_name": "钥匙扣",
                "quantity": 100,
                "quantity_unit": "个",
                "materials": [],
                "plating": [],
                "accessories": [],
                "polishing": [],
                "coloring": [],
                "resin": [],
                "packaging": [],
            }, ensure_ascii=False)}}]
        }, ensure_ascii=False).encode("utf-8")


def fake_urlopen(request, timeout=0):
    captured["url"] = request.full_url
    captured["headers"] = dict(request.header_items())
    captured["body"] = json.loads(request.data.decode("utf-8"))
    captured["timeout"] = timeout
    return FakeResponse()


root = Path(tempfile.mkdtemp(prefix="twd-import-image-"))
image_path = root / "order.png"
image_path.write_bytes(PNG_BYTES)
original_urlopen = order_import.urllib.request.urlopen
order_import.urllib.request.urlopen = fake_urlopen
try:
    result = order_import.analyze_order_document(
        image_path,
        "test-key",
        {
            "order_type": ["新订单"],
            "quantity_unit": ["个", "套"],
            "back_mode": [],
            "materials": [],
            "plating": [],
            "accessories": [],
            "polishing": [],
            "coloring": [],
            "resin": [],
            "packaging": [],
            "surface_crafts": [],
        },
        "",
    )
finally:
    order_import.urllib.request.urlopen = original_urlopen

body = captured["body"]
assert body["model"] == "qwen3.7-plus"
content = body["messages"][1]["content"]
assert isinstance(content, list)
assert content[0]["type"] == "text"
assert "勾画" in content[0]["text"] and "高亮" in content[0]["text"] and "制作工艺" in content[0]["text"]
assert "颜色块" in content[0]["text"] and "空白的方框" in content[0]["text"]
assert "锌合金铸造烤漆" in content[0]["text"] and "锌合金  烤漆" in content[0]["text"]
assert content[1]["type"] == "image_url"
assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
assert result["product_name"] == "钥匙扣"
print(f"order import image smoke ok: {root}")
