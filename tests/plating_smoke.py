from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-plating-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "plating-test-secret-long-enough"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.database import dumps_json  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402
from order_system.web.repository import ORDER_COLUMNS  # noqa: E402


def csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def payload(order_no: str) -> dict[str, object]:
    data = {column: None for column in ORDER_COLUMNS}
    data.update({
        "order_type": "新订单",
        "salesman": "测试业务员",
        "order_no": order_no,
        "product_name": "测试徽章",
        "order_date": "2026-08-25",
        "delivery_date": "2026-09-05",
        "quantity": 100,
        "spare_quantity": 15,
        "quantity_unit": "个",
        "order_prefix_no": 1,
        "materials_json": dumps_json([]),
        "plating_json": dumps_json(["仿金", "保护油"]),
        "accessories_json": dumps_json([]),
        "polishing_json": dumps_json([]),
        "coloring_json": dumps_json([]),
        "resin_json": dumps_json([]),
        "packaging_json": dumps_json([]),
        "image_paths_json": dumps_json([]),
        "component_parts_json": dumps_json([]),
    })
    return data


with TestClient(app) as client:
    repo.create_user("qixin", "qixin888", "plating")
    repo.create_user("admin", "admin-password", "admin")
    order_id, order_no = repo.create_order(payload("TWD1-260825501"))

    login_page = client.get("/login")
    login = client.post(
        "/login",
        data={"csrf": csrf(login_page.text), "username": "qixin", "password": "qixin888"},
        follow_redirects=False,
    )
    assert login.status_code == 303 and login.headers["location"] == "/plating"

    page = client.get("/plating")
    assert page.status_code == 200
    assert "data-plating-scan" in page.text
    assert '<span class="role">电镀</span>' in page.text
    assert "电镀工艺" in page.text and "加工单价" in page.text and "备注" in page.text
    assert "data-touch-keypad" not in page.text and "data-touch-number" not in page.text
    assert "订单列表" not in page.text and "workshop-record-list" not in page.text
    assert "data-nav-toggle" not in page.text and "/messages" not in page.text
    assert client.get("/orders").status_code == 403
    assert client.get("/workshop").status_code == 403

    lookup = client.get(f"/plating/order-lookup?order_no={order_no}")
    assert lookup.status_code == 200
    assert lookup.json()["order"]["process_name"] == "仿金、保护油"
    assert lookup.json()["order"]["quantity"] == 115

    saved = client.post(
        "/plating",
        data={
            "csrf": csrf(page.text),
            "order_no": [order_no],
            "process_name": ["亮金（修改）"],
            "quantity": ["120"],
            "unit_price": ["0.35"],
            "remark": ["加厚处理"],
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303 and saved.headers["location"] == "/plating?created=1"
    records = repo.order_workshop_records(order_id)
    assert len(records) == 1
    record = records[0]
    assert record["department_key"] == "plating" and record["department_name"] == "电镀"
    assert record["material"] == "亮金（修改）" and record["note_text"] == "加厚处理"
    assert record["quantity"] == 120 and abs(record["unit_price"] - 0.35) < 1e-9
    assert record["operator_name"] == "qixin"

    client.post("/logout", data={"csrf": csrf(client.get("/plating").text)}, follow_redirects=False)
    admin_login_page = client.get("/login")
    admin_login = client.post(
        "/login",
        data={"csrf": csrf(admin_login_page.text), "username": "admin", "password": "admin-password"},
        follow_redirects=False,
    )
    assert admin_login.status_code == 303
    admin_page = client.get("/")
    assert admin_page.status_code == 200
    assert '<a href="/plating">&#30005;&#38208;</a>' in admin_page.text
    assert client.get("/plating").status_code == 200

print("plating smoke test passed")
