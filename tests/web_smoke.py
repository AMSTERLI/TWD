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
    preview = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2")
    assert preview.status_code == 200 and preview.json()["order_no"] == "TWD2-260715001"
    preview_again = client.get("/api/next-order-no?order_date=2026-07-15&order_prefix_no=2")
    assert preview_again.status_code == 200 and preview_again.json()["order_no"] == "TWD2-260715002"
    assert 'name="order_no"' in form_page.text
    assert 'readonly data-order-number' not in form_page.text
    assert 'name="spare_quantity"' in form_page.text
    assert 'data-paste-image-target="#product-images"' in form_page.text
    assert 'data-customer-name' in form_page.text and "程炬（编码 1）" in form_page.text
    customers = repo.list_customers()
    assert len(customers) == 66
    assert {row["code"] for row in customers if row["name"] == "优品"} == {15}
    assert {(row["code"], row["name"]) for row in customers if row["code"] in {66, 67, 68, 69}} == {(66, "宜创"), (67, "睿华"), (68, "旭日"), (69, "铭威")}
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
            "quantity_unit": "个", "order_prefix_no": "1", "order_no": "TWD1-MANUAL001",
        },
        follow_redirects=False,
    )
    assert manual.status_code == 303
    manual_id = int(manual.headers["location"].split("/")[2].split("?")[0])
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
    assert client.get("/orders/1/pdf").status_code == 200

print(f"web smoke ok: {root}")


