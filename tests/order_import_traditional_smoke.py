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
        "materials": ["銅  烤漆"],
        "coloring": ["說明"],
        "global_note": "客戶備註",
    },
    catalogs,
)

assert normalized["product_name"] == "台湾铜牌"
assert "铜  烤漆" in normalized["materials"]
assert normalized["coloring"] == ["说明"]
assert normalized["global_note"] == "客户备注"
print("order import traditional smoke ok")
