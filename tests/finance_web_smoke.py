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


def create_order(client: TestClient, order_date: str, product: str, customer_code: int) -> str:
    page = client.get("/orders/new")
    response = client.post(
        "/orders/new",
        data={
            "csrf": csrf(page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": product, "order_date": order_date, "delivery_date": "2026-07-30",
            "quantity": "10", "spare_quantity": "0", "quantity_unit": "个", "unit_price": "2.5",
            "extra_fee": "3", "order_prefix_no": str(customer_code),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    order_id = int(response.headers["location"].split("/")[2].split("?")[0])
    return repo.get_order(order_id)["order_no"]



def direct_order_payload(order_no: str, order_date: str) -> dict[str, object]:
    data = {column: None for column in ORDER_COLUMNS}
    data.update({
        "order_type": "\u65b0\u8ba2\u5355",
        "salesman": "\u6d4b\u8bd5",
        "order_no": order_no,
        "product_name": "\u6279\u91cf\u6d4b\u8bd5",
        "order_date": order_date,
        "delivery_date": "2026-07-30",
        "quantity": 10,
        "spare_quantity": 0,
        "quantity_unit": "\u4e2a",
        "unit_price": 2.5,
        "extra_fee": 3,
        "order_prefix_no": 9,
        "paid_status": 0,
        "invoice_status": 0,
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
    assert "产品" not in finance_page.text and "旧产品" not in finance_page.text and "新产品" not in finance_page.text
    assert "是否开票" in finance_page.text and "未开票" in finance_page.text
    assert "是否收款" in finance_page.text and "已选未收款合计 ¥" in finance_page.text
    assert "订单暂存区" in finance_page.text and "data-finance-stash" in finance_page.text
    assert "data-context-stash" in Path("order_system/web/static/app.js").read_text(encoding="utf-8")
    assert f'data-request-edit-url="/orders/1/edit"' in finance_page.text
    assert f'data-stash-no="{old_order}"' in finance_page.text and 'data-stash-id="1"' in finance_page.text
    assert "/finance/receivables/pdf" in finance_page.text
    payables_page = client.get("/finance/payables")
    assert payables_page.status_code == 200
    assert old_order in payables_page.text and new_order in payables_page.text

    filtered_customer = client.get("/finance/receivables?receivable_q=莱威尔")
    receivable_html = filtered_customer.text
    assert new_order in receivable_html and old_order not in receivable_html

    filtered_income = client.get("/finance/receivables?receivable_date_from=2026-07-10")
    assert new_order in filtered_income.text and old_order not in filtered_income.text
    filtered_unpaid = client.get("/finance/receivables?receivable_paid_status=unpaid")
    assert old_order in filtered_unpaid.text and new_order in filtered_unpaid.text
    filtered_paid = client.get("/finance/receivables?receivable_paid_status=paid")
    assert old_order not in filtered_paid.text and new_order not in filtered_paid.text
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
    invoice_response = client.post(
        "/finance/receivables/invoice",
        data={"csrf": token, "selected_ids": ["1", "2"], "invoiced": "1"},
        follow_redirects=False,
    )
    assert invoice_response.status_code == 303
    assert repo.get_order(1)["invoice_status"] == 1 and repo.get_order(2)["invoice_status"] == 1
    invoice_page = client.get("/finance/receivables")
    assert "已开票" in invoice_page.text
    uninvoice_response = client.post(
        "/finance/receivables/invoice",
        data={"csrf": csrf(invoice_page.text), "selected_ids": "2", "invoiced": "0"},
        follow_redirects=False,
    )
    assert uninvoice_response.status_code == 303
    assert repo.get_order(1)["invoice_status"] == 1 and repo.get_order(2)["invoice_status"] == 0
    bulk_ids = []
    for index in range(45):
        order_id, _ = repo.create_order(direct_order_payload(f"TWD9-260722{index + 1:03d}", "2026-07-22"))
        bulk_ids.append(order_id)
    bulk_status = client.post(
        "/finance/receivables/status",
        data={
            "csrf": csrf(invoice_page.text),
            "select_scope": "all_matching",
            "receivable_date_from": "2026-07-22",
            "receivable_date_to": "2026-07-22",
            "paid": "1",
        },
        follow_redirects=False,
    )
    assert bulk_status.status_code == 303
    assert all(repo.get_order(order_id)["paid_status"] == 1 for order_id in bulk_ids)
    assert repo.get_order(1)["paid_status"] == 1 and repo.get_order(2)["paid_status"] == 1
    filtered_unpaid_after = client.get("/finance/receivables?receivable_paid_status=unpaid")
    assert old_order not in filtered_unpaid_after.text and new_order not in filtered_unpaid_after.text

    finance_edit_page = client.get("/orders/1/edit")
    assert finance_edit_page.status_code == 200
    assert "提交订单修改申请" in finance_edit_page.text and "提交审批" in finance_edit_page.text
    edit_request = client.post(
        "/orders/1/edit",
        data={
            "csrf": csrf(finance_edit_page.text),
            "order_type": "新订单",
            "salesman": "测试",
            "order_no": old_order,
            "product_name": "旧订单",
            "order_date": "2026-07-01",
            "delivery_date": "2026-07-30",
            "quantity": "50",
            "spare_quantity": "0",
            "quantity_unit": "个",
            "unit_price": "2.5",
            "split_quantity": ["20", "30"],
            "split_unit_price": ["2", "3"],
            "extra_fee": "3",
            "order_prefix_no": "1",
            "invoice_status": "1",
        },
        follow_redirects=False,
    )
    assert edit_request.status_code == 303, edit_request.text
    assert edit_request.headers["location"] == "/messages"
    assert repo.get_order(1)["quantity"] == 10
    finance_messages = client.get("/messages")
    assert finance_messages.status_code == 200 and "数量从10修改为50" in finance_messages.text
    assert "拆分单价从空修改为20×2、30×3" in finance_messages.text
    page = client.get("/")
    client.post("/logout", data={"csrf": csrf(page.text)})
    login(client, "admin", "admin-password")
    admin_messages = client.get("/messages")
    assert "数量从10修改为50" in admin_messages.text
    assert "拆分单价从空修改为20×2、30×3" in admin_messages.text
    approve = client.post(
        "/messages/1/review",
        data={"csrf": csrf(admin_messages.text), "decision": "approve", "review_note": "同意财务修改"},
        follow_redirects=False,
    )
    assert approve.status_code == 303
    assert repo.get_order(1)["quantity"] == 50
    assert repo.finance_order_rows([1])[0]["amount"] == 133
    page = client.get("/")
    client.post("/logout", data={"csrf": csrf(page.text)})
    login(client, "finance", "finance-password")
    approved_messages = client.get("/messages?status=approved")
    assert "同意财务修改" in approved_messages.text and "/orders/1" in approved_messages.text
    assert "/orders/1/edit?request_id=1" not in approved_messages.text
    receivables_after_edit = client.get("/finance/receivables?receivable_date_to=2026-07-21")
    assert "多单价" in receivables_after_edit.text and "¥ 133.00" in receivables_after_edit.text
    token = csrf(receivables_after_edit.text)

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
