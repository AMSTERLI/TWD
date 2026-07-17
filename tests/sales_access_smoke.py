from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-sales-access-"))
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


def create_payload(order_no: str, salesman: str, product_name: str) -> dict[str, object]:
    payload = {column: None for column in ORDER_COLUMNS}
    payload.update({
        "order_type": "新订单",
        "salesman": salesman,
        "order_no": order_no,
        "product_name": product_name,
        "order_date": "2026-07-17",
        "quantity": 1,
        "quantity_unit": "个",
        "order_prefix_no": 1,
        "paid_status": 0,
        "size_as_sample": 0,
        "materials_json": dumps_json([]),
        "plating_json": dumps_json([]),
        "accessories_json": dumps_json([]),
        "polishing_json": dumps_json([]),
        "coloring_json": dumps_json([]),
        "resin_json": dumps_json([]),
        "packaging_json": dumps_json([]),
        "image_paths_json": dumps_json([]),
    })
    return payload


with TestClient(app) as client:
    repo.create_user("admin", "admin-pass-123", "admin", display_name="管理员")
    repo.create_user("yangjuan", "sales-pass-123", "sales", display_name="杨娟")
    repo.create_user("liaochunfeng", "sales-pass-456", "sales", display_name="廖春凤")
    own_id, own_no = repo.create_order(create_payload("TWD1-260717901", "杨娟", "杨娟订单"))
    other_id, other_no = repo.create_order(create_payload("TWD1-260717902", "廖春凤", "廖春凤订单"))

    login(client, "yangjuan", "sales-pass-123")
    new_page = client.get("/orders/new")
    assert new_page.status_code == 200
    assert 'name="salesman" value="杨娟"' in new_page.text
    assert "readonly" in new_page.text

    orders = client.get("/orders")
    assert orders.status_code == 200
    assert own_no in orders.text
    assert other_no not in orders.text
    searched = client.get(f"/orders?q={other_no}")
    assert searched.status_code == 200
    assert "?????" not in searched.text
    assert client.get(f"/orders/{own_id}").status_code == 200
    assert client.get(f"/orders/{other_id}").status_code == 403
    assert client.get(f"/orders/{other_id}/pdf").status_code == 403

    denied_request = client.post(
        f"/orders/{other_id}/edit-request",
        data={"csrf": csrf(orders.text), "reason": "想改别人的订单"},
        follow_redirects=False,
    )
    assert denied_request.status_code == 400
    own_request = client.post(
        f"/orders/{own_id}/edit-request",
        data={"csrf": csrf(orders.text), "reason": "补充说明"},
        follow_redirects=False,
    )
    assert own_request.status_code == 303
    logout(client)

    login(client, "admin", "admin-pass-123")
    messages = client.get("/messages")
    assert messages.status_code == 200
    assert "杨娟" in messages.text
    review = client.post(
        "/messages/1/review",
        data={"csrf": csrf(messages.text), "decision": "approve", "review_note": "同意"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    logout(client)

    login(client, "yangjuan", "sales-pass-123")
    messages = client.get("/messages?status=approved")
    assert messages.status_code == 200
    assert "管理员" in messages.text
    assert "同意" in messages.text

print(f"sales access smoke ok: {root}")
