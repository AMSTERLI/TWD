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
from openpyxl import load_workbook  # noqa: E402
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
        "width_mm": 32,
        "height_mm": 45,
        "thickness_mm": 2,
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
    checked_payload = payload("TWD1-260825501")
    checked_payload["plating_note"] = "电镀加厚"
    order_id, order_no = repo.create_order(checked_payload)
    note_only_payload = payload("TWD1-260825502")
    note_only_payload["plating_json"] = dumps_json([])
    note_only_payload["plating_note"] = "按样品电镀"
    _, note_only_order_no = repo.create_order(note_only_payload)
    diameter_payload = payload("TWD1-260825503")
    diameter_payload["diameter_mm"] = 38
    _, diameter_order_no = repo.create_order(diameter_payload)

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
    assert "工艺一" in page.text and "工艺二" in page.text and "规格" in page.text
    assert "加工单价" in page.text and "备注" in page.text
    assert 'name="amount"' in page.text and "金额" in page.text
    assert '<colgroup>' in page.text and 'class="plating-col-action"' in page.text
    assert "data-touch-keypad" in page.text and "data-touch-number" in page.text
    assert 'name="process_name_2"' in page.text and "打铜底" in page.text and "＋雾黑" in page.text
    assert 'name="remark"' in page.text and "多款" in page.text and "补数" in page.text
    assert 'pattern="[1-9][0-9]*"' in page.text
    assert "plating-record-list" in page.text
    assert "订单列表" not in page.text
    assert "data-nav-toggle" in page.text and "/messages" in page.text
    assert client.get("/orders").status_code == 403
    assert client.get("/workshop").status_code == 403

    lookup = client.get(f"/plating/order-lookup?order_no={order_no}")
    assert lookup.status_code == 200
    assert lookup.json()["order"]["process_name"] == "仿金、保护油"
    assert lookup.json()["order"]["process_name_2"] == ""
    assert lookup.json()["order"]["size_text"] == "45*32"
    assert lookup.json()["order"]["remark"] == ""
    assert lookup.json()["order"]["quantity"] == 115
    diameter_lookup = client.get(f"/plating/order-lookup?order_no={diameter_order_no}")
    assert diameter_lookup.status_code == 200
    assert diameter_lookup.json()["order"]["size_text"] == "38"
    note_only_lookup = client.get(f"/plating/order-lookup?order_no={note_only_order_no}")
    assert note_only_lookup.status_code == 200
    assert note_only_lookup.json()["order"]["process_name"] == "按样品电镀"
    assert note_only_lookup.json()["order"]["remark"] == ""
    assert note_only_lookup.json()["order"]["quantity"] == 115

    invalid_quantity = client.post(
        "/plating",
        data={
            "csrf": csrf(page.text),
            "order_no": [order_no],
            "process_name": ["亮金"],
            "process_name_2": [""],
            "size_text": ["45*32"],
            "quantity": ["1.5"],
            "unit_price": ["0.35"],
            "amount": ["0.525"],
            "remark": [""],
        },
    )
    assert invalid_quantity.status_code == 422
    assert "数量必须是大于 0 的整数" in invalid_quantity.text

    saved = client.post(
        "/plating",
        data={
            "csrf": csrf(page.text),
            "order_no": [order_no],
            "process_name": ["亮金（修改）"],
            "process_name_2": ["封油"],
            "size_text": ["45*32"],
            "quantity": ["120"],
            "unit_price": ["0.35"],
            "amount": ["50"],
            "remark": ["返工"],
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303 and saved.headers["location"] == "/plating?created=1"
    records = repo.order_workshop_records(order_id)
    assert len(records) == 1
    record = records[0]
    assert record["department_key"] == "plating" and record["department_name"] == "电镀"
    assert record["material"] == "亮金（修改）" and record["spec"] == "封油"
    assert record["size_text"] == "45*32" and record["note_text"] == "返工"
    assert record["quantity"] == 120 and abs(record["unit_price"] - 0.35) < 1e-9
    assert record["manual_amount"] == 50 and record["amount"] == 50
    assert record["operator_name"] == "qixin"

    record_page = client.get("/plating")
    assert record_page.status_code == 200
    assert order_no in record_page.text and "测试徽章" in record_page.text
    assert "亮金（修改）" in record_page.text and "封油" in record_page.text
    assert "45*32" in record_page.text and "返工" in record_page.text and "50.00" in record_page.text
    assert f'href="/orders/{order_id}"' in record_page.text
    assert f'data-request-edit-url="/plating/records/{record["id"]}/edit"' in record_page.text
    assert f'data-request-delete-url="/plating/records/{record["id"]}/delete-request"' in record_page.text
    assert f'data-edit-url="/plating/records/{record["id"]}/edit"' not in record_page.text
    assert 'type="date" name="reported_from"' in record_page.text
    assert 'type="date" name="reported_to"' in record_page.text
    assert 'data-selection-total="1"' in record_page.text
    assert 'data-selection-amount-total-all="50.00"' in record_page.text
    assert 'data-select-all' in record_page.text and 'data-selected-amount-total' in record_page.text
    assert 'action="/plating/export"' in record_page.text and "导出选中" in record_page.text
    export = client.post(
        "/plating/export",
        data={"csrf": csrf(record_page.text), "select_scope": "page", "selected_ids": [record["id"]]},
    )
    assert export.status_code == 200
    assert "spreadsheetml.sheet" in export.headers["content-type"]
    export_path = root / "plating-export.xlsx"
    export_path.write_bytes(export.content)
    export_sheet = load_workbook(export_path).active
    assert [cell.value for cell in export_sheet[1]][:10] == [
        "订单号", "产品", "工艺一", "工艺二", "规格", "数量", "加工单价", "金额", "备注", "录入时间",
    ]
    assert [cell.value for cell in export_sheet[2]][:9] == [
        order_no, "测试徽章", "亮金（修改）", "封油", "45*32", 120, 0.35, 50, "返工",
    ]
    assert client.get("/plating?reported_from=1900-01-01&reported_to=2999-12-31").text.count(order_no) >= 1
    assert order_no not in client.get("/plating?reported_from=1900-01-01&reported_to=1900-01-01").text

    detail_page = client.get(f"/orders/{order_id}")
    assert detail_page.status_code == 200
    assert "pdf-preview" in detail_page.text and f'/orders/{order_id}/pdf' in detail_page.text
    assert "基本信息" not in detail_page.text

    edit_page = client.get(f'/plating/records/{record["id"]}/edit')
    assert edit_page.status_code == 200
    assert "修改电镀记录" in edit_page.text and "data-plating-edit" in edit_page.text
    assert "data-touch-keypad" in edit_page.text
    assert "申请原因" in edit_page.text and "提交修改申请" in edit_page.text
    updated = client.post(
        f'/plating/records/{record["id"]}/edit',
        data={
            "csrf": csrf(edit_page.text),
            "process_name": "雾银",
            "process_name_2": "清洗",
            "size_text": "46*33",
            "quantity": "121",
            "unit_price": "0.4",
            "amount": "55",
            "remark": "补数",
            "reason": "工艺和数量录入错误",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303 and updated.headers["location"] == "/messages"
    pending_record = repo.plating_record(record["id"])
    assert pending_record is not None and pending_record["material"] == "亮金（修改）"
    plating_messages = client.get("/messages")
    assert plating_messages.status_code == 200
    assert "电镀记录修改" in plating_messages.text and "工艺一从亮金（修改）修改为雾银" in plating_messages.text
    direct_delete = client.post(
        f'/plating/records/{record["id"]}/delete',
        data={"csrf": csrf(record_page.text)},
        follow_redirects=False,
    )
    assert direct_delete.status_code == 403 and repo.plating_record(record["id"]) is not None

    client.post("/logout", data={"csrf": csrf(plating_messages.text)}, follow_redirects=False)
    admin_login_page = client.get("/login")
    admin_login = client.post(
        "/login",
        data={"csrf": csrf(admin_login_page.text), "username": "admin", "password": "admin-password"},
        follow_redirects=False,
    )
    assert admin_login.status_code == 303
    admin_messages = client.get("/messages")
    assert "电镀记录修改" in admin_messages.text
    approve_update = client.post(
        "/messages/1/review",
        data={"csrf": csrf(admin_messages.text), "decision": "approve", "review_note": "同意修改"},
        follow_redirects=False,
    )
    assert approve_update.status_code == 303
    edited_record = repo.plating_record(record["id"])
    assert edited_record is not None
    assert edited_record["material"] == "雾银" and edited_record["spec"] == "清洗"
    assert edited_record["size_text"] == "46*33" and edited_record["note_text"] == "补数"
    assert edited_record["quantity"] == 121 and edited_record["unit_price"] == 0.4
    assert edited_record["manual_amount"] == 55
    admin_plating_page = client.get("/plating")
    assert f'data-edit-url="/plating/records/{record["id"]}/edit"' in admin_plating_page.text
    assert f'data-delete-url="/plating/records/{record["id"]}/delete"' in admin_plating_page.text

    client.post("/logout", data={"csrf": csrf(admin_plating_page.text)}, follow_redirects=False)
    qixin_login_page = client.get("/login")
    qixin_login = client.post(
        "/login",
        data={"csrf": csrf(qixin_login_page.text), "username": "qixin", "password": "qixin888"},
        follow_redirects=False,
    )
    assert qixin_login.status_code == 303
    qixin_page = client.get("/plating")
    delete_request = client.post(
        f'/plating/records/{record["id"]}/delete-request',
        data={"csrf": csrf(qixin_page.text), "reason": "重复录入"},
        follow_redirects=False,
    )
    assert delete_request.status_code == 303 and delete_request.headers["location"] == "/messages"
    assert repo.plating_record(record["id"]) is not None
    delete_messages = client.get("/messages")
    assert "电镀记录删除" in delete_messages.text and "重复录入" in delete_messages.text

    client.post("/logout", data={"csrf": csrf(delete_messages.text)}, follow_redirects=False)
    final_admin_login_page = client.get("/login")
    final_admin_login = client.post(
        "/login",
        data={"csrf": csrf(final_admin_login_page.text), "username": "admin", "password": "admin-password"},
        follow_redirects=False,
    )
    assert final_admin_login.status_code == 303
    final_admin_messages = client.get("/messages")
    approve_delete = client.post(
        "/messages/2/review",
        data={"csrf": csrf(final_admin_messages.text), "decision": "approve", "review_note": "同意删除"},
        follow_redirects=False,
    )
    assert approve_delete.status_code == 303
    assert repo.plating_record(record["id"]) is None
    admin_page = client.get("/")
    assert admin_page.status_code == 200
    assert '<a href="/plating">&#30005;&#38208;</a>' in admin_page.text
    assert client.get("/plating").status_code == 200

print("plating smoke test passed")
