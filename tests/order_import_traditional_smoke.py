from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from order_system.order_import import normalize_order_data  # noqa: E402
from order_system.web.catalogs import import_catalogs  # noqa: E402

catalogs = import_catalogs()
normalized = normalize_order_data(
    {
        "product_name": "臺灣銅牌",
        "materials": ["銅"],
        "coloring": ["說明", "UV"],
        "accessories": ["安全別針"],
        "accessories_note": "配件要求：掛繩",
        "packaging_note": "OPP袋",
        "global_note": "客戶備註",
    },
    catalogs,
)

assert normalized["product_name"] == "牌"
assert "铜  UV" in normalized["materials"]
assert normalized["coloring"] == ["说明"]
assert normalized["accessories"] == []
assert not normalized.get("resin")
assert "OPP袋" in normalized["packaging_note"]
assert "配件：" in normalized["packaging_note"]
assert "挂绳" in normalized["packaging_note"]
assert normalized["global_note"] == "客户备注"

category_normalized = normalize_order_data({"product_name": "台湾纪念双面币金属礼品"}, catalogs)
assert category_normalized["product_name"] == "双面币"
category_fallback = normalize_order_data({"product_name": "台湾铜牌纪念礼品定制"}, catalogs)
assert category_fallback["product_name"] == "牌"
print("order import traditional smoke ok")
