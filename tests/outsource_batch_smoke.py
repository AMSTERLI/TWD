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
    first_no = repo.create_order(order_payload("batch-one"))[1]
    second_no = repo.create_order(order_payload("batch-two"))[1]

    login = client.get("/login")
    client.post("/login", data={
        "csrf": token(login.text), "username": "admin", "password": "test-password",
    })
    page = client.get("/outsource")
    assert page.status_code == 200
    assert "data-outsource-batch" in page.text
    assert "spare_quantity" in page.text and "12.5" in page.text and "8.25" in page.text
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
    records = repo.outsource_records()["rows"]
    assert len(records) == 2
    assert {row["order_no"] for row in records} == {first_no, second_no}
    assert {row["factory_name"] for row in records} == {"batch-factory"}
    refreshed = client.get("/outsource")
    assert "data-admin-context" in refreshed.text
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
