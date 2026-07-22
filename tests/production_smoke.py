from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-production-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "test-secret-that-is-long-enough-for-smoke-test"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.database import dumps_json  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402
from order_system.web.repository import ORDER_COLUMNS  # noqa: E402


def csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def login(client: TestClient, username: str, password: str) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={"csrf": csrf(page.text), "username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def logout(client: TestClient) -> None:
    page = client.get("/orders")
    client.post("/logout", data={"csrf": csrf(page.text)}, follow_redirects=False)


def payload(order_no: str, salesman: str, product_name: str) -> dict[str, object]:
    data = {column: None for column in ORDER_COLUMNS}
    data.update({
        "order_type": "\u65b0\u8ba2\u5355",
        "salesman": salesman,
        "order_no": order_no,
        "product_name": product_name,
        "order_date": "2026-07-20",
        "delivery_date": "2026-07-30",
        "quantity": 300,
        "spare_quantity": 15,
        "quantity_unit": "\u4e2a",
        "unit_price": 2.5,
        "extra_fee": 8,
        "order_prefix_no": 1,
        "paid_status": 1,
        "shipped_status": 1,
        "invoice_status": 1,
        "bi_no": f"PO-{order_no[-3:]}",
        "production_no": f"SC-{order_no[-3:]}",
        "width_mm": "42",
        "height_mm": "35",
        "thickness_mm": "2",
        "size_as_sample": 0,
        "materials_json": dumps_json(["\u94dc  \u70e4\u6f06"]),
        "plating_json": dumps_json([]),
        "accessories_json": dumps_json([]),
        "polishing_json": dumps_json([]),
        "coloring_json": dumps_json([]),
        "resin_json": dumps_json([]),
        "packaging_json": dumps_json([]),
        "image_paths_json": dumps_json([]),
    })
    return data


with TestClient(app) as client:
    repo.create_user("admin", "admin-pass-123", "admin", display_name="\u7ba1\u7406\u5458")
    repo.create_user("shengguan", "prod-pass-123", "production", display_name="\u9ec4\u519b\u56fd")
    first_id, first_no = repo.create_order(payload("TWD1-260720901", "\u6768\u5a1f", "\u53cc\u9762\u5e01"))
    second_id, second_no = repo.create_order(payload("TWD1-260720902", "\u5ed6\u6625\u51e4", "\u94a5\u5319\u6263"))

    login(client, "shengguan", "prod-pass-123")
    page = client.get("/production")
    assert page.status_code == 200
    assert first_no in page.text and second_no in page.text
    assert "\u751f\u7ba1\u8ba2\u5355" in page.text
    assert f'data-replenishment-url="/orders/{first_id}/replenishment-request"' in page.text
    assert 'data-inline-replenish' in page.text
    assert 'data-edit-url=' not in page.text and 'data-delete-url=' not in page.text
    searched = client.get("/production?q=PO-901")
    assert searched.status_code == 200 and first_no in searched.text and second_no not in searched.text
    request = client.post(
        f"/orders/{first_id}/replenishment-request",
        data={"csrf": csrf(page.text), "quantity": "25", "reason": "\u5ba2\u6237\u8981\u6c42\u8865\u53d1"},
        follow_redirects=False,
    )
    assert request.status_code == 303
    prod_messages = client.get("/messages")
    assert prod_messages.status_code == 200
    assert "\u8865\u6570\u7533\u8bf7" in prod_messages.text and "\u9ec4\u519b\u56fd" in prod_messages.text
    logout(client)

    login(client, "admin", "admin-pass-123")
    messages = client.get("/messages")
    assert messages.status_code == 200
    assert "\u8865\u6570\u7533\u8bf7" in messages.text and "\u5ba2\u6237\u8981\u6c42\u8865\u53d1" in messages.text
    review = client.post(
        "/messages/1/review",
        data={"csrf": csrf(messages.text), "decision": "approve", "review_note": "\u540c\u610f"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    approved = repo.list_edit_requests("approved")[0]
    new_order = repo.get_order(int(approved["created_order_id"]))
    original = repo.get_order(first_id)
    assert new_order["order_no"] == original["order_no"]
    assert new_order["order_type"] == "\u8865\u6570\u5355\uff08\u9ec4\u519b\u56fd\uff09"
    assert new_order["quantity"] == 25 and new_order["spare_quantity"] == 0
    assert new_order["global_note"] == "\u8865\u6570\u539f\u56e0\uff1a\u5ba2\u6237\u8981\u6c42\u8865\u53d1"
    assert new_order["customer_name"] == original["customer_name"]
    assert new_order["width_mm"] == original["width_mm"]
    assert new_order["paid_status"] == 0 and new_order["shipped_status"] == 0 and new_order["invoice_status"] == 0
    detail = client.get(f"/orders/{new_order['id']}")
    assert detail.status_code == 200 and "red-note" in detail.text
    logout(client)

    login(client, "shengguan", "prod-pass-123")
    approved_page = client.get("/messages?status=approved")
    assert approved_page.status_code == 200
    assert "\u7ba1\u7406\u5458" in approved_page.text and "\u67e5\u770b\u8865\u6570\u5355" in approved_page.text

print(f"production smoke ok: {root}")
