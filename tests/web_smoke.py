from __future__ import annotations

import os
import re
import tempfile
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-web-test-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "test-secret-that-is-long-enough-for-smoke-test"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402


def csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


with TestClient(app) as client:
    assert client.get("/health").status_code == 200
    repo.create_user("admin", "test-password", "admin")
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={"csrf": csrf(login_page.text), "username": "admin", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    form_page = client.get("/orders/new")
    assert form_page.status_code == 200
    preview = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2")
    assert preview.status_code == 200 and preview.json()["order_no"] == "TWD2-260715001"
    assert 'name="order_no"' in form_page.text
    assert 'data-paste-image-target="#product-images"' in form_page.text
    assert 'data-customer-name' in form_page.text and "程炬（编码 1）" in form_page.text
    customers = repo.list_customers()
    assert len(customers) == 62
    assert {row["code"] for row in customers if row["name"] == "优品"} == {15}
    assert client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=13").status_code == 400
    response = client.post(
        "/orders/new",
        data={
            "csrf": csrf(form_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "测试产品", "order_date": "2026-07-15", "delivery_date": "2026-07-20",
            "quantity": "100", "quantity_unit": "个", "order_prefix_no": "1",
            "order_no": "TWD1-260715001",
            "bi_no": "PO-001", "production_no": "SC-001", "global_note": "红字备注",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    detail_url = response.headers["location"]
    detail = client.get(detail_url)
    assert detail.status_code == 200 and "TWD1-260715001" in detail.text
    assert "程炬" in detail.text
    duplicate_page = client.get("/orders/new")
    duplicate = client.post(
        "/orders/new",
        data={
            "csrf": csrf(duplicate_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "重复编号测试", "order_date": "2026-07-15", "quantity": "1",
            "quantity_unit": "个", "order_prefix_no": "1", "order_no": "TWD1-260715001",
        },
        follow_redirects=False,
    )
    assert duplicate.status_code == 303
    assert "TWD1-260715001" in client.get(duplicate.headers["location"]).text
    manual_page = client.get("/orders/new")
    manual = client.post(
        "/orders/new",
        data={
            "csrf": csrf(manual_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "手动编号", "order_date": "2026-07-15", "quantity": "1",
            "quantity_unit": "个", "order_prefix_no": "1", "order_no": "TWD1-MANUAL001",
        },
        follow_redirects=False,
    )
    assert manual.status_code == 303
    manual_id = int(manual.headers["location"].split("/")[2].split("?")[0])
    assert "TWD1-MANUAL001" in client.get(manual.headers["location"]).text
    orders_page = client.get("/orders")
    assert orders_page.status_code == 200 and "data-admin-context" in orders_page.text
    edit_page = client.get("/orders/1/edit")
    assert edit_page.status_code == 200
    assert 'data-paste-image-target="#edit-product-images"' in edit_page.text
    updated = client.post(
        "/orders/1/edit",
        data={
            "csrf": csrf(edit_page.text), "order_type": "新订单", "salesman": "admin-editor",
            "order_no": "TWD1-260715001", "product_name": "admin-updated",
            "order_date": "2026-07-15", "delivery_date": "2026-07-21", "quantity": "88",
            "quantity_unit": "个", "order_prefix_no": "1", "global_note": "updated",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert "admin-updated" in client.get(updated.headers["location"]).text
    deleted = client.post(
        f"/orders/{manual_id}/delete",
        data={"csrf": csrf(orders_page.text)},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert client.get(f"/orders/{manual_id}").status_code == 404
    assert client.get("/orders").status_code == 200
    assert client.get("/finance").status_code == 200
    outsource_page = client.get("/outsource")
    assert outsource_page.status_code == 200
    assert client.get("/orders/1/pdf").status_code == 200

print(f"web smoke ok: {root}")


