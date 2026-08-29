from __future__ import annotations

import base64
from io import BytesIO
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
from pypdf import PdfReader  # noqa: E402
from order_system.database import loads_json  # noqa: E402
from order_system.web.app import app, repo  # noqa: E402
from order_system.web.image_thumbnails import backfill_order_thumbnails, cached_thumbnail_path  # noqa: E402
from order_system.web.settings import IMAGES_DIR, THUMBNAILS_DIR  # noqa: E402


def csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")


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
    assert 'name="plating" value="\u94f6"' in form_page.text
    preview = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2")
    assert preview.status_code == 200 and preview.json()["order_no"] == "TWD2-260715001"
    preview_again = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2")
    assert preview_again.status_code == 200 and preview_again.json()["order_no"] == "TWD2-260715001"
    forced_preview = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2&force=1")
    assert forced_preview.status_code == 200 and forced_preview.json()["order_no"] == "TWD2-260715002"
    assert 'name="order_no"' in form_page.text
    assert 'readonly data-order-number' not in form_page.text
    assert 'name="spare_quantity"' in form_page.text
    assert 'data-ai-file hidden' in form_page.text
    assert 'data-ai-file-button' in form_page.text
    assert 'data-ai-paste-image' not in form_page.text
    assert 'data-ai-file-name' in form_page.text
    assert "点击本段文字，选中本框直接粘贴" in form_page.text
    assert "拖拽文件到本框" in form_page.text
    assert "补充描述" in form_page.text
    assert 'class="ai-import-upload"' in form_page.text
    assert form_page.text.count("data-ai-prompt-select") == 1
    assert "data-ai-prompt-option" not in form_page.text
    assert "把客单中的品名识别成PO号" in form_page.text
    assert "精炼订单总备注中的内容，但是要保留关键工艺信息" in form_page.text
    assert "提交自动填好的表格前，必须人工核对。" in form_page.text
    assert 'data-paste-image-target="#product-images"' in form_page.text
    assert 'data-customer-name' in form_page.text and "程炬（编码 1）" in form_page.text
    customers = repo.list_customers()
    customer_names = {row["code"]: row["name"] for row in customers}
    assert len(customers) == 63
    assert {row["code"] for row in customers if row["name"] == "\u4f18\u54c1"} == {15}
    assert {code: customer_names.get(code) for code in (7, 8, 16, 18, 21, 24, 66)} == {
        7: "\u5408\u4e50", 8: "\u4e50\u521b", 16: "\u94ed\u5a01", 18: "\u65ed\u65e5", 21: "\u777f\u534e", 24: "\u5176\u4ed6", 66: "\u5b9c\u521b",
    }
    assert all(code not in customer_names for code in (67, 68, 69))
    assert client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=13").status_code == 400
    reserved = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=1")
    assert reserved.status_code == 200 and reserved.json()["order_no"] == "TWD1-260715001"
    response = client.post(
        "/orders/new",
        data={
            "csrf": csrf(form_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "测试产品", "order_date": "2026-07-15", "delivery_date": "2026-07-20",
            "quantity": "100", "spare_quantity": "15", "quantity_unit": "个", "order_prefix_no": "1",
            "order_no": "TWD1-260715001",
            "bi_no": "PO-001", "production_no": "SC-001", "global_note": "红字备注",
            "component_text": ["component note"], "component_existing_image": [""],
        },
        files=[("product_images", ("sample.png", PNG_BYTES, "image/png")), ("component_image", ("component.png", PNG_BYTES, "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    detail_url = response.headers["location"]
    detail = client.get(detail_url)
    assert detail.status_code == 200 and "TWD1-260715001" in detail.text
    assert "100+15" in detail.text
    assert "程炬" in detail.text
    stored_order = repo.get_order(1)
    assert stored_order["salesman"] != "admin"
    image_names = loads_json(stored_order["image_paths_json"])
    assert len(image_names) == 1
    assert client.get(f"/images/{image_names[0]}").status_code == 200
    image_path = IMAGES_DIR / image_names[0]
    cached_path = cached_thumbnail_path(image_path, THUMBNAILS_DIR)
    assert cached_path is not None
    cached_path.unlink()
    backfill_stats = backfill_order_thumbnails(repo.db_path, IMAGES_DIR, THUMBNAILS_DIR)
    assert backfill_stats["created"] == 1 and not backfill_stats["failed"]
    assert cached_thumbnail_path(image_path, THUMBNAILS_DIR) is not None
    component_parts = loads_json(stored_order["component_parts_json"])
    assert component_parts and component_parts[0]["text"] == "component note"
    assert client.get(f"/images/{component_parts[0]['image']}").status_code == 200
    component_pdf = client.get("/orders/1/pdf")
    assert component_pdf.status_code == 200
    assert len(PdfReader(BytesIO(component_pdf.content)).pages) >= 2
    duplicate_page = client.get("/orders/new")
    duplicate = client.post(
        "/orders/new",
        data={
            "csrf": csrf(duplicate_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "重复编号测试", "order_date": "2026-07-15", "quantity": "1",
            "spare_quantity": "0",
            "quantity_unit": "个", "order_prefix_no": "1", "order_no": "TWD1-260715001",
        },
        follow_redirects=False,
    )
    assert duplicate.status_code == 422
    assert "TWD1-260715001" in client.get(detail_url).text
    manual_page = client.get("/orders/new")
    manual = client.post(
        "/orders/new",
        data={
            "csrf": csrf(manual_page.text), "order_type": "新订单", "salesman": "测试",
            "product_name": "手动编号", "order_date": "2026-07-15", "quantity": "1",
            "spare_quantity": "0",
            "quantity_unit": "个", "order_prefix_no": "1", "order_no": " TWD1 - MANUAL001 ",
        },
        follow_redirects=False,
    )
    assert manual.status_code == 303
    manual_id = int(manual.headers["location"].split("/")[2].split("?")[0])
    assert repo.get_order(manual_id)["order_no"] == "TWD1-MANUAL001"
    assert "TWD1-MANUAL001" in client.get(manual.headers["location"]).text
    orders_page = client.get("/orders")
    assert orders_page.status_code == 200 and "data-admin-context" in orders_page.text
    edit_page = client.get("/orders/1/edit")
    assert edit_page.status_code == 200
    assert 'data-paste-image-target="#edit-product-images"' in edit_page.text
    assert 'data-manual-order-number' in form_page.text and 'data-manual-order-number' in edit_page.text
    assert 'data-existing-images' in edit_page.text and image_names[0] in edit_page.text
    updated = client.post(
        "/orders/1/edit",
        data={
            "csrf": csrf(edit_page.text), "order_type": "新订单", "salesman": "admin-editor",
            "order_no": "TWD1-260715001", "product_name": "admin-updated",
            "order_date": "2026-07-15", "delivery_date": "2026-07-21", "quantity": "88",
            "spare_quantity": "2",
            "quantity_unit": "个", "order_prefix_no": "1", "global_note": "updated",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    updated_detail = client.get(updated.headers["location"]).text
    assert "admin-updated" in updated_detail
    assert "88+2" in updated_detail
    assert loads_json(repo.get_order(1)["image_paths_json"]) == []
    assert client.get(f"/images/{image_names[0]}").status_code == 404
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
    process_names = [item["process_name"] for item in repo.processes()]
    expected_process_order = ["\u51b2\u538b", "\u4e0a\u8272", "\u6bdb\u8fb9", "\u5305\u88c5", "\u5370\u5237/UV", "\u8f66\u7ec7\u5e26", "\u956d\u96d5", "\u6811\u8102", "\u4f4e\u6e29\u950c\u5408\u91d1"]
    assert process_names[:len(expected_process_order)] == expected_process_order
    assert 'name="receive_factory_name"' in outsource_page.text
    assert 'data-unreceived-factories-url="/outsource/unreceived-factories"' in outsource_page.text
    assert 'data-receive-factory' in outsource_page.text
    assert "receive-table" in outsource_page.text
    assert "<th>\u52a0\u5de5\u5382</th>" in outsource_page.text
    assert "\u78e8\u77f3" in outsource_page.text and "\u6bdb\u536b\u5175" in outsource_page.text
    stone_outsource = client.post(
        "/outsource",
        data={
            "csrf": csrf(outsource_page.text),
            "process_name": "\u78e8\u77f3",
            "factory_name": "\u6bdb\u536b\u5175",
            "outsource_date": "2026-07-20",
            "order_no": ["TWD1-260715001"],
            "product_quantity": ["10"],
            "spare_quantity": ["2"],
            "unit_price": ["0.3"],
            "manual_amount": [""],
            "flag_type": [""],
            "remark": [""],
        },
        follow_redirects=False,
    )
    assert stone_outsource.status_code == 303, stone_outsource.text
    stone_rows = [row for row in repo.outsource_records("TWD1-260715001", 1, 100)["rows"] if row["process_name"] == "\u78e8\u77f3"]
    assert stone_rows and stone_rows[0]["factory_name"] == "\u6bdb\u536b\u5175"
    assert abs(stone_rows[0]["amount"] - 3.6) < 1e-9
    first_outsource = repo.create_outsource_batch(
        {"process_name": "\u956d\u96d5", "factory_name": "\u5f20\u5c55\u5c71", "outsource_date": "2026-07-18", "paid_status": 0},
        [{"order_no": "TWD1-260715001", "product_quantity": 5, "spare_quantity": 0, "unit_price": 1}],
    )[0]
    second_outsource = repo.create_outsource_batch(
        {"process_name": "\u76ae\u9769", "factory_name": "\u8001\u96f7", "outsource_date": "2026-07-19", "paid_status": 0},
        [{"order_no": "TWD1-260715001", "product_quantity": 6, "spare_quantity": 0, "unit_price": 1}],
    )[0]
    receive_factory_lookup = client.get("/outsource/unreceived-factories?order_no=TWD1%20-%20260715%20001")
    assert receive_factory_lookup.status_code == 200
    assert {item["factory_name"] for item in receive_factory_lookup.json()["factories"]} == {"\u8001\u96f7", "\u5f20\u5c55\u5c71", "\u6bdb\u536b\u5175"}
    receive_first = client.post(
        "/outsource/receive",
        data={
            "csrf": csrf(outsource_page.text),
            "receive_order_no": ["TWD1 - 260715 001"],
            "receive_factory_name": ["\u5f20\u5c55\u5c71"],
        },
        follow_redirects=False,
    )
    assert receive_first.status_code == 303
    assert repo.get_outsource_record(first_outsource)["received_status"] == 1
    assert repo.get_outsource_record(second_outsource)["received_status"] == 0
    receive_factory_lookup_after = client.get("/outsource/unreceived-factories?order_no=TWD1-260715001")
    assert "\u5f20\u5c55\u5c71" not in [item["factory_name"] for item in receive_factory_lookup_after.json()["factories"]]
    receive_again = client.post(
        "/outsource/receive",
        data={
            "csrf": csrf(client.get("/outsource").text),
            "receive_order_no": ["TWD1-260715001"],
            "receive_factory_name": ["\u5f20\u5c55\u5c71"],
        },
        follow_redirects=False,
    )
    assert receive_again.status_code == 422
    static_js = Path("order_system/web/static/app.js").read_text(encoding="utf-8")
    assert "receiveFailureMessage" in static_js and "fetch(form.action" in static_js
    assert "\\u6279\\u91cf\\u6536\\u8d27\\u4fdd\\u5b58\\u5931\\u8d25" in static_js
    receive_second = client.post(
        "/outsource/receive",
        data={
            "csrf": csrf(client.get("/outsource").text),
            "receive_order_no": ["TWD1-260715001"],
            "receive_factory_name": ["\u8001\u96f7"],
        },
        follow_redirects=False,
    )
    assert receive_second.status_code == 303
    assert repo.get_outsource_record(second_outsource)["received_status"] == 1
    assert client.get("/orders/1/pdf").status_code == 200

print(f"web smoke ok: {root}")
