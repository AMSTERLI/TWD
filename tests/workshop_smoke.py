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
os.environ["TWD_WORKSHOP_CUTTER_PASSWORD"] = "cutter-pass-123"
os.environ["TWD_WORKSHOP_PRESS_PASSWORD"] = "press-pass-123"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.database import dumps_json  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402
from order_system.web.repository import ORDER_COLUMNS  # noqa: E402
from openpyxl import load_workbook  # noqa: E402


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


def assert_workshop_detail_pdf_only(html: str, order_id: int, hidden_unit_price: str) -> None:
    assert "pdf-preview" in html and f"/orders/{order_id}/pdf" in html
    assert "detail-grid" not in html
    assert "workflow-line" not in html
    assert "craft-grid" not in html
    assert hidden_unit_price not in html
    assert "&#36710;&#38388;&#25253;&#21040;&#35760;&#24405;" not in html
    assert "外发记录" not in html


with TestClient(app) as client:
    repo.create_user("admin", "admin-pass-123", "admin")
    repo.create_user("workshop", "workshop-pass-123", "workshop", display_name="\u8f66\u95f4")
    order_id, order_no = repo.create_order(payload("TWD1-260721101"))
    cutter_order_id, cutter_order_no = repo.create_order(payload("TWD1-260721102"))
    press_order_id, press_order_no = repo.create_order(payload("TWD1-260721103"))
    auto_qty_payload = payload("TWD1-260721104")
    auto_qty_payload["spare_quantity"] = 15
    _, auto_qty_order_no = repo.create_order(auto_qty_payload)

    admin_login_page = client.get("/login")
    admin_login = client.post(
        "/login",
        data={"csrf": csrf(admin_login_page.text), "username": "admin", "password": "admin-pass-123"},
        follow_redirects=False,
    )
    assert admin_login.status_code == 303
    admin_home = client.get("/workshop")
    assert admin_home.status_code == 200 and "/workshop/mold/unlock" not in admin_home.text
    admin_mold = client.get("/workshop/mold")
    assert admin_mold.status_code == 200 and "data-workshop-scan" in admin_mold.text
    admin_cutter = client.get("/workshop/cutter")
    assert admin_cutter.status_code == 200 and "data-workshop-scan" in admin_cutter.text
    client.post("/logout", data={"csrf": csrf(admin_mold.text)})

    login_page = client.get("/login")
    login = client.post(
        "/login",
        data={"csrf": csrf(login_page.text), "username": "workshop", "password": "workshop-pass-123"},
        follow_redirects=False,
    )
    assert login.status_code == 303 and login.headers["location"] == "/workshop"
    assert client.get("/orders").status_code == 403

    home = client.get("/workshop")
    assert home.status_code == 200 and "/workshop/mold/unlock" in home.text and "/workshop/cutter/unlock" in home.text and "/workshop/press/unlock" in home.text
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
        data={"csrf": csrf(mold.text), "order_no": [order_no], "quantity": ["2"], "unit_price": ["10.5"]},
        follow_redirects=False,
    )
    assert report.status_code == 303
    records = repo.order_workshop_records(order_id)
    assert len(records) == 1
    assert records[0]["department_name"] == "\u523b\u6a21"
    assert records[0]["quantity"] == 2
    assert abs(records[0]["unit_price"] - 10.5) < 1e-9
    cutter_unlock = client.post(
        "/workshop/cutter/unlock",
        data={"csrf": csrf(home.text), "password": "cutter-pass-123"},
        follow_redirects=False,
    )
    assert cutter_unlock.status_code == 303 and cutter_unlock.headers["location"] == "/workshop/cutter"
    cutter = client.get("/workshop/cutter")
    assert cutter.status_code == 200 and "data-workshop-scan" in cutter.text
    cutter_report = client.post(
        "/workshop/cutter",
        data={"csrf": csrf(cutter.text), "order_no": [cutter_order_no], "quantity": ["1"], "unit_price": ["8.8"]},
        follow_redirects=False,
    )
    assert cutter_report.status_code == 303
    cutter_records = repo.order_workshop_records(cutter_order_id)
    assert len(cutter_records) == 1
    assert cutter_records[0]["department_name"] == "\u8f66\u5200"
    assert cutter_records[0]["quantity"] == 1
    assert abs(cutter_records[0]["unit_price"] - 8.8) < 1e-9
    press_unlock = client.post(
        "/workshop/press/unlock",
        data={"csrf": csrf(home.text), "password": "press-pass-123"},
        follow_redirects=False,
    )
    assert press_unlock.status_code == 303 and press_unlock.headers["location"] == "/workshop/press"
    press = client.get("/workshop/press")
    assert press.status_code == 200 and "touch-piecework-panel" in press.text
    assert "workshop-press-page" in press.text
    assert "data-touch-keypad" in press.text and "data-touch-number" in press.text
    assert "data-touch-integer" in press.text and "data-touch-scale" in press.text
    press_employees = ["\u5f90\u5c71\u7acb", "\u5218\u9053\u6797", "\u6881\u8d3b\u6821", "\u79e6\u5e94\u57ce", "\u66fe\u51e4\u5a25", "\u519c\u7231\u67f3"]
    for employee in press_employees:
        assert f'data-employee-value="{employee}"' in press.text
        assert f'<option value="{employee}"' in press.text
    press_report = client.post(
        "/workshop/press",
        data={"csrf": csrf(press.text), "employee_name": ["\u5f90\u5c71\u7acb,\u5218\u9053\u6797"], "order_no": [press_order_no], "quantity": ["120"], "unit_price": ["0.08"]},
        follow_redirects=False,
    )
    assert press_report.status_code == 303
    press_records = repo.order_workshop_records(press_order_id)
    assert len(press_records) == 2
    assert {row["operator_name"] for row in press_records} == {"\u5f90\u5c71\u7acb", "\u5218\u9053\u6797"}
    for row in press_records:
        assert row["department_name"] == "\u51b2\u538b"
        assert row["quantity"] == 60
        assert abs(row["unit_price"] - 0.08) < 1e-9
        assert abs(row["amount"] - 4.8) < 1e-9
    press_list = client.get("/workshop/press")
    assert press_list.status_code == 200 and ">\u5f90\u5c71\u7acb<" in press_list.text and press_order_no in press_list.text
    assert "data-selected-amount-total" in press_list.text and 'data-amount="4.80"' in press_list.text
    assert "&#37329;&#39069;" in press_list.text and "4.80" in press_list.text
    assert 'data-selection-amount-total-all="9.60"' in press_list.text
    assert 'data-workshop-quantity-url="/workshop/press/records/' not in press_list.text
    press_filtered = client.get("/workshop/press?employee_name=%E5%BE%90%E5%B1%B1%E7%AB%8B")
    assert press_filtered.status_code == 200 and press_order_no in press_filtered.text and ">\u5f90\u5c71\u7acb<" in press_filtered.text
    press_filtered_second = client.get("/workshop/press?employee_name=%E5%88%98%E9%81%93%E6%9E%97")
    assert press_filtered_second.status_code == 200 and press_order_no in press_filtered_second.text
    press_filtered_empty = client.get("/workshop/press?employee_name=%E6%A2%81%E8%B4%BB%E6%A0%A1")
    assert press_filtered_empty.status_code == 200 and press_order_no not in press_filtered_empty.text
    history_total = client.get(f"/workshop/press/history?order_no={press_order_no}")
    assert history_total.status_code == 200 and history_total.json()["record"]["quantity"] == 100
    assert history_total.json()["record"]["existing_workshop_record"] is True
    auto_qty = client.get(f"/workshop/press/history?order_no={auto_qty_order_no}")
    assert auto_qty.status_code == 200
    assert auto_qty.json()["record"]["quantity"] == 115
    assert auto_qty.json()["record"]["unit_price"] == 0
    assert auto_qty.json()["record"]["existing_workshop_record"] is False
    press_export = client.post(
        "/workshop/press/export",
        data={"csrf": csrf(press_list.text), "selected_ids": [str(row["id"]) for row in press_records]},
    )
    assert press_export.status_code == 200
    press_workbook_path = root / "press-export.xlsx"
    press_workbook_path.write_bytes(press_export.content)
    press_sheet = load_workbook(press_workbook_path).active
    assert press_sheet.cell(row=1, column=5).value == "\u5458\u5de5"
    assert press_sheet.cell(row=2, column=1).value == press_order_no
    assert {press_sheet.cell(row=row_index, column=5).value for row_index in (2, 3)} == {"\u5f90\u5c71\u7acb", "\u5218\u9053\u6797"}
    assert press_sheet.cell(row=2, column=6).value == 60
    assert press_sheet.cell(row=3, column=6).value == 60
    assert abs(sum(press_sheet.cell(row=row_index, column=8).value for row_index in (2, 3)) - 9.6) < 1e-9
    list_page = client.get("/workshop/mold")
    assert "operator_name" not in list_page.text and "&#25805;&#20316;&#20154;" not in list_page.text
    assert "&#20986;&#36135;&#29366;&#24577;" not in list_page.text
    assert "/workshop/mold/ship" not in list_page.text
    assert 'data-delete-url="/workshop/mold/records/' in list_page.text
    assert 'data-request-edit-url="/workshop/mold/records/' not in list_page.text
    assert 'data-request-edit-mode="prompt"' not in list_page.text
    assert 'data-workshop-quantity-url="/workshop/mold/records/' in list_page.text
    assert 'data-workshop-quantity="2"' in list_page.text
    assert 'data-select-all' in list_page.text and 'data-requires-selection' in list_page.text
    wide_date_page = client.get("/workshop/mold?reported_from=1900-01-01&reported_to=2999-12-31")
    assert wide_date_page.status_code == 200 and order_no in wide_date_page.text
    narrow_date_page = client.get("/workshop/mold?reported_from=1900-01-01&reported_to=1900-01-01")
    assert narrow_date_page.status_code == 200 and order_no not in narrow_date_page.text
    history = client.get(f"/workshop/mold/history?order_no={order_no}")
    assert history.status_code == 200
    assert history.json()["record"]["quantity"] == 100
    assert abs(history.json()["record"]["unit_price"] - 10.5) < 1e-9
    quantity_request = client.post(
        f"/workshop/mold/records/{records[0]['id']}/quantity-request",
        data={"csrf": csrf(list_page.text), "quantity": "5", "reason": "漏扫数量"},
        follow_redirects=False,
    )
    assert quantity_request.status_code == 303 and quantity_request.headers["location"] == "/messages"
    assert repo.order_workshop_records(order_id)[0]["quantity"] == 2
    workshop_messages = client.get("/messages")
    assert workshop_messages.status_code == 200 and "刻模数量修改" in workshop_messages.text and "数量从2修改为5" in workshop_messages.text
    duplicate_report = client.post(
        "/workshop/mold",
        data={"csrf": csrf(client.get("/workshop/mold").text), "order_no": [order_no], "quantity": ["3"], "unit_price": ["20"]},
        follow_redirects=False,
    )
    assert duplicate_report.status_code == 303
    records = repo.order_workshop_records(order_id)
    assert len(records) == 2
    assert records[1]["quantity"] == 3
    assert abs(records[1]["unit_price"] - 20) < 1e-9
    history = client.get(f"/workshop/mold/history?order_no={order_no}")
    assert history.json()["record"]["quantity"] == 100
    assert abs(history.json()["record"]["unit_price"] - 20) < 1e-9
    delete = client.post(
        f"/workshop/mold/records/{records[1]['id']}/delete",
        data={"csrf": csrf(client.get("/workshop/mold").text)},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    records = repo.order_workshop_records(order_id)
    assert len(records) == 1

    detail = client.get(f"/orders/{order_id}")
    assert detail.status_code == 200
    assert_workshop_detail_pdf_only(detail.text, order_id, "10.5000")
    cutter_detail = client.get(f"/orders/{cutter_order_id}")
    assert cutter_detail.status_code == 200
    assert_workshop_detail_pdf_only(cutter_detail.text, cutter_order_id, "8.8000")
    workshop_user = repo.get_user(2)
    assert workshop_user is not None
    for index in range(45):
        _, bulk_order_no = repo.create_order(payload(f"TWD1-260722{index + 200:03d}"))
        repo.create_workshop_records(
            "mold",
            "\u523b\u6a21",
            [{"order_no": bulk_order_no, "quantity": 1, "unit_price": 6.6}],
            workshop_user,
        )
    bulk_page = client.get("/workshop/mold?q=TWD1-260722")
    assert bulk_page.status_code == 200 and 'data-selection-total="45"' in bulk_page.text
    bulk_export = client.post(
        "/workshop/mold/export",
        data={"csrf": csrf(bulk_page.text), "select_scope": "all_matching", "q": "TWD1-260722"},
    )
    assert bulk_export.status_code == 200
    bulk_workbook_path = root / "mold-bulk-export.xlsx"
    bulk_workbook_path.write_bytes(bulk_export.content)
    bulk_sheet = load_workbook(bulk_workbook_path).active
    exported_order_nos = {bulk_sheet.cell(row=row_index, column=1).value for row_index in range(2, bulk_sheet.max_row + 1)}
    assert len(exported_order_nos) == 45
    assert "TWD1-260722200" in exported_order_nos and "TWD1-260722244" in exported_order_nos
    cutter_export = client.post(
        "/workshop/cutter/export",
        data={"csrf": csrf(client.get("/workshop/cutter").text), "selected_ids": [str(cutter_records[0]["id"])]},
    )
    assert cutter_export.status_code == 200
    assert "spreadsheetml.sheet" in cutter_export.headers["content-type"]
    workbook_path = root / "cutter-export.xlsx"
    workbook_path.write_bytes(cutter_export.content)
    sheet = load_workbook(workbook_path).active
    headers = [sheet.cell(row=1, column=index).value for index in range(1, sheet.max_column + 1)]
    assert sheet.max_column == 7
    assert not any("\u51fa\u8d27" in str(value) or "鍑鸿揣" in str(value) for value in headers)
    assert sheet.cell(row=2, column=1).value == cutter_order_no
    assert sheet.cell(row=2, column=4).value == "车刀"

    page = client.get("/")
    client.post("/logout", data={"csrf": csrf(page.text)})
    login_page = client.get("/login")
    login = client.post(
        "/login",
        data={"csrf": csrf(login_page.text), "username": "admin", "password": "admin-pass-123"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    admin_messages = client.get("/messages")
    assert admin_messages.status_code == 200 and "刻模数量修改" in admin_messages.text
    review = client.post(
        "/messages/1/review",
        data={"csrf": csrf(admin_messages.text), "decision": "approve", "review_note": "同意"},
        follow_redirects=False,
    )
    assert review.status_code == 303
    assert repo.order_workshop_records(order_id)[0]["quantity"] == 5

    admin_detail = client.get(f"/orders/{order_id}")
    assert admin_detail.status_code == 200
    assert "workflow-line" in admin_detail.text
    assert "current" in admin_detail.text
    assert "刻模" in admin_detail.text
    assert "冲压" not in admin_detail.text
    assert "10.5000" in admin_detail.text
    assert ">5<" in admin_detail.text

print(f"workshop smoke ok: {root}")
