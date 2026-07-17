from __future__ import annotations

import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from order_system.database import dumps_json  # noqa: E402
from order_system.web.repository import Repository  # noqa: E402


db_path = Path(tempfile.mkdtemp(prefix="twd-concurrency-")) / "orders.db"
repo = Repository(db_path)
repo.initialize()


def create(index: int) -> str:
    payload = {column: None for column in __import__("order_system.web.repository", fromlist=["ORDER_COLUMNS"]).ORDER_COLUMNS}
    payload.update({
        "order_type": "新订单", "salesman": f"业务{index}", "product_name": "并发测试",
        "order_date": "2026-07-15", "quantity": 1, "quantity_unit": "个",
        "order_prefix_no": 1, "paid_status": 0, "size_as_sample": 0,
        "materials_json": dumps_json([]), "plating_json": dumps_json([]),
        "accessories_json": dumps_json([]), "polishing_json": dumps_json([]),
        "coloring_json": dumps_json([]), "resin_json": dumps_json([]),
        "packaging_json": dumps_json([]), "image_paths_json": dumps_json([]),
    })
    return repo.create_order(payload)[1]


with ThreadPoolExecutor(max_workers=12) as pool:
    numbers = list(pool.map(create, range(20)))

assert len(numbers) == len(set(numbers)) == 20
assert sorted(numbers)[0] == "TWD1-260715001"
assert sorted(numbers)[-1] == "TWD1-260715020"

with sqlite3.connect(db_path) as conn:
    indexes = conn.execute("PRAGMA index_list(orders)").fetchall()
    assert not any(row[1] == "idx_orders_order_no_unique" for row in indexes)
    conn.execute(
        "INSERT INTO orders (order_type, order_no, materials_json, plating_json, "
        "accessories_json, polishing_json, resin_json, packaging_json, image_paths_json) "
        "VALUES (?, ?, '[]', '[]', '[]', '[]', '[]', '[]', '[]')",
        ("新订单", numbers[0]),
    )
    duplicate_count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE order_no = ?", (numbers[0],)
    ).fetchone()[0]
    assert duplicate_count == 2

recycle_db_path = db_path.with_name("recycle.db")
recycle_repo = Repository(recycle_db_path)
recycle_repo.initialize()
failed_payload = {column: None for column in __import__("order_system.web.repository", fromlist=["ORDER_COLUMNS"]).ORDER_COLUMNS}
failed_payload.update({"order_date": "2026-07-16", "order_prefix_no": 1})
try:
    recycle_repo.create_order(failed_payload)
except sqlite3.IntegrityError:
    pass
else:
    raise AssertionError("invalid order unexpectedly saved")
valid_payload = failed_payload.copy()
valid_payload.update({"order_type": "新订单", "quantity_unit": "个"})
assert recycle_repo.create_order(valid_payload)[1] == "TWD1-260716001"

print("concurrency smoke ok: automatic numbers unique, manual duplicates allowed, unused number recycled")


