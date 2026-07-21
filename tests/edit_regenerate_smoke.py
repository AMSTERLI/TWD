
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

root = Path(tempfile.mkdtemp(prefix="twd-edit-regenerate-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "edit-regenerate-secret-long-enough"

from order_system.web.app import repo
from order_system.web.repository import ORDER_COLUMNS

repo.initialize()
admin_id = repo.create_user("admin", "admin-password", "admin", display_name="Admin")
finance_id = repo.create_user("finance", "finance-password", "finance", display_name="Finance")
admin = repo.get_user(admin_id)
finance = repo.get_user(finance_id)


def base_payload(order_no: str, user_id: int, product: str) -> dict:
    payload = {column: None for column in ORDER_COLUMNS}
    payload.update({
        "order_type": "\u65b0\u8ba2\u5355",
        "salesman": "Tester",
        "order_no": order_no,
        "product_name": product,
        "order_date": "2026-07-21",
        "delivery_date": "2026-07-30",
        "quantity": 10,
        "spare_quantity": 0,
        "quantity_unit": "\u4e2a",
        "unit_price": 1.0,
        "extra_fee": 0,
        "paid_status": 0,
        "shipped_status": 0,
        "invoice_status": 0,
        "order_prefix_no": 1,
        "customer_code": 1,
        "width_mm": 10,
        "height_mm": 10,
        "thickness_mm": 1,
        "size_as_sample": 0,
        "materials_json": "[]",
        "plating_json": "[]",
        "accessories_json": "[]",
        "polishing_json": "[]",
        "coloring_json": "[]",
        "resin_json": "[]",
        "packaging_json": "[]",
        "image_paths_json": "[]",
        "component_parts_json": "[]",
        "_reservation_user_id": user_id,
    })
    return payload

first_no = repo.reserve_order_no("2026-07-21", 1, admin_id)
order_id, _ = repo.create_order(base_payload(first_no, admin_id, "original"))
existing = repo.get_order(order_id)
existing["product_name"] = "same-number-edit"
assert repo.update_order(order_id, existing, admin_id)
assert repo.get_order(order_id)["order_no"] == first_no

new_no = repo.reserve_order_no("2026-07-21", 1, admin_id)
admin_payload = repo.get_order(order_id)
admin_payload["order_no"] = new_no
admin_payload["product_name"] = "admin-regenerated"
assert repo.update_order(order_id, admin_payload, admin_id)
assert repo.get_order(order_id)["order_no"] == new_no

finance_order_no = repo.reserve_order_no("2026-07-21", 1, admin_id)
finance_order_id, _ = repo.create_order(base_payload(finance_order_no, admin_id, "finance-original"))
proposed_no = repo.reserve_order_no("2026-07-21", 1, finance_id)
proposal = repo.get_order(finance_order_id)
proposal["order_no"] = proposed_no
proposal["quantity"] = 12
request_id = repo.create_proposed_edit_request(finance_order_id, finance, proposal, "regenerate order number")
repo.review_edit_request(request_id, admin, True, "approved")
assert repo.get_order(finance_order_id)["order_no"] == proposed_no
assert repo.get_order(finance_order_id)["quantity"] == 12

with sqlite3.connect(repo.db_path) as conn:
    used = conn.execute(
        "SELECT used_order_id, used_at FROM order_no_reservations WHERE order_no = ?",
        (proposed_no,),
    ).fetchone()
assert used[0] == finance_order_id and used[1]
print(f"edit regenerate smoke ok: {root}")
