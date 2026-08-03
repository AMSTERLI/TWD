from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(tempfile.mkdtemp(prefix="twd-outsource-batch-"))
os.environ["TWD_DATA_DIR"] = str(root)
os.environ["TWD_SESSION_SECRET"] = "outsource-batch-test-secret-long-enough"

from fastapi.testclient import TestClient  # noqa: E402
from order_system.database import dumps_json  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402
from order_system.web.repository import ORDER_COLUMNS  # noqa: E402


DIE_CAST = "\u538b\u94f8"
PUNCH = "\u51b2\u538b"
COLORING = "\u4e0a\u8272"
PIN = "\u710a\u9488"
LASER = "\u956d\u96d5"
LOW_ZINC = "\u4f4e\u6e29\u950c\u5408\u91d1"


def token(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def order_payload(product: str) -> dict:
    payload = {column: None for column in ORDER_COLUMNS}
    payload.update({
        "order_type": "test", "salesman": "tester", "product_name": product,
        "order_date": "2026-07-15", "quantity": 100, "spare_quantity": 7, "quantity_unit": "pcs",
        "width_mm": 12.5, "height_mm": 8.25, "thickness_mm": 1.2,
        "order_prefix_no": 1, "materials_json": dumps_json(["brass"]),
        "coloring_json": dumps_json([COLORING, "UV"]),
    })
    return payload


with TestClient(app) as client:
    repo.create_user("admin", "test-password", "admin")
    repo.legacy.add_outsource_factory(DIE_CAST, "batch-factory")
    repo.legacy.add_outsource_factory(COLORING, "color-factory")
    repo.legacy.add_outsource_factory(LOW_ZINC, "low-zinc-factory")
    first_no = repo.create_order(order_payload("batch-one"))[1]
    second_no = repo.create_order(order_payload("batch-two"))[1]

    login = client.get("/login")
    client.post("/login", data={
        "csrf": token(login.text), "username": "admin", "password": "test-password",
    })
    pin_factories = {item["factory_name"] for item in repo.factories(PIN)}
    assert "\u79e6\u6c38\u548c" in pin_factories
    page = client.get("/outsource")
    assert page.status_code == 200
    assert "data-outsource-batch" in page.text
    assert "data-outsource-receive" in page.text
    assert "data-order-lookup-url" in page.text and "data-outsource-orders-json" not in page.text
    assert 'name="width_mm" step="any"' in page.text
    assert "模具费" in page.text
    static_js = Path("order_system/web/static/app.js").read_text(encoding="utf-8")
    assert "input.disabled = !active" in static_js
    lookup = client.get(f"/outsource/order-lookup?order_no={first_no}")
    assert lookup.status_code == 200
    lookup_order = lookup.json()["order"]
    assert lookup_order["order_no"] == first_no
    assert lookup_order["quantity"] == 100 and lookup_order["spare_quantity"] == 7
    assert float(lookup_order["width_mm"]) == 12.5 and float(lookup_order["height_mm"]) == 8.25
    response = client.post(
        "/outsource",
        data={
            "csrf": token(page.text), "process_name": DIE_CAST, "factory_name": "batch-factory",
            "outsource_date": "2026-07-15", "order_no": [first_no, second_no],
            "product_quantity": ["80", "90"], "spare_quantity": ["5", "6"],
            "unit_price": ["0.3", "0.4"], "processing_fee": ["2", "3"],
            "flag_type": ["", "replenishment"], "remark": ["first", "second"],
            "manual_amount": ["", ""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert response.headers["location"].startswith("/outsource/receipt?ids=")
    receipt_page = client.get(response.headers["location"])
    assert receipt_page.status_code == 200
    assert "泰威德五金厂" in receipt_page.text
    assert "batch-factory" in receipt_page.text and DIE_CAST in receipt_page.text
    assert first_no in receipt_page.text and second_no in receipt_page.text
    assert "本次合计" in receipt_page.text and "本月合计" in receipt_page.text
    assert "63.90" in receipt_page.text and "{{" not in receipt_page.text
    assert "85个" in receipt_page.text and "96个" in receipt_page.text
    assert "item-subline" in receipt_page.text
    receipt_ids = [int(item) for item in response.headers["location"].split("ids=", 1)[1].split(",")]
    receipt_data = repo.outsource_receipt(receipt_ids)
    assert receipt_data is not None
    assert abs(receipt_data["current_total"] - 63.9) < 1e-9
    assert abs(receipt_data["month_total"] - 63.9) < 1e-9
    records = repo.outsource_records()["rows"]
    assert len(records) == 2
    assert {row["order_no"] for row in records} == {first_no, second_no}
    assert {row["factory_name"] for row in records} == {"batch-factory"}
    assert all(row["received_status"] == 0 for row in records)
    receive = client.post(
        "/outsource/receive",
        data={"csrf": token(page.text), "receive_order_no": [first_no]},
        follow_redirects=False,
    )
    assert receive.status_code == 303 and "received=1" in receive.headers["location"]
    received_record = [row for row in repo.outsource_records()["rows"] if row["order_no"] == first_no][0]
    assert received_record["received_status"] == 1 and received_record["received_at"]
    refreshed = client.get("/outsource")
    assert "data-admin-context" in refreshed.text
    assert "已收货" in refreshed.text and "已外发" in refreshed.text
    editable_id = records[0]["id"]
    edit_page = client.get(f"/outsource/{editable_id}/edit")
    assert edit_page.status_code == 200
    edited = client.post(
        f"/outsource/{editable_id}/edit",
        data={
            "csrf": token(edit_page.text), "process_name": DIE_CAST,
            "factory_name": "batch-factory", "outsource_date": "2026-07-16",
            "product_quantity": "50", "spare_quantity": "2", "unit_price": "0.8",
            "flag_type": "remake", "remark": "admin-updated",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303, edited.text
    edited_record = repo.get_outsource_record(editable_id)
    assert edited_record["quantity"] == 52 and edited_record["remark"] == "admin-updated"

    before = len(records)
    try:
        repo.create_outsource_batch(
            {"process_name": DIE_CAST, "factory_name": "rollback-factory"},
            [
                {"order_no": first_no, "product_quantity": 1, "unit_price": 1},
                {"order_no": "NOT-EXISTS", "product_quantity": 1, "unit_price": 1},
            ],
        )
        raise AssertionError("missing order should fail")
    except ValueError:
        pass
    assert len(repo.outsource_records()["rows"]) == before

    process_names = {item["process_name"] for item in repo.processes()}
    assert {PUNCH, COLORING, "印刷/UV"}.issubset(process_names)
    assert "UV" not in process_names and "印刷" not in process_names

    punch_id = repo.create_outsource_batch(
        {"process_name": PUNCH, "factory_name": "punch-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{
            "order_no": first_no, "product_quantity": 80, "spare_quantity": 5,
            "unit_price": 0.3, "processing_fee": 2, "length_mm": 10,
            "width_mm": 5, "thickness_mm": 1, "density": 0.00785, "weight": 0.00555,
        }],
    )[0]
    punch = repo.legacy.get_outsource_record(punch_id)
    expected_material = (10 + 3) * (5 + 3) * 1 * 0.00785 * 0.00555
    assert abs(punch["material_unit_price"] - expected_material) < 1e-9
    assert abs(punch["amount"] - (85 * (0.3 + expected_material) + 2)) < 1e-9

    manual_punch_id = repo.create_outsource_batch(
        {"process_name": PUNCH, "factory_name": "punch-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{
            "order_no": first_no, "product_quantity": 80, "spare_quantity": 5,
            "unit_price": 0.3, "processing_fee": 2, "length_mm": 10,
            "width_mm": 5, "thickness_mm": 1, "density": 0.00785, "weight": 0.00555,
            "manual_amount": 123.45,
        }],
    )[0]
    manual_punch = repo.legacy.get_outsource_record(manual_punch_id)
    assert manual_punch["amount"] == 123.45

    flagged_coloring_id = repo.create_outsource_batch(
        {"process_name": COLORING, "factory_name": "ignore-factory", "outsource_date": "2026-07-14", "paid_status": 0},
        [{"order_no": second_no, "product_quantity": 10, "unit_price": 0.2, "color_count": "3", "remake_flag": 1}],
    )[0]
    ignored_history = client.get(f"/outsource/history?order_no={second_no}&process_name={COLORING}")
    assert ignored_history.status_code == 200 and ignored_history.json()["record"] is None

    coloring_id = repo.create_outsource_batch(
        {"process_name": COLORING, "factory_name": "color-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": first_no, "product_quantity": 10, "unit_price": 0.2, "color_count": "3"}],
    )[0]
    coloring = repo.legacy.get_outsource_record(coloring_id)
    assert coloring["color_count"] == 3 and abs(coloring["amount"] - (10 * 0.2 * 3)) < 1e-9
    coloring_history = client.get(f"/outsource/history?order_no={first_no}&process_name={COLORING}")
    assert coloring_history.status_code == 200
    assert coloring_history.json()["record"]["factory_name"] == "color-factory"

    manual_coloring_id = repo.create_outsource_batch(
        {"process_name": COLORING, "factory_name": "color-factory", "outsource_date": "2026-07-16", "paid_status": 0},
        [{"order_no": first_no, "product_quantity": 10, "unit_price": 0.2, "color_count": "3", "manual_amount": 99.9}],
    )[0]
    manual_coloring = repo.legacy.get_outsource_record(manual_coloring_id)
    assert manual_coloring["amount"] == 99.9

    uv_id = repo.create_outsource_batch(
        {"process_name": "印刷/UV", "factory_name": "print-uv-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": second_no, "product_quantity": 10, "spare_quantity": 2, "unit_price": 3, "plate_fee": 12}],
    )[0]
    uv = repo.legacy.get_outsource_record(uv_id)
    assert uv["plate_fee"] == 12 and uv["amount"] == 48

    uv_blank_id = repo.create_outsource_batch(
        {"process_name": "印刷/UV", "factory_name": "print-uv-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": second_no, "product_quantity": 10, "unit_price": 99, "plate_fee": 12}],
    )[0]
    uv_blank = repo.legacy.get_outsource_record(uv_blank_id)
    assert uv_blank["amount"] == 1002

    laser_id = repo.create_outsource_batch(
        {"process_name": LASER, "factory_name": "\u5f20\u5c55\u5c71", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": first_no, "unit_price": 0.5}],
    )[0]
    laser = repo.legacy.get_outsource_record(laser_id)
    assert laser["product_quantity"] == 107 and laser["spare_quantity"] == 0
    assert laser["quantity"] == 107 and laser["amount"] == 53.5

    low_zinc_id = repo.create_outsource_batch(
        {"process_name": LOW_ZINC, "factory_name": "low-zinc-factory", "outsource_date": "2026-07-15", "paid_status": 0},
        [{"order_no": second_no, "product_quantity": 10, "spare_quantity": 2, "unit_price": 1.5, "mold_fee": 8}],
    )[0]
    low_zinc = repo.legacy.get_outsource_record(low_zinc_id)
    assert low_zinc["mold_fee"] == 8 and low_zinc["amount"] == 26

    assert client.post(f"/outsource/{punch_id}/paid", data={"csrf": token(page.text), "paid": "1"}).status_code == 404
    refreshed = client.get("/outsource")
    assert "/paid" not in refreshed.text
    first_order = repo.legacy.get_order_by_order_no(first_no)
    blocked = client.post(
        f"/orders/{first_order['id']}/delete",
        data={"csrf": token(refreshed.text)},
    )
    assert blocked.status_code == 409

    # The outsource role can edit and delete records from the list context menu.
    repo.create_user("outsource", "test-password", "outsource")
    client.post("/login", data={"csrf": token(client.get("/login").text), "username": "outsource", "password": "test-password"})
    outsource_page = client.get("/outsource")
    assert f'/outsource/{coloring_id}/delete' in outsource_page.text
    assert f'/outsource/{coloring_id}/edit' in outsource_page.text
    assert repo.get_outsource_record(flagged_coloring_id) is not None
    outsource_edit_page = client.get(f"/outsource/{coloring_id}/edit")
    assert outsource_edit_page.status_code == 200
    outsource_edited = client.post(
        f"/outsource/{coloring_id}/edit",
        data={
            "csrf": token(outsource_edit_page.text), "process_name": COLORING,
            "factory_name": "color-factory", "outsource_date": "2026-07-17",
            "product_quantity": "12", "spare_quantity": "1", "unit_price": "0.5",
            "color_count": "2", "flag_type": "", "remark": "outsource-updated",
        },
        follow_redirects=False,
    )
    assert outsource_edited.status_code == 303, outsource_edited.text
    assert repo.get_outsource_record(coloring_id)["remark"] == "outsource-updated"
    deleted = client.post(
        f"/outsource/{coloring_id}/delete",
        data={"csrf": token(client.get("/outsource").text)},
        follow_redirects=False,
    )
    assert deleted.status_code == 303 and repo.get_outsource_record(coloring_id) is None
print("outsource batch smoke ok")
