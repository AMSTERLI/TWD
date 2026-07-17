from __future__ import annotations

import os
import re
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-finance-web-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "finance-test-secret-that-is-long-enough"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402


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


def create_order(client: TestClient, order_date: str, product: str, customer_code: int) -> str:
    page = client.get("/orders/new")
    response = client.post(
        "/orders/new",
        data={
            "csrf": csrf(page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": product, "order_date": order_date, "delivery_date": "2026-07-30",
            "quantity": "10", "quantity_unit": "个", "unit_price": "2.5",
            "extra_fee": "3", "order_prefix_no": str(customer_code),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    order_id = int(response.headers["location"].split("/")[2].split("?")[0])
    return repo.get_order(order_id)["order_no"]


def xlsx_strings(content: bytes) -> str:
    with ZipFile(BytesIO(content)) as workbook:
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        return workbook.read("xl/sharedStrings.xml").decode("utf-8")


with TestClient(app) as client:
    repo.create_user("admin", "admin-password", "admin")
    repo.create_user("finance", "finance-password", "finance")
    repo.create_user("outsource", "outsource-password", "outsource")
    login(client, "admin", "admin-password")
    old_order = create_order(client, "2026-07-01", "旧订单", 1)
    new_order = create_order(client, "2026-07-15", "新订单", 2)
    first_record = repo.create_outsource_batch(
        {"process_name": "电镀", "factory_name": "甲厂", "outsource_date": "2026-07-10", "paid_status": 0},
        [{"order_no": old_order, "product_quantity": 10, "spare_quantity": 1, "unit_price": 0.5}],
    )[0]
    second_record = repo.create_outsource_batch(
        {"process_name": "电镀", "factory_name": "乙厂", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": new_order, "product_quantity": 10, "spare_quantity": 2, "unit_price": 0.6}],
    )[0]

    page = client.get("/")
    client.post("/logout", data={"csrf": csrf(page.text)})
    login(client, "finance", "finance-password")

    assert client.get("/outsource").status_code == 403
    finance_home = client.get("/finance", follow_redirects=False)
    assert finance_home.status_code == 303
    assert finance_home.headers["location"] == "/finance/receivables"
    finance_page = client.get("/finance/receivables")
    assert finance_page.status_code == 200
    assert old_order in finance_page.text and new_order in finance_page.text
    assert "/finance/receivables/pdf" in finance_page.text
    payables_page = client.get("/finance/payables")
    assert payables_page.status_code == 200
    assert old_order in payables_page.text and new_order in payables_page.text

    filtered_customer = client.get("/finance/receivables?receivable_q=莱威尔")
    receivable_html = filtered_customer.text
    assert new_order in receivable_html and old_order not in receivable_html

    filtered_income = client.get("/finance/receivables?receivable_date_from=2026-07-10")
    assert new_order in filtered_income.text and old_order not in filtered_income.text
    filtered_payable = client.get("/finance/payables?payable_factory=乙厂")
    payable_body = filtered_payable.text.split("<tbody>")[1].split("</tbody>")[0]
    assert "乙厂" in payable_body and "甲厂" not in payable_body

    token = csrf(finance_page.text)
    response = client.post(
        "/finance/receivables/status",
        data={"csrf": token, "selected_ids": ["1", "2"], "paid": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.get_order(1)["paid_status"] == 1 and repo.get_order(2)["paid_status"] == 1

    response = client.post(
        "/finance/payables/status",
        data={"csrf": token, "selected_ids": [str(first_record), str(second_record)], "paid": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.legacy.get_outsource_record(first_record)["paid_status"] == 1
    assert repo.legacy.get_outsource_record(second_record)["paid_status"] == 1

    income_export = client.post(
        "/finance/receivables/export",
        data={"csrf": token, "selected_ids": "2"},
    )
    assert income_export.status_code == 200
    assert "spreadsheetml.sheet" in income_export.headers["content-type"]
    strings = xlsx_strings(income_export.content)
    assert new_order in strings and "莱威尔" in strings and old_order not in strings

    payable_export = client.post(
        "/finance/payables/export",
        data={"csrf": token, "selected_ids": str(second_record)},
    )
    assert payable_export.status_code == 200
    strings = xlsx_strings(payable_export.content)
    assert new_order in strings and "乙厂" in strings and old_order not in strings

    page = client.get("/")
    client.post("/logout", data={"csrf": csrf(page.text)})
    login(client, "outsource", "outsource-password")
    outsider_payables = client.get("/finance/payables")
    assert outsider_payables.status_code == 200
    assert "/finance/payables/export" in outsider_payables.text
    assert "/finance/payables/status" not in outsider_payables.text
    assert client.get("/finance/receivables").status_code == 403
    forbidden_status = client.post(
        "/finance/payables/status",
        data={"csrf": csrf(outsider_payables.text), "selected_ids": str(second_record), "paid": "0"},
        follow_redirects=False,
    )
    assert forbidden_status.status_code == 403
    outsource_export = client.post(
        "/finance/payables/export",
        data={"csrf": csrf(outsider_payables.text), "selected_ids": str(second_record)},
    )
    assert outsource_export.status_code == 200

print(f"finance web smoke ok: {root}")