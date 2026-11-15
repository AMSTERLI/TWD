import os
import re
import sys
import tempfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["TWD_DATA_DIR"] = tempfile.mkdtemp(prefix="twd-uv-options-")
os.environ["TWD_SESSION_SECRET"] = "uv-options-test-secret-long-enough"

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from order_system.web.app import app, repo
from order_system.web.repository import ORDER_COLUMNS


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html)[1]


with TestClient(app) as client:
    repo.create_user("workshop", "test-pass-123", "workshop")
    login = client.get("/login")
    client.post("/login", data={"csrf": csrf(login.text), "username": "workshop", "password": "test-pass-123"})
    for option in ("\u5370\u5237", "\u6253\u5370"):
        payload = dict.fromkeys(ORDER_COLUMNS)
        payload.update(order_type="test", salesman="test", product_name="test",
                       order_date="2026-11-15", quantity=100, spare_quantity=0,
                       order_prefix_no=1)
        order_id, order_no = repo.create_order(payload)
        page = client.get("/workshop/uv")
        assert f'data-employee-value="{option}"' in page.text
        result = client.post("/workshop/uv", data={
            "csrf": csrf(page.text), "employee_name": option, "order_no": order_no,
            "quantity": "20", "unit_price": "0.5", "mold_fee": "8",
        }, follow_redirects=False)
        assert result.status_code == 303, result.text
        record = repo.order_workshop_records(order_id)[0]
        assert record["operator_name"] == option and record["amount"] == 18
        listing = client.get("/workshop/uv")
        exported = client.post("/workshop/uv/export", data={
            "csrf": csrf(listing.text), "selected_ids": str(record["id"]),
        })
        sheet = load_workbook(BytesIO(exported.content)).active
        assert sheet.cell(2, 12).value == option
print("uv options smoke ok")
