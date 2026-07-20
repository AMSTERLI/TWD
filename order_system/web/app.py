from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.datastructures import UploadFile

from order_system.database import dumps_json, loads_json
from order_system.excel_export import export_rows_to_excel
from order_system.order_import import OrderImportError, analyze_order_document

from .catalogs import import_catalogs
from .pdf import merge_order_pdfs, render_order_pdf
from .repository import Repository
from .security import csrf_token, valid_csrf
from .settings import (
    DB_PATH, IMAGES_DIR, MAX_IMAGE_BYTES, MAX_UPLOAD_BYTES, SESSION_HTTPS_ONLY,
    STATIC_DIR, TEMPLATES_DIR, TMP_DIR, ensure_directories, session_secret,
)


repo = Repository(DB_PATH)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
ai_slots = asyncio.Semaphore(max(1, int(os.environ.get("TWD_AI_CONCURRENCY", "2"))))


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_directories()
    repo.initialize()
    yield


app = FastAPI(title="TWD 订单管理系统", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1200)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="twd_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def current_user(request: Request) -> dict[str, Any] | None:
    user_id = request.session.get("user_id")
    return repo.get_user(int(user_id)) if user_id else None


def page_context(request: Request, **values: Any) -> dict[str, Any]:
    values.update({
        "request": request,
        "user": current_user(request),
        "csrf": csrf_token(request.session),
    })
    return values


def require_page(request: Request, roles: set[str] | None = None):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    if roles and user["role"] not in roles and user["role"] != "admin":
        return user, templates.TemplateResponse(
            request, "error.html", page_context(request, status=403, message="没有此功能的访问权限"),
            status_code=403,
        )
    return user, None




def user_display_name(user: dict[str, Any]) -> str:
    return str(user.get("display_name") or user.get("username") or "")


def sales_order_forbidden(user: dict[str, Any], record: dict[str, Any] | None) -> bool:
    return bool(user and user.get("role") == "sales" and record and str(record.get("salesman") or "") != user_display_name(user))


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "")


def valid_form_csrf(request: Request, value: str) -> bool:
    return valid_csrf(request.session, value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value or "").replace(",", ""))
    except ValueError:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").replace(",", "")))
    except ValueError:
        return default


def selected_ids(form: Any, field: str) -> list[int]:
    values: list[int] = []
    for raw in form.getlist(field):
        value = as_int(raw)
        if value > 0:
            values.append(value)
    return values[:1000]


def compose_materials(form: Any) -> list[str]:
    catalogs = import_catalogs()
    allowed = set(catalogs["materials"])
    bases = [str(value).strip() for value in form.getlist("material_base") if str(value).strip()]
    crafts = [str(value).strip() for value in form.getlist("material_craft") if str(value).strip()]
    values: list[str] = []
    if bases and crafts:
        candidates = [f"{base}  {craft}" for base in bases for craft in crafts]
    elif bases:
        candidates = bases
    else:
        candidates = [str(value).strip() for value in form.getlist("materials") if str(value).strip()]
    for candidate in candidates:
        if candidate in allowed and candidate not in values:
            values.append(candidate)
    return values


def split_materials(values: list[str]) -> tuple[list[str], list[str]]:
    catalogs = import_catalogs()
    base_allowed = set(catalogs["base_materials"])
    craft_allowed = set(catalogs["surface_crafts"])
    bases: list[str] = []
    crafts: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if "  " in item:
            base, craft = item.split("  ", 1)
        else:
            base, craft = item, ""
        if base in base_allowed and base not in bases:
            bases.append(base)
        if craft in craft_allowed and craft not in crafts:
            crafts.append(craft)
    return bases, crafts


def excel_response(sheet_name: str, headers: list[str], rows: list[list[Any]], prefix: str) -> Response:
    target = TMP_DIR / f"{uuid4().hex}.xlsx"
    try:
        export_rows_to_excel(target, sheet_name, headers, rows)
        content = target.read_bytes()
    finally:
        target.unlink(missing_ok=True)
    filename = f"{prefix}_{date.today().strftime('%Y%m%d')}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def save_images(files: list[UploadFile]) -> list[str]:
    paths: list[str] = []
    for upload in files[:6]:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("产品图片仅支持 JPG、PNG 或 WEBP")
        target = IMAGES_DIR / f"{uuid4().hex}{suffix}"
        size = 0
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("单张图片不能超过 5 MB")
                output.write(chunk)
        paths.append(target.name)
    return paths

async def save_preview_images(files: list[UploadFile]) -> list[str]:
    paths: list[str] = []
    for upload in files[:6]:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("产品图片仅支持 JPG、PNG 或 WEBP")
        target = IMAGES_DIR / f"preview-{uuid4().hex}{suffix}"
        size = 0
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("单张图片不能超过 5 MB")
                output.write(chunk)
        paths.append(target.name)
    return paths


def safe_image_name(value: Any) -> str:
    name = Path(str(value or "")).name
    if not name or name != str(value or "") or Path(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return ""
    return name


def image_is_visible_to_user(image_name: str, user: dict[str, Any]) -> bool:
    if not safe_image_name(image_name):
        return False
    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT salesman, image_paths_json FROM orders WHERE image_paths_json LIKE ?",
            (f"%{image_name}%",),
        ).fetchall()
    for row in rows:
        image_names = loads_json(row["image_paths_json"] or "[]")
        if image_name not in image_names:
            continue
        if user.get("role") == "admin" or str(row["salesman"] or "") == user_display_name(user):
            return True
    return False


def merge_edit_images(form: Any, existing: dict[str, Any], uploaded_images: list[str]) -> tuple[list[str], list[str]]:
    existing_images = [name for name in loads_json(existing.get("image_paths_json") or "[]") if safe_image_name(name)]
    allowed_existing = set(existing_images)
    kept: list[str] = []
    for raw in form.getlist("existing_images"):
        name = safe_image_name(raw)
        if name in allowed_existing and name not in kept:
            kept.append(name)
    merged = kept + [name for name in uploaded_images if safe_image_name(name)]
    if len(merged) > 6:
        raise ValueError("产品图片最多 6 张")
    removed = [name for name in existing_images if name not in kept]
    return merged, removed

async def order_payload(form: Any, *, save_uploaded_images: bool = True) -> dict[str, Any]:
    images = [item for item in form.getlist("product_images") if isinstance(item, UploadFile)]
    image_paths = await save_images(images) if save_uploaded_images else await save_preview_images(images)
    customer_code = as_int(form.get("order_prefix_no"))
    return {
        "order_type": str(form.get("order_type") or "新订单"),
        "salesman": str(form.get("salesman") or "").strip(),
        "order_no": str(form.get("order_no") or "").strip(),
        "product_name": str(form.get("product_name") or "").strip(),
        "order_date": str(form.get("order_date") or "").strip(),
        "delivery_date": str(form.get("delivery_date") or "").strip(),
        "quantity": as_int(form.get("quantity")),
        "spare_quantity": as_int(form.get("spare_quantity")),
        "quantity_unit": str(form.get("quantity_unit") or "个"),
        "unit_price": as_float(form.get("unit_price")),
        "extra_fee": as_float(form.get("extra_fee")),
        "paid_status": 0,
        "shipped_status": 0,
        "invoice_status": int(form.get("invoice_status") == "1"),
        "order_prefix_no": customer_code,
        "customer_code": customer_code,
        "customer_name": "",
        "production_no": str(form.get("production_no") or "").strip(),
        "bi_no": str(form.get("bi_no") or "").strip(),
        "width_mm": str(form.get("width_mm") or "").strip(),
        "height_mm": str(form.get("height_mm") or "").strip(),
        "thickness_mm": str(form.get("thickness_mm") or "").strip(),
        "size_as_sample": int(form.get("size_as_sample") == "1"),
        "materials_json": dumps_json(compose_materials(form)),
        "material_note": str(form.get("material_note") or "").strip(),
        "material_note_red": 1,
        "plating_json": dumps_json(form.getlist("plating")),
        "plating_note": str(form.get("plating_note") or "").strip(),
        "plating_note_red": 1,
        "accessories_json": dumps_json(form.getlist("accessories")),
        "accessories_note": str(form.get("accessories_note") or "").strip(),
        "accessories_note_red": 1,
        "polishing_json": dumps_json(form.getlist("polishing")),
        "polishing_note": str(form.get("polishing_note") or "").strip(),
        "polishing_note_red": 1,
        "coloring_json": dumps_json(form.getlist("coloring")),
        "coloring_text": "",
        "coloring_note": str(form.get("coloring_note") or "").strip(),
        "coloring_note_red": 1,
        "resin_json": dumps_json(form.getlist("resin")),
        "resin_note": str(form.get("resin_note") or "").strip(),
        "resin_note_red": 1,
        "packaging_json": dumps_json(form.getlist("packaging")),
        "packaging_rule": "",
        "packaging_note": str(form.get("packaging_note") or "").strip(),
        "packaging_note_red": 1,
        "back_mode": str(form.get("back_mode") or ""),
        "back_mode_note": str(form.get("back_mode_note") or "").strip(),
        "back_mode_note_red": 1,
        "global_note": str(form.get("global_note") or "").strip(),
        "global_note_red": 1,
        "image_paths_json": dumps_json(image_paths),
    }


def outsource_edit_payload(form: Any) -> dict[str, Any]:
    process_name = str(form.get("process_name") or "").strip()
    factory_name = str(form.get("factory_name") or "").strip()
    product_quantity = as_float(form.get("product_quantity"))
    spare_quantity = as_float(form.get("spare_quantity"))
    unit_price = as_float(form.get("unit_price"))
    quantity = product_quantity + spare_quantity
    if not process_name or not factory_name:
        raise ValueError("工序和加工厂不能为空")
    if min(product_quantity, spare_quantity, unit_price) < 0 or quantity <= 0:
        raise ValueError("数量和加工单价必须为非负数，合计数量须大于 0")

    processing_fee = length_mm = width_mm = thickness_mm = 0.0
    density, weight = 0.00785, 0.0055
    material_unit_price = 0.0
    color_count = None
    plate_fee = 0.0
    amount: float | None
    if process_name == "冲压":
        processing_fee = as_float(form.get("processing_fee"))
        length_mm = as_float(form.get("length_mm"))
        width_mm = as_float(form.get("width_mm"))
        thickness_mm = as_float(form.get("thickness_mm"))
        density = as_float(form.get("density"), 0.00785)
        weight = as_float(form.get("weight"), 0.0055)
        if min(length_mm, width_mm, thickness_mm, density, weight) <= 0:
            raise ValueError("冲压的长、宽、厚、密度和重量必须大于 0")
        material_unit_price = (length_mm + 3) * (width_mm + 3) * thickness_mm * density * weight
        amount = quantity * (unit_price + material_unit_price) + processing_fee
    elif process_name == "上色":
        color_count = as_int(form.get("color_count"))
        if color_count <= 0:
            raise ValueError("上色记录必须填写大于 0 的颜色数量")
        amount = quantity * unit_price * color_count
    elif process_name == "印刷/UV":
        plate_fee = as_float(form.get("plate_fee"))
        if plate_fee < 0:
            raise ValueError("版费不能为负数")
        amount = quantity * unit_price + plate_fee
    else:
        amount = quantity * unit_price

    flag_type = str(form.get("flag_type") or "")
    return {
        "process_name": process_name,
        "factory_name": factory_name,
        "quantity": quantity,
        "product_quantity": product_quantity,
        "spare_quantity": spare_quantity,
        "unit_price": unit_price,
        "processing_fee": processing_fee,
        "length_mm": length_mm,
        "width_mm": width_mm,
        "thickness_mm": thickness_mm,
        "density": density,
        "weight": weight,
        "material_unit_price": material_unit_price,
        "color_count": color_count,
        "plate_fee": plate_fee,
        "outsource_date": str(form.get("outsource_date") or date.today().isoformat()).strip(),
        "remark": str(form.get("remark") or "").strip(),
        "amount": amount,
        "remake_flag": int(flag_type == "remake"),
        "replenishment_flag": int(flag_type == "replenishment"),
        "paid_status": int(form.get("paid_status") == "1"),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", page_context(request, error=""))


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return templates.TemplateResponse(
            request, "login.html", page_context(request, error="页面已过期，请重试"), status_code=400
        )
    user = await run_in_threadpool(repo.authenticate, str(form.get("username") or ""), str(form.get("password") or ""))
    if not user:
        return templates.TemplateResponse(
            request, "login.html", page_context(request, error="用户名或密码错误"), status_code=401
        )
    request.session.clear()
    request.session["user_id"] = user["id"]
    csrf_token(request.session)
    await run_in_threadpool(repo.audit, user, "login", "", client_ip(request))
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    form = await request.form()
    if valid_form_csrf(request, str(form.get("csrf") or "")):
        request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    _, denied = require_page(request)
    if denied:
        return denied
    return templates.TemplateResponse(request, "dashboard.html", page_context(request, stats=repo.dashboard()))


@app.get("/orders", response_class=HTMLResponse)
def orders(request: Request, q: str = "", page: int = 1):
    user, denied = require_page(request)
    if denied:
        return denied
    salesman = user_display_name(user) if user["role"] == "sales" else None
    result = repo.list_orders(q, page, salesman=salesman)
    return templates.TemplateResponse(request, "orders.html", page_context(request, result=result, q=q, list_mode="orders"))


@app.get("/production", response_class=HTMLResponse)
def production_orders(request: Request, q: str = "", page: int = 1):
    _, denied = require_page(request, {"production"})
    if denied:
        return denied
    result = repo.list_orders(q, page)
    return templates.TemplateResponse(request, "orders.html", page_context(request, result=result, q=q, list_mode="production"))


@app.get("/messages", response_class=HTMLResponse)
def messages(request: Request, status: str = ""):
    user, denied = require_page(request, {"admin", "sales", "finance", "production"})
    if denied:
        return denied
    default_status = "pending" if user["role"] == "admin" and status == "" else status
    normalized_status = default_status if default_status in {"", "pending", "approved", "rejected"} else "pending"
    requester_id = None if user["role"] == "admin" else int(user["id"])
    return templates.TemplateResponse(
        request,
        "messages.html",
        page_context(
            request,
            requests=repo.list_edit_requests(normalized_status, requester_id),
            status=normalized_status,
        ),
    )

@app.post("/messages/{request_id}/review")
async def review_message(request: Request, request_id: int):
    user, denied = require_page(request, {"admin"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    approved = str(form.get("decision") or "") == "approve"
    note = str(form.get("review_note") or "").strip()
    try:
        order_no = await run_in_threadpool(repo.review_edit_request, request_id, user, approved, note)
        await run_in_threadpool(
            repo.audit,
            user,
            "order.edit_request.review",
            f"{request_id}:{order_no}:{'approved' if approved else 'rejected'}",
            client_ip(request),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "error.html",
            page_context(request, status=400, message=str(exc)),
            status_code=400,
        )
    return RedirectResponse("/messages", status_code=303)

@app.get("/orders/new", response_class=HTMLResponse)
def new_order(request: Request):
    user, denied = require_page(request, {"sales"})
    if denied:
        return denied
    today = date.today().isoformat()
    return templates.TemplateResponse(
        request, "order_form.html",
        page_context(
            request,
            catalogs=import_catalogs(),
            customers=repo.list_customers(),
            today=today,
            order_no="",
            customer_selection="",
            default_salesman=user_display_name(user),
            error="",
        ),
    )


@app.get("/api/next-order-no")
def next_order_no(request: Request, order_date: str = "", order_prefix_no: int = 1):
    _, denied = require_page(request, {"sales"})
    if denied:
        return JSONResponse({"error": "未登录或无权限"}, status_code=401)
    normalized_date = order_date.strip() or date.today().isoformat()
    try:
        date.fromisoformat(normalized_date)
    except ValueError:
        return JSONResponse({"error": "下单日期格式无效"}, status_code=400)
    try:
        return {"order_no": repo.preview_order_no(normalized_date, order_prefix_no)}
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/orders/preview")
async def preview_order(request: Request):
    user, denied = require_page(request, {"sales"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    preview_images: list[str] = []
    try:
        payload = await order_payload(form, save_uploaded_images=False)
        payload["salesman"] = user_display_name(user)
        preview_images = loads_json(payload.get("image_paths_json") or "[]")
        if not payload["product_name"] or payload["quantity"] <= 0 or payload["spare_quantity"] < 0 or not str(form.get("spare_quantity") or "").strip():
            raise ValueError("产品名称、有效数量和备品数量为必填项")
        content = await run_in_threadpool(render_order_pdf, payload)
    except ValueError as exc:
        return Response(str(exc), status_code=422)
    finally:
        for image_name in preview_images:
            if str(image_name).startswith("preview-"):
                (IMAGES_DIR / Path(image_name).name).unlink(missing_ok=True)
    safe_name = str(form.get("order_no") or "preview").replace("/", "-")
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}_preview.pdf"'},
    )

@app.post("/orders/new", response_class=HTMLResponse)
async def create_order(request: Request):
    user, denied = require_page(request, {"sales"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return templates.TemplateResponse(
            request, "error.html", page_context(request, status=400, message="页面已过期，请重新提交"), status_code=400
        )
    try:
        payload = await order_payload(form)
        payload["salesman"] = user_display_name(user)
        if not payload["product_name"] or payload["quantity"] <= 0 or payload["spare_quantity"] < 0 or not str(form.get("spare_quantity") or "").strip():
            raise ValueError("产品名称、有效数量和备品数量为必填项")
        order_id, order_no = await run_in_threadpool(repo.create_order, payload)
        await run_in_threadpool(repo.audit, user, "order.create", order_no, client_ip(request))
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "order_form.html",
            page_context(
                request,
                catalogs=import_catalogs(),
                customers=repo.list_customers(),
                today=date.today().isoformat(),
                order_no=str(form.get("order_no") or "").strip(),
                customer_selection=str(form.get("customer_selection") or "").strip(),
                default_salesman=user_display_name(user),
                error=str(exc),
            ),
            status_code=422,
        )
    return RedirectResponse(f"/orders/{order_id}?created=1", status_code=303)


def _editable_order(order_id: int) -> dict[str, Any] | None:
    record = repo.get_order(order_id)
    if not record:
        return None
    for key in ("materials_json", "plating_json", "accessories_json", "polishing_json",
                "coloring_json", "resin_json", "packaging_json", "image_paths_json"):
        record[key] = loads_json(record.get(key) or "[]")
    material_bases, material_crafts = split_materials(record["materials_json"])
    record["material_base_json"] = material_bases
    record["material_craft_json"] = material_crafts
    return record


@app.get("/orders/{order_id}/edit", response_class=HTMLResponse)
def edit_order_page(request: Request, order_id: int, request_id: int = 0):
    user, denied = require_page(request)
    if denied:
        return denied
    edit_request = None
    if user["role"] != "admin":
        if user["role"] not in {"sales", "finance"}:
            return templates.TemplateResponse(
                request, "error.html", page_context(request, status=403, message="没有此功能的访问权限"), status_code=403
            )
        edit_request = repo.edit_request_for_edit(request_id, order_id, int(user["id"])) if request_id else None
        if not edit_request:
            return templates.TemplateResponse(
                request, "error.html", page_context(request, status=403, message="请从消息里的修改按钮进入订单修改页面"), status_code=403
            )
    record = _editable_order(order_id)
    if not record:
        return Response(status_code=404)
    if sales_order_forbidden(user, record):
        return templates.TemplateResponse(
            request, "error.html", page_context(request, status=403, message="forbidden"), status_code=403
        )
    return templates.TemplateResponse(
        request, "order_edit.html",
        page_context(request, order=record, catalogs=import_catalogs(), error="", edit_request=edit_request),
    )


@app.post("/orders/{order_id}/edit", response_class=HTMLResponse)
async def edit_order(request: Request, order_id: int):
    user, denied = require_page(request)
    if denied:
        return denied
    form = await request.form()
    edit_request = None
    if user["role"] != "admin":
        if user["role"] not in {"sales", "finance"}:
            return Response(status_code=403)
        request_id = as_int(form.get("edit_request_id"))
        edit_request = repo.edit_request_for_edit(request_id, order_id, int(user["id"])) if request_id else None
        if not edit_request:
            return Response(status_code=403)
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    existing = repo.get_order(order_id)
    if not existing:
        return Response(status_code=404)
    if sales_order_forbidden(user, existing):
        return Response(status_code=403)
    try:
        payload = await order_payload(form)
        if user["role"] == "sales":
            payload["salesman"] = user_display_name(user)
        if not payload["product_name"] or payload["quantity"] <= 0 or payload["spare_quantity"] < 0 or not str(form.get("spare_quantity") or "").strip():
            raise ValueError("产品名称、有效数量和备品数量为必填项")
        payload["paid_status"] = int(existing.get("paid_status") or 0)
        payload["shipped_status"] = int(existing.get("shipped_status") or 0)
        if user["role"] == "sales":
            payload["invoice_status"] = int(existing.get("invoice_status") or 0)
        uploaded_images = loads_json(payload.get("image_paths_json") or "[]")
        merged_images, removed_images = merge_edit_images(form, existing, uploaded_images)
        payload["image_paths_json"] = dumps_json(merged_images)
        if not await run_in_threadpool(repo.update_order, order_id, payload):
            return Response(status_code=404)
        for image_name in removed_images:
            (IMAGES_DIR / image_name).unlink(missing_ok=True)
        if edit_request:
            await run_in_threadpool(repo.consume_edit_request, int(edit_request["id"]))
        await run_in_threadpool(repo.audit, user, "order.update", str(order_id), client_ip(request))
    except ValueError as exc:
        record = _editable_order(order_id)
        return templates.TemplateResponse(
            request, "order_edit.html",
            page_context(request, order=record, catalogs=import_catalogs(), error=str(exc), edit_request=edit_request),
            status_code=422,
        )
    return RedirectResponse(f"/orders/{order_id}", status_code=303)

@app.post("/orders/{order_id}/edit-request")
async def request_order_edit(request: Request, order_id: int):
    user, denied = require_page(request, {"sales", "finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    reason = str(form.get("reason") or "").strip()
    try:
        request_id = await run_in_threadpool(repo.create_edit_request, order_id, user, reason)
        await run_in_threadpool(
            repo.audit,
            user,
            "order.edit_request.create",
            f"{request_id}:{order_id}",
            client_ip(request),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "error.html",
            page_context(request, status=400, message=str(exc)),
            status_code=400,
        )
    return RedirectResponse("/finance/receivables" if user["role"] == "finance" else "/orders", status_code=303)


@app.post("/orders/{order_id}/replenishment-request")
async def request_order_replenishment(request: Request, order_id: int):
    user, denied = require_page(request, {"production"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    try:
        request_id = await run_in_threadpool(
            repo.create_replenishment_request,
            order_id,
            user,
            as_int(form.get("quantity")),
        )
        await run_in_threadpool(
            repo.audit,
            user,
            "order.replenishment_request.create",
            f"{request_id}:{order_id}",
            client_ip(request),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "error.html",
            page_context(request, status=400, message=str(exc)),
            status_code=400,
        )
    return RedirectResponse("/production", status_code=303)

@app.post("/orders/{order_id}/ship")
async def ship_order(request: Request, order_id: int):
    user, denied = require_page(request, {"sales"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    record = await run_in_threadpool(repo.get_order, order_id)
    if not record:
        return Response(status_code=404)
    if sales_order_forbidden(user, record):
        return Response(status_code=403)
    shipped = str(form.get("shipped") or "") == "1"
    await run_in_threadpool(repo.set_order_shipped, order_id, shipped)
    await run_in_threadpool(repo.audit, user, "order.ship", f"{order_id}:{int(shipped)}", client_ip(request))
    return RedirectResponse("/orders", status_code=303)

@app.post("/orders/{order_id}/delete")
async def delete_order(request: Request, order_id: int):
    user, denied = require_page(request, {"admin"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    try:
        order_no = await run_in_threadpool(repo.delete_order, order_id)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "error.html",
            page_context(request, status=409, message=str(exc)),
            status_code=409,
        )
    await run_in_threadpool(repo.audit, user, "order.delete", order_no, client_ip(request))
    return RedirectResponse("/orders", status_code=303)


@app.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(request: Request, order_id: int, created: int = 0):
    user, denied = require_page(request)
    if denied:
        return denied
    record = repo.get_order(order_id)
    if not record:
        return templates.TemplateResponse(
            request, "error.html", page_context(request, status=404, message="订单不存在"), status_code=404
        )
    if sales_order_forbidden(user, record):
        return templates.TemplateResponse(
            request, "error.html", page_context(request, status=403, message="forbidden"), status_code=403
        )
    for key in ("materials_json", "plating_json", "accessories_json", "polishing_json",
                "coloring_json", "resin_json", "packaging_json", "image_paths_json"):
        record[key] = loads_json(record.get(key) or "[]")
    outsource_records = repo.order_outsource_records(order_id)
    return templates.TemplateResponse(
        request,
        "order_detail.html",
        page_context(
            request,
            order=record,
            created=bool(created),
            outsource_records=outsource_records,
        ),
    )


@app.get("/images/{image_name}")
def product_image(request: Request, image_name: str):
    user, denied = require_page(request)
    if denied:
        return denied
    safe_name = safe_image_name(image_name)
    if not safe_name or not image_is_visible_to_user(safe_name, user):
        return Response(status_code=404)
    target = IMAGES_DIR / safe_name
    if not target.is_file():
        return Response(status_code=404)
    return FileResponse(target)


@app.get("/orders/{order_id}/pdf")
async def order_pdf(request: Request, order_id: int):
    user, denied = require_page(request)
    if denied:
        return denied
    record = await run_in_threadpool(repo.get_order, order_id)
    if not record:
        return Response(status_code=404)
    if sales_order_forbidden(user, record):
        return Response(status_code=403)
    content = await run_in_threadpool(render_order_pdf, record)
    safe_name = str(record.get("order_no") or order_id).replace("/", "-")
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}.pdf"'},
    )


@app.post("/api/import-order")
async def import_order(request: Request):
    user, denied = require_page(request, {"sales"})
    if denied:
        return JSONResponse({"error": "未登录或无权限"}, status_code=401)
    if not valid_csrf(request.session, request.headers.get("x-csrf-token", "")):
        return JSONResponse({"error": "页面已过期，请刷新后重试"}, status_code=400)
    form = await request.form()
    upload = form.get("file")
    supplemental_prompt = str(form.get("supplemental_prompt", "")).strip()
    if not isinstance(upload, UploadFile) or not upload.filename:
        return JSONResponse({"error": "请选择客单文件"}, status_code=400)
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {".docx", ".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".html", ".htm", ".pdf"}:
        return JSONResponse({"error": "仅支持 DOCX、Excel、CSV、TSV、HTML 和 PDF"}, status_code=415)
    target = TMP_DIR / f"{uuid4().hex}{suffix}"
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise OrderImportError("客单文件过大")
                output.write(chunk)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        async with ai_slots:
            data = await run_in_threadpool(
                analyze_order_document,
                target,
                api_key,
                import_catalogs(),
                supplemental_prompt,
            )
        await run_in_threadpool(repo.audit, user, "order.ai_import", upload.filename, client_ip(request))
        return {"data": data}
    except OrderImportError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    finally:
        target.unlink(missing_ok=True)


@app.get("/finance", response_class=HTMLResponse)
def finance(request: Request):
    _, denied = require_page(request, {"finance"})
    if denied:
        return denied
    return RedirectResponse("/finance/receivables", status_code=303)


@app.get("/finance/receivables", response_class=HTMLResponse)
def finance_receivables(
    request: Request,
    receivable_q: str = "",
    receivable_date_from: str = "",
    receivable_date_to: str = "",
    receivable_paid_status: str = "",
    receivable_page: int = 1,
):
    _, denied = require_page(request, {"finance"})
    if denied:
        return denied
    receivables = repo.finance_orders(
        receivable_q, receivable_date_from, receivable_date_to, receivable_paid_status, receivable_page
    )
    return templates.TemplateResponse(
        request,
        "finance.html",
        page_context(
            request,
            active_finance_page="receivables",
            receivables=receivables,
            payables=None,
            factories=[],
            receivable_q=receivable_q,
            receivable_date_from=receivable_date_from,
            receivable_date_to=receivable_date_to,
            receivable_paid_status=receivable_paid_status,
            payable_q="",
            payable_factory="",
            payable_date_from="",
            payable_date_to="",
        ),
    )


@app.get("/finance/payables", response_class=HTMLResponse)
def finance_payables(
    request: Request,
    payable_q: str = "",
    payable_factory: str = "",
    payable_date_from: str = "",
    payable_date_to: str = "",
    payable_page: int = 1,
):
    user, denied = require_page(request, {"finance", "outsource"})
    if denied:
        return denied
    payables = repo.finance_outsource_records(
        payable_q, payable_factory, payable_date_from, payable_date_to, payable_page
    )
    return templates.TemplateResponse(
        request,
        "finance.html",
        page_context(
            request,
            active_finance_page="payables",
            receivables=None,
            payables=payables,
            factories=repo.finance_factory_names(),
            receivable_q="",
            receivable_date_from="",
            receivable_date_to="",
            receivable_paid_status="",
            payable_q=payable_q,
            payable_factory=payable_factory,
            payable_date_from=payable_date_from,
            payable_date_to=payable_date_to,
            can_update_payables=user["role"] in {"admin", "finance"},
        ),
    )


@app.post("/finance/receivables/status")
async def finance_receivables_status(request: Request):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    ids = selected_ids(form, "selected_ids")
    paid = form.get("paid") == "1"
    changed = await run_in_threadpool(repo.set_order_paid_many, ids, paid)
    await run_in_threadpool(
        repo.audit, user, "finance.receivables.status",
        f"{changed}:{int(paid)}", client_ip(request),
    )
    return RedirectResponse("/finance/receivables", status_code=303)


@app.post("/finance/receivables/invoice")
async def finance_receivables_invoice(request: Request):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    ids = selected_ids(form, "selected_ids")
    invoiced = form.get("invoiced") == "1"
    changed = await run_in_threadpool(repo.set_order_invoice_many, ids, invoiced)
    await run_in_threadpool(
        repo.audit, user, "finance.receivables.invoice",
        f"{changed}:{int(invoiced)}", client_ip(request),
    )
    return RedirectResponse("/finance/receivables", status_code=303)


@app.post("/finance/payables/status")
async def finance_payables_status(request: Request):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    ids = selected_ids(form, "selected_ids")
    paid = form.get("paid") == "1"
    changed = await run_in_threadpool(repo.set_outsource_paid_many, ids, paid)
    await run_in_threadpool(
        repo.audit, user, "finance.payables.status",
        f"{changed}:{int(paid)}", client_ip(request),
    )
    return RedirectResponse("/finance/payables", status_code=303)


@app.post("/finance/receivables/export")
async def finance_receivables_export(request: Request):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    rows = await run_in_threadpool(repo.finance_order_rows, selected_ids(form, "selected_ids"))
    if not rows:
        return Response("请至少选择一条收款记录", status_code=400)
    data = [[
        row["order_no"], row.get("customer_name") or "", row.get("bi_no") or "",
        row.get("production_no") or "", row.get("product_name") or "",
        row.get("quantity") or 0,
        row.get("quantity_unit") or "", row.get("unit_price") or 0,
        row.get("extra_fee") or 0, row.get("amount") or 0,
        row.get("order_date") or "", "已收款" if row.get("paid_status") else "未收款",
    ] for row in rows]
    await run_in_threadpool(
        repo.audit, user, "finance.receivables.export", str(len(rows)), client_ip(request)
    )
    return await run_in_threadpool(
        excel_response,
        "客户收款",
        ["订单号", "客户名称", "PO号", "生产制号", "产品", "数量", "单位", "单价", "附加费", "应收金额", "订单日期", "收款状态"],
        data,
        "receivables",
    )


@app.post("/finance/receivables/pdf")
async def finance_receivables_pdf(request: Request):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    ids = selected_ids(form, "selected_ids")
    rows = await run_in_threadpool(repo.order_pdf_rows, ids)
    if not rows:
        return Response("Please select at least one order", status_code=400)
    content = await run_in_threadpool(merge_order_pdfs, rows)
    await run_in_threadpool(
        repo.audit, user, "finance.receivables.pdf", str(len(rows)), client_ip(request)
    )
    filename = f"orders_{date.today().strftime('%Y%m%d')}.pdf"
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/finance/payables/export")
async def finance_payables_export(request: Request):
    user, denied = require_page(request, {"finance", "outsource"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    rows = await run_in_threadpool(repo.finance_outsource_rows, selected_ids(form, "selected_ids"))
    if not rows:
        return Response("请至少选择一条付款记录", status_code=400)
    data = [[
        row["order_no"], row.get("product_name") or "", row.get("process_name") or "",
        row.get("factory_name") or "", row.get("product_quantity") or 0,
        row.get("spare_quantity") or 0, row.get("quantity") or 0,
        row.get("unit_price") or 0, row.get("processing_fee") or 0,
        row.get("length_mm") or 0, row.get("width_mm") or 0, row.get("thickness_mm") or 0,
        row.get("density") or 0, row.get("weight") or 0,
        row.get("material_unit_price") or 0, row.get("color_count"),
        row.get("plate_fee") or 0, row.get("amount"),
        row.get("outsource_date") or "", "已付款" if row.get("paid_status") else "未付款",
        row.get("remark") or "",
    ] for row in rows]
    await run_in_threadpool(
        repo.audit, user, "finance.payables.export", str(len(rows)), client_ip(request)
    )
    return await run_in_threadpool(
        excel_response,
        "加工厂付款",
        ["订单号", "产品", "工艺", "加工厂", "产品数量", "备品数量", "合计数量", "加工单价",
         "加工费", "长mm", "宽mm", "厚mm", "密度", "重量", "材料单价", "颜色数量",
         "版费", "金额", "外发日期", "付款状态", "备注"],
        data,
        "payables",
    )


@app.post("/finance/{order_id}/paid")
async def finance_paid(request: Request, order_id: int):
    user, denied = require_page(request, {"finance"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    paid = form.get("paid") == "1"
    await run_in_threadpool(repo.set_order_paid, order_id, paid)
    await run_in_threadpool(repo.audit, user, "finance.paid", f"{order_id}:{int(paid)}", client_ip(request))
    return RedirectResponse("/finance/receivables", status_code=303)

@app.get("/outsource", response_class=HTMLResponse)
def outsource(request: Request, q: str = "", page: int = 1, created: int = 0):
    _, denied = require_page(request, {"outsource"})
    if denied:
        return denied
    return templates.TemplateResponse(
        request, "outsource.html",
        page_context(
            request,
            result=repo.outsource_records(q, page),
            q=q,
            orders=repo.lookup_orders(),
            processes=repo.processes(),
            factories=repo.factories(),
            today=date.today().isoformat(),
            error="",
            created=max(0, created),
        ),
    )


@app.get("/outsource/history")
def outsource_history(request: Request, order_no: str = "", process_name: str = ""):
    _, denied = require_page(request, {"outsource"})
    if denied:
        return denied
    record = repo.latest_outsource_for_order_process(order_no, process_name)
    return JSONResponse({"record": record})


@app.get("/outsource/{record_id}/edit", response_class=HTMLResponse)
def edit_outsource_page(request: Request, record_id: int):
    _, denied = require_page(request, {"admin"})
    if denied:
        return denied
    record = repo.get_outsource_record(record_id)
    if not record:
        return Response(status_code=404)
    return templates.TemplateResponse(
        request, "outsource_edit.html",
        page_context(
            request, record=record, processes=repo.processes(), factories=repo.factories(), error=""
        ),
    )


@app.post("/outsource/{record_id}/edit", response_class=HTMLResponse)
async def edit_outsource(request: Request, record_id: int):
    user, denied = require_page(request, {"admin"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    record = repo.get_outsource_record(record_id)
    if not record:
        return Response(status_code=404)
    try:
        payload = outsource_edit_payload(form)
        valid_factories = {
            str(row.get("factory_name") or "").strip()
            for row in repo.factories(payload["process_name"])
        }
        if payload["factory_name"] not in valid_factories:
            raise ValueError("所选加工厂不属于当前工序")
        if not await run_in_threadpool(repo.update_outsource_record, record_id, payload):
            return Response(status_code=404)
        await run_in_threadpool(repo.audit, user, "outsource.update", str(record_id), client_ip(request))
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "outsource_edit.html",
            page_context(
                request, record=record, processes=repo.processes(), factories=repo.factories(), error=str(exc)
            ),
            status_code=422,
        )
    return RedirectResponse("/outsource", status_code=303)


@app.post("/outsource/{record_id}/delete")
async def delete_outsource(request: Request, record_id: int):
    user, denied = require_page(request, {"admin", "outsource"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)
    try:
        order_no = await run_in_threadpool(repo.delete_outsource_record, record_id)
    except ValueError as exc:
        return Response(str(exc), status_code=404)
    await run_in_threadpool(repo.audit, user, "outsource.delete", order_no, client_ip(request))
    return RedirectResponse("/outsource", status_code=303)


@app.post("/outsource")
async def create_outsource(request: Request):
    user, denied = require_page(request, {"outsource"})
    if denied:
        return denied
    form = await request.form()
    if not valid_form_csrf(request, str(form.get("csrf") or "")):
        return Response(status_code=400)

    process_name = str(form.get("process_name") or "").strip()
    factory_name = str(form.get("factory_name") or "").strip()
    outsource_date = str(form.get("outsource_date") or date.today().isoformat()).strip()
    order_nos = form.getlist("order_no")
    product_quantities = form.getlist("product_quantity")
    spare_quantities = form.getlist("spare_quantity")
    unit_prices = form.getlist("unit_price")
    processing_fees = form.getlist("processing_fee")
    lengths = form.getlist("length_mm")
    widths = form.getlist("width_mm")
    thicknesses = form.getlist("thickness_mm")
    densities = form.getlist("density")
    weights = form.getlist("weight")
    color_counts = form.getlist("color_count")
    plate_fees = form.getlist("plate_fee")
    manual_amounts = form.getlist("manual_amount")
    flag_types = form.getlist("flag_type")
    remarks = form.getlist("remark")

    def item(values: list[Any], index: int, default: Any = "") -> Any:
        return values[index] if index < len(values) else default

    rows: list[dict[str, Any]] = []
    for index, raw_order_no in enumerate(order_nos):
        order_no = str(raw_order_no or "").strip()
        if not order_no:
            continue
        flag_type = str(item(flag_types, index))
        manual_amount = str(item(manual_amounts, index)).strip()
        rows.append({
            "order_no": order_no,
            "product_quantity": as_float(item(product_quantities, index)),
            "spare_quantity": as_float(item(spare_quantities, index)),
            "unit_price": as_float(item(unit_prices, index)),
            "processing_fee": as_float(item(processing_fees, index)),
            "length_mm": as_float(item(lengths, index)),
            "width_mm": as_float(item(widths, index)),
            "thickness_mm": as_float(item(thicknesses, index)),
            "density": as_float(item(densities, index), 0.00785),
            "weight": as_float(item(weights, index), 0.0055),
            "color_count": str(item(color_counts, index)).strip(),
            "plate_fee": as_float(item(plate_fees, index)),
            "manual_amount": as_float(manual_amount) if manual_amount else None,
            "remark": str(item(remarks, index)).strip(),
            "remake_flag": int(flag_type == "remake"),
            "replenishment_flag": int(flag_type == "replenishment"),
        })

    shared = {
        "process_name": process_name,
        "factory_name": factory_name,
        "outsource_date": outsource_date,
        "length_mm": 0,
        "width_mm": 0,
        "thickness_mm": 0,
        "density": 0.00785,
        "weight": 0.0055,
        "material_unit_price": 0,
        "color_count": None,
        "plate_fee": 0,
        "paid_status": 0,
    }
    try:
        if not process_name or not factory_name:
            raise ValueError("工序和加工厂不能为空")
        factory_rows = await run_in_threadpool(repo.factories, process_name)
        valid_factories = {str(row.get("factory_name") or "").strip() for row in factory_rows}
        if factory_name not in valid_factories:
            raise ValueError("所选加工厂不属于当前工序，请重新选择")
        record_ids = await run_in_threadpool(repo.create_outsource_batch, shared, rows)
        await run_in_threadpool(
            repo.audit,
            user,
            "outsource.batch_create",
            f"{factory_name}:{len(record_ids)}",
            client_ip(request),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "outsource.html",
            page_context(
                request,
                result=repo.outsource_records(),
                q="",
                orders=repo.lookup_orders(),
                processes=repo.processes(),
                factories=repo.factories(),
                today=outsource_date or date.today().isoformat(),
                error=str(exc),
                created=0,
            ),
            status_code=422,
        )
    return RedirectResponse(f"/outsource?created={len(record_ids)}", status_code=303)



