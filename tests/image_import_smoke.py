
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from order_system.order_import import analyze_order_document  # noqa: E402
import order_system.order_import as order_import  # noqa: E402

root = Path(tempfile.mkdtemp(prefix="twd-image-import-"))
image_path = root / "order.png"
image_path.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"))

captured = {}

class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return json.dumps({"choices": [{"message": {"content": json.dumps({"product_name": "keychain", "quantity": 12})}}]}).encode("utf-8")


def fake_urlopen(request, timeout=0):
    captured["timeout"] = timeout
    captured["body"] = json.loads(request.data.decode("utf-8"))
    return FakeResponse()

original = order_import.urllib.request.urlopen
order_import.urllib.request.urlopen = fake_urlopen
try:
    result = analyze_order_document(image_path, "api-key", {"quantity_unit": ["个", "套"]})
finally:
    order_import.urllib.request.urlopen = original

message_content = captured["body"]["messages"][1]["content"]
assert isinstance(message_content, list)
assert message_content[0]["type"] == "text"
assert message_content[1]["type"] == "image_url"
assert message_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
assert result["quantity"] == 12
print(f"image import smoke ok: {root}")
