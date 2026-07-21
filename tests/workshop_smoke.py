from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-workshop-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "workshop-test-secret-long-enough"
os.environ["TWD_WORKSHOP_MOLD_PASSWORD"] = "mold-pass-123"

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
        "order_type": "\u65b0\u8ba2\u5355",
        "salesman": "\u6768\u5a1f",
        "order_no": order_no,
        "product_name": "\u6d4b\u8bd5\u5fbd\u7ae0",
        "order_date": "2026-07-21",
        "delivery_date": "2026-07-30",
        "quantity": 100,
        "spare_quantity": 0,
        "quantity_unit": "\u4e2a",
        "order_prefix_no": 1,
        "materials_json": dumps_json([]),
        "plating_json": dumps_json([]),
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
    repo.create_user("admin", "admin-pass-123", "admin")
    repo.create_user("workshop", "workshop-pass-123", "workshop", display_name="\u8f66\u95f4")
    order_id, order_no = repo.create_order(payload("TWD1-260721101"))

    login_page = client.get("/login")
    login = client.post(
        "/login",
        data={"csrf": csrf(login_page.text), "username": "workshop", "password": "workshop-pass-123"},
        follow_redirects=False,
    )
    assert login.status_code == 303 and login.headers["location"] == "/workshop"
    assert client.get("/orders").status_code == 403

    home = client.get("/workshop")
    assert home.status_code == 200 and "/workshop/mold/unlock" in home.text
    bad_unlock = client.post(
        "/workshop/mold/unlock",
        data={"csrf": csrf(home.text), "password": "bad"},
        follow_redirects=False,
    )
    assert bad_unlock.status_code == 403
    unlock = client.post(
        "/workshop/mold/unlock",
        data={"csrf": csrf(home.text), "password": "mold-pass-123"},
        follow_redirects=False,
    )
    assert unlock.status_code == 303 and unlock.headers["location"] == "/workshop/mold"

    mold = client.get("/workshop/mold")
    assert mold.status_code == 200 and "data-workshop-scan" in mold.text
    report = client.post(
        "/workshop/mold",
        data={"csrf": csrf(mold.text), "order_no": [order_no], "unit_price": ["10.5"]},
        follow_redirects=False,
    )
    assert report.status_code == 303
    records = repo.order_workshop_records(order_id)
    assert len(records) == 1
    assert records[0]["department_name"] == "\u523b\u6a21"
    assert abs(records[0]["unit_price"] - 10.5) < 1e-9

    detail = client.get(f"/orders/{order_id}")
    assert detail.status_code == 200
    assert "workflow-line" in detail.text
    assert "current" in detail.text
    assert "10.5000" in detail.text

print(f"workshop smoke ok: {root}")
