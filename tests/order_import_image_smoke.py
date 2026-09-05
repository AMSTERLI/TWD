from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

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
assert body["model"] == "qwen3.7-flash"
system_prompt = body["messages"][0]["content"]
assert "系统字段规则和允许值 > 业务员补充说明" in system_prompt
assert "行业常见表达和字段关系进行合理推测与补全" in system_prompt
assert "不推测、不补全" not in system_prompt
assert "待报价、未报价和空白均为null" in system_prompt
assert "\u6b63\u9762+\u4fa7\u9762+\u80cc\u9762\u5747\u7b49\u4ef7\u4e8e\u4e09\u9762" in system_prompt
assert "证章、襟章" in system_prompt and "三面抛" in system_prompt
assert "蝴夹、蝴蝶夹" in system_prompt and "不入色" in system_prompt
assert "一般/厚/薄最多选择一个" in system_prompt
content = body["messages"][1]["content"]
assert isinstance(content, list)
assert content[0]["type"] == "text"
assert "勾画" in content[0]["text"] and "高亮" in content[0]["text"] and "制作工艺" in content[0]["text"]
assert "颜色块" in content[0]["text"] and "空白的方框" in content[0]["text"]
assert "表格布局和上下文合理判断" in content[0]["text"] and "不加" in content[0]["text"]
assert "逐区检查每一个编号区域" in content[0]["text"]
assert "POLISH FRONT SIDE" in content[0]["text"] and "BACK OF PIN" in content[0]["text"]
assert "不要猜测" not in content[0]["text"]
assert content[1]["type"] == "image_url"
assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
assert content[1]["min_pixels"] == order_import.VISUAL_MIN_PIXELS
assert content[1]["max_pixels"] == order_import.VISUAL_MAX_PIXELS
assert result["product_name"] == "钥匙扣"

tall_image_path = root / "tall-order.png"
Image.new("RGB", (1_000, 1_400), "white").save(tall_image_path)
expanded = order_import._expanded_visual_images([tall_image_path], root / "sections")
assert expanded[0] == tall_image_path
assert len(expanded) == 3
with Image.open(expanded[1]) as top_section, Image.open(expanded[2]) as bottom_section:
    assert top_section.size == bottom_section.size == (1_000, 868)
print(f"order import image smoke ok: {root}")
