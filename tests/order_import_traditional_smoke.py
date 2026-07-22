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
        "accessories": ["安全別針", "寶石", "蝴蝶帽"],
        "accessories_note": "配件要求：焊針；電話：123456；地址：台北市",
        "packaging_note": "OPP袋；客户公司：ABC",
        "global_note": "客戶備註；电话：123",
    },
    catalogs,
)

assert normalized["product_name"] == "牌"
assert "铜  UV印刷" in normalized["materials"]
assert normalized["coloring"] == ["说明"]
assert "安全别针" in normalized["accessories"]
assert "宝石" in normalized["accessories"]
assert "焊针" in normalized["accessories"]
assert "蝴蝶帽" in normalized["packaging"]
assert not normalized.get("resin")
assert "电话" not in normalized.get("accessories_note", "")
assert "地址" not in normalized.get("accessories_note", "")
assert "客户公司" not in normalized.get("packaging_note", "")
assert normalized["global_note"] == "客户备注"

category_normalized = normalize_order_data({"product_name": "台湾纪念双面币金属礼品"}, catalogs)
assert category_normalized["product_name"] == "双面币"
category_fallback = normalize_order_data({"product_name": "台湾铜牌纪念礼品定制"}, catalogs)
assert category_fallback["product_name"] == "牌"

exclusive_normalized = normalize_order_data(
    {
        "polishing": ["正面", "侧面", "背面", "喷砂"],
        "resin": ["厚", "薄", "单面", "双面"],
    },
    catalogs,
)
assert exclusive_normalized["polishing"] == ["三面", "喷砂"]
assert exclusive_normalized["resin"] == []
assert "互斥树脂选项" in exclusive_normalized["resin_note"]
print("order import traditional smoke ok")
