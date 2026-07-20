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


def create_payload(order_no: str, salesman: str, product_name: str, delivery_date: str = "2026-07-20") -> dict[str, object]:
    payload = {column: None for column in ORDER_COLUMNS}
    payload.update({
        "order_type": "新订单",
        "salesman": salesman,
        "order_no": order_no,
        "product_name": product_name,
        "order_date": "2026-07-17",
        "delivery_date": delivery_date,
        "quantity": 1,
        "spare_quantity": 5,
        "quantity_unit": "个",
        "order_prefix_no": 1,
        "paid_status": 0,
        "shipped_status": 0,
        "bi_no": f"PO-{order_no[-3:]}",
        "production_no": f"SC-{order_no[-3:]}",
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
    own_id, own_no = repo.create_order(create_payload("TWD1-260717901", "杨娟", "杨娟订单", "2026-07-20"))
    other_id, other_no = repo.create_order(create_payload("TWD1-260717902", "廖春凤", "廖春凤订单", "2026-07-25"))
    later_id, later_no = repo.create_order(create_payload("TWD1-260717903", "杨娟", "杨娟晚交期订单", "2026-08-20"))

    login(client, "yangjuan", "sales-pass-123")
    new_page = client.get("/orders/new")
    assert new_page.status_code == 200
    assert 'name="salesman" value="杨娟"' in new_page.text
    assert "readonly" in new_page.text

    orders = client.get("/orders")
    assert orders.status_code == 200
    assert own_no in orders.text and later_no in orders.text
    assert orders.text.index(later_no) < orders.text.index(own_no)
    assert other_no not in orders.text
    assert "PO号" in orders.text and "PO-901" in orders.text
    assert "杨娟订单" not in orders.text and "业务员" not in orders.text
    assert "1+5" in orders.text and "待出货" in orders.text
    assert f'data-ship-url="/orders/{own_id}/ship"' in orders.text
    searched = client.get("/orders?q=PO-901")
    assert searched.status_code == 200 and own_no in searched.text
    searched = client.get("/orders?q=SC-901")
    assert searched.status_code == 200 and own_no in searched.text
    searched = client.get(f"/orders?q={other_no}")
    assert searched.status_code == 200
    assert f'/orders/{other_id}' not in searched.text
    detail = client.get(f"/orders/{own_id}")
    assert detail.status_code == 200 and "出货状态" in detail.text and "待出货" in detail.text
    assert client.get(f"/orders/{other_id}").status_code == 403
    assert client.get(f"/orders/{other_id}/pdf").status_code == 403

    shipped = client.post(
        f"/orders/{own_id}/ship",
        data={"csrf": csrf(orders.text), "shipped": "1"},
        follow_redirects=False,
    )
    assert shipped.status_code == 303
    assert repo.get_order(own_id)["shipped_status"] == 1
    shipped_orders = client.get("/orders")
    assert "已出货" in shipped_orders.text and 'data-shipped="1"' in shipped_orders.text
    denied_ship = client.post(
        f"/orders/{other_id}/ship",
        data={"csrf": csrf(shipped_orders.text), "shipped": "1"},
        follow_redirects=False,
    )
    assert denied_ship.status_code == 403
    unshipped = client.post(
        f"/orders/{own_id}/ship",
        data={"csrf": csrf(shipped_orders.text), "shipped": "0"},
        follow_redirects=False,
    )
    assert unshipped.status_code == 303
    assert repo.get_order(own_id)["shipped_status"] == 0
    orders = client.get("/orders")

    assert f'data-request-edit-url="/orders/{own_id}/edit"' in orders.text
    assert client.get(f"/orders/{other_id}/edit").status_code == 403
    edit_page = client.get(f"/orders/{own_id}/edit")
    assert edit_page.status_code == 200
    assert "提交订单修改申请" in edit_page.text and "提交审批" in edit_page.text
    own_request = client.post(
        f"/orders/{own_id}/edit",
        data={
            "csrf": csrf(edit_page.text),
            "order_type": "新订单",
            "salesman": "廖春凤",
            "order_no": own_no,
            "product_name": "杨娟订单已改",
            "order_date": "2026-07-17",
            "delivery_date": "2026-07-20",
            "quantity": "50",
            "spare_quantity": "5",
            "quantity_unit": "个",
            "unit_price": "0",
            "extra_fee": "0",
            "order_prefix_no": "1",
            "bi_no": "PO-901",
            "production_no": "SC-901",
        },
        follow_redirects=False,
    )
    assert own_request.status_code == 303
    assert own_request.headers["location"] == "/messages"
    unchanged = repo.get_order(own_id)
    assert unchanged["quantity"] == 1 and unchanged["product_name"] == "杨娟订单"
    logout(client)

    login(client, "admin", "admin-pass-123")
    messages = client.get("/messages")
    assert messages.status_code == 200
    assert "杨娟" in messages.text
    assert "数量从1修改为50" in messages.text
    assert "品名从杨娟订单修改为杨娟订单已改" in messages.text
    review = client.post(
        "/messages/1/review",
        data={"csrf": csrf(messages.text), "decision": "approve", "review_note": "同意"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    updated = repo.get_order(own_id)
    assert updated["quantity"] == 50 and updated["product_name"] == "杨娟订单已改"
    assert updated["salesman"] == "杨娟"
    logout(client)

    login(client, "yangjuan", "sales-pass-123")
    messages = client.get("/messages?status=approved")
    assert messages.status_code == 200
    assert "管理员" in messages.text
    assert "同意" in messages.text
    assert f"/orders/{own_id}" in messages.text

print(f"sales access smoke ok: {root}")
