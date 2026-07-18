from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from order_system.database import Database

from .security import hash_password, verify_password


REQUIRED_WEB_PROCESSES = ["冲压", "上色", "印刷/UV"]

ORDER_COLUMNS = [
    "order_type", "salesman", "order_no", "product_name", "order_date",
    "delivery_date", "quantity", "spare_quantity", "quantity_unit", "unit_price", "extra_fee",
    "paid_status", "shipped_status", "invoice_status", "order_prefix_no", "customer_code", "customer_name",
    "production_no", "bi_no", "width_mm",
    "height_mm", "thickness_mm", "size_as_sample", "materials_json",
    "material_note", "material_note_red", "plating_json", "plating_note",
    "plating_note_red", "accessories_json", "accessories_note",
    "accessories_note_red", "polishing_json", "polishing_note",
    "polishing_note_red", "coloring_json", "coloring_text", "coloring_note",
    "coloring_note_red", "resin_json", "resin_note", "resin_note_red",
    "packaging_json", "packaging_rule", "packaging_note", "packaging_note_red",
    "back_mode", "back_mode_note", "back_mode_note_red", "global_note",
    "global_note_red", "image_paths_json",
]


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.legacy = Database(db_path)

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        self.legacy.initialize()
        with self.connect(write=True) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'sales',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS order_edit_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    order_no TEXT NOT NULL,
                    requester_id INTEGER NOT NULL,
                    requester_name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewer_id INTEGER,
                    reviewer_name TEXT,
                    review_note TEXT,
                    reviewed_at TEXT,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
                );                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    action TEXT NOT NULL,
                    detail TEXT,
                    ip TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_orders_lookup
                    ON orders(order_no, order_date, id);
                CREATE INDEX IF NOT EXISTS idx_outsource_lookup
                    ON outsource_records(order_no, process_name, factory_name, outsource_date);
                CREATE INDEX IF NOT EXISTS idx_audit_created_at
                    ON audit_log(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_order_edit_requests_status
                    ON order_edit_requests(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_order_edit_requests_order_user
                    ON order_edit_requests(order_id, requester_id, status, consumed_at);                """
            )
            existing_user_columns = {row[1] for row in conn.execute("PRAGMA table_info(web_users)").fetchall()}
            if "display_name" not in existing_user_columns:
                conn.execute("ALTER TABLE web_users ADD COLUMN display_name TEXT")
            conn.execute(
                "UPDATE web_users SET display_name = username "
                "WHERE display_name IS NULL OR TRIM(display_name) = ''"
            )
            conn.execute(
                """UPDATE order_edit_requests
                   SET requester_name = (
                       SELECT COALESCE(NULLIF(display_name, ''), username)
                       FROM web_users WHERE web_users.id = order_edit_requests.requester_id
                   )
                   WHERE EXISTS (SELECT 1 FROM web_users WHERE web_users.id = order_edit_requests.requester_id)"""
            )
            conn.execute(
                """UPDATE order_edit_requests
                   SET reviewer_name = (
                       SELECT COALESCE(NULLIF(display_name, ''), username)
                       FROM web_users WHERE web_users.id = order_edit_requests.reviewer_id
                   )
                   WHERE reviewer_id IS NOT NULL
                     AND EXISTS (SELECT 1 FROM web_users WHERE web_users.id = order_edit_requests.reviewer_id)"""
            )
            conn.executemany(
                "INSERT OR IGNORE INTO outsource_processes (process_name) VALUES (?)",
                [(name,) for name in REQUIRED_WEB_PROCESSES],
            )
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA wal_autocheckpoint=500")

    def list_customers(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT code, name FROM customers WHERE active = 1 ORDER BY code"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _customer_for_code(conn: sqlite3.Connection, code: int) -> sqlite3.Row:
        row = conn.execute(
            "SELECT code, name FROM customers WHERE code = ? AND active = 1", (code,)
        ).fetchone()
        if not row:
            raise ValueError("请选择客户名称列表中的有效客户")
        return row

    def user_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM web_users").fetchone()[0])

    def create_user(self, username: str, password: str, role: str = "sales", display_name: str = "") -> int:
        username = username.strip()
        display_name = display_name.strip() or username
        if not username or len(password) < 10:
            raise ValueError("用户名不能为空，密码至少需要 10 位")
        if role not in {"admin", "sales", "finance", "outsource"}:
            raise ValueError("无效角色")
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                "INSERT INTO web_users (username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, display_name, hash_password(password), role),
            )
            return int(cursor.lastrowid)

    def set_password(self, username: str, password: str) -> None:
        username = username.strip()
        if not username or len(password) < 10:
            raise ValueError("用户名不能为空，密码至少需要 10 位")
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                "UPDATE web_users SET password_hash = ? WHERE username = ?",
                (hash_password(password), username),
            )
            if cursor.rowcount != 1:
                raise ValueError("账号不存在")
    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM web_users WHERE username = ? AND active = 1",
                (username.strip(),),
            ).fetchone()
        if not row or not verify_password(password, str(row["password_hash"])):
            return None
        user = dict(row)
        with self.connect(write=True) as conn:
            conn.execute(
                "UPDATE web_users SET last_login_at = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), user["id"]),
            )
        return user

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, username, COALESCE(NULLIF(display_name, ''), username) AS display_name, role, active FROM web_users WHERE id = ? AND active = 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def audit(self, user: dict[str, Any], action: str, detail: str = "", ip: str = "") -> None:
        with self.connect(write=True) as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, username, action, detail, ip) VALUES (?, ?, ?, ?, ?)",
                (user.get("id"), user.get("username"), action, detail[:1000], ip[:100]),
            )

    def dashboard(self) -> dict[str, Any]:
        today = datetime.now().date().isoformat()
        with self.connect() as conn:
            order_count = int(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
            today_count = int(conn.execute(
                "SELECT COUNT(*) FROM orders WHERE order_date = ?", (today,)
            ).fetchone()[0])
            unpaid_count = int(conn.execute(
                "SELECT COUNT(*) FROM orders WHERE paid_status = 0"
            ).fetchone()[0])
            outsource_unpaid = int(conn.execute(
                "SELECT COUNT(*) FROM outsource_records WHERE paid_status = 0"
            ).fetchone()[0])
            recent = conn.execute(
                "SELECT id, order_no, product_name, salesman, delivery_date FROM orders "
                "ORDER BY id DESC LIMIT 8"
            ).fetchall()
        return {
            "order_count": order_count,
            "today_count": today_count,
            "unpaid_count": unpaid_count,
            "outsource_unpaid": outsource_unpaid,
            "recent": [dict(row) for row in recent],
        }

    def pending_edit_request_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM order_edit_requests WHERE status = 'pending'"
            ).fetchone()[0])

    def list_edit_requests(self, status: str = "pending", requester_id: int | None = None) -> list[dict[str, Any]]:
        status = status.strip()
        user_filter = "" if requester_id is None else " AND r.requester_id = ?"
        args: list[Any] = [status, status]
        if requester_id is not None:
            args.append(int(requester_id))
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT r.*, o.product_name, o.customer_name, o.salesman
                    FROM order_edit_requests r
                    LEFT JOIN orders o ON o.id = r.order_id
                    WHERE (? = '' OR r.status = ?){user_filter}
                    ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                             r.created_at DESC, r.id DESC
                    LIMIT 200""",
                args,
            ).fetchall()
        return [dict(row) for row in rows]
    def create_edit_request(self, order_id: int, user: dict[str, Any], reason: str) -> int:
        reason = reason.strip()
        if not reason:
            raise ValueError("请填写修改原因")
        if len(reason) > 1000:
            raise ValueError("修改原因不能超过 1000 个字")
        with self.connect(write=True) as conn:
            order = conn.execute(
                "SELECT id, order_no, salesman FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if not order:
                raise ValueError("订单不存在")
            if str(user.get("role") or "") == "sales":
                user_names = {
                    str(user.get("username") or "").strip(),
                    str(user.get("display_name") or "").strip(),
                }
                if str(order["salesman"] or "").strip() not in user_names:
                    raise ValueError("只能申请修改自己的订单")
            existing = conn.execute(
                """SELECT id FROM order_edit_requests
                   WHERE order_id = ? AND requester_id = ? AND status = 'pending'
                   LIMIT 1""",
                (order_id, int(user.get("id") or 0)),
            ).fetchone()
            if existing:
                raise ValueError("这张订单已有待审批的修改申请")
            cursor = conn.execute(
                """INSERT INTO order_edit_requests
                   (order_id, order_no, requester_id, requester_name, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (order_id, str(order["order_no"]), int(user.get("id") or 0), str(user.get("display_name") or user.get("username") or ""), reason),
            )
            return int(cursor.lastrowid)

    def review_edit_request(
        self,
        request_id: int,
        admin: dict[str, Any],
        approved: bool,
        note: str = "",
    ) -> str:
        status = "approved" if approved else "rejected"
        with self.connect(write=True) as conn:
            row = conn.execute(
                "SELECT * FROM order_edit_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if not row:
                raise ValueError("申请不存在")
            if str(row["status"]) != "pending":
                raise ValueError("该申请已处理")
            conn.execute(
                """UPDATE order_edit_requests
                   SET status = ?, reviewer_id = ?, reviewer_name = ?, review_note = ?,
                       reviewed_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (status, int(admin.get("id") or 0), str(admin.get("display_name") or admin.get("username") or ""), note.strip()[:1000], request_id),
            )
            return str(row["order_no"])

    def edit_request_for_edit(self, request_id: int, order_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM order_edit_requests
                   WHERE id = ? AND order_id = ? AND requester_id = ?
                     AND status = 'approved' AND consumed_at IS NULL
                   LIMIT 1""",
                (request_id, order_id, user_id),
            ).fetchone()
        return dict(row) if row else None
    def approved_edit_request(self, order_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM order_edit_requests
                   WHERE order_id = ? AND requester_id = ? AND status = 'approved'
                     AND consumed_at IS NULL
                   ORDER BY reviewed_at DESC, id DESC LIMIT 1""",
                (order_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def approved_edit_order_ids(self, user_id: int) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT order_id FROM order_edit_requests
                   WHERE requester_id = ? AND status = 'approved' AND consumed_at IS NULL""",
                (user_id,),
            ).fetchall()
        return {int(row[0]) for row in rows}

    def consume_edit_request(self, request_id: int) -> None:
        with self.connect(write=True) as conn:
            conn.execute(
                "UPDATE order_edit_requests SET consumed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (request_id,),
            )
    def list_orders(
        self,
        keyword: str = "",
        page: int = 1,
        page_size: int = 30,
        salesman: str | None = None,
    ) -> dict[str, Any]:
        keyword = keyword.strip()
        salesman = salesman.strip() if salesman is not None else None
        page = max(page, 1)
        offset = (page - 1) * page_size
        where = "WHERE (? = '' OR order_no LIKE ? OR customer_name LIKE ? OR product_name LIKE ? OR salesman LIKE ? OR bi_no LIKE ? OR production_no LIKE ?)"
        like = f"%{keyword}%"
        args: list[Any] = [keyword, like, like, like, like, like, like]
        if salesman:
            where += " AND salesman = ?"
            args.append(salesman)
        with self.connect() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM orders {where}", args).fetchone()[0])
            rows = conn.execute(
                f"""SELECT id, order_no, customer_code, customer_name, product_name,
                           order_type, salesman, bi_no, production_no, quantity, spare_quantity, quantity_unit, order_date,
                           delivery_date, paid_status, shipped_status
                    FROM orders {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
                (*args, page_size, offset),
            ).fetchall()
        return {"rows": [dict(row) for row in rows], "total": total, "page": page,
                "pages": max(1, (total + page_size - 1) // page_size)}

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        return self.legacy.get_order(order_id)

    @staticmethod
    def _next_order_no(conn: sqlite3.Connection, order_date: str, prefix_no: int) -> str:
        sequence = int(conn.execute(
            "SELECT COUNT(*) + 1 FROM orders WHERE order_date = ?", (order_date,)
        ).fetchone()[0])
        suffix = order_date[2:].replace("-", "")
        while True:
            order_no = f"TWD{prefix_no}-{suffix}{sequence:03d}"
            exists = conn.execute(
                "SELECT 1 FROM orders WHERE order_no = ? LIMIT 1", (order_no,)
            ).fetchone()
            if not exists:
                return order_no
            sequence += 1

    def preview_order_no(self, order_date: str, order_prefix_no: int = 1) -> str:
        order_date = str(order_date or "").strip()
        prefix_no = int(order_prefix_no or 0)
        with self.connect() as conn:
            self._customer_for_code(conn, prefix_no)
            return self._next_order_no(conn, order_date, prefix_no)

    def create_order(self, payload: dict[str, Any]) -> tuple[int, str]:
        order_date = str(payload.get("order_date") or "").strip()
        if not order_date:
            raise ValueError("下单日期不能为空")
        prefix_no = int(payload.get("customer_code") or payload.get("order_prefix_no") or 0)
        requested_order_no = str(payload.get("order_no") or "").strip()
        if len(requested_order_no) > 100:
            raise ValueError("订单编号不能超过 100 个字符")
        with self.connect(write=True) as conn:
            customer = self._customer_for_code(conn, prefix_no)
            expected_prefix = f"TWD{prefix_no}-"
            if requested_order_no and not requested_order_no.startswith(expected_prefix):
                raise ValueError(f"订单编号必须以 {expected_prefix} 开头")
            order_no = requested_order_no or self._next_order_no(conn, order_date, prefix_no)
            payload["order_no"] = order_no
            payload["order_prefix_no"] = prefix_no
            payload["customer_code"] = prefix_no
            payload["customer_name"] = str(customer["name"])
            required_defaults = {
                "quantity_unit": "个", "spare_quantity": 0, "paid_status": 0, "shipped_status": 0, "invoice_status": 0, "order_prefix_no": prefix_no,
                "size_as_sample": 0, "materials_json": "[]", "plating_json": "[]",
                "accessories_json": "[]", "polishing_json": "[]", "coloring_json": "[]",
                "resin_json": "[]", "packaging_json": "[]", "image_paths_json": "[]",
                "material_note_red": 1, "plating_note_red": 1, "accessories_note_red": 1,
                "polishing_note_red": 1, "coloring_note_red": 1, "resin_note_red": 1,
                "packaging_note_red": 1, "back_mode_note_red": 1, "global_note_red": 1,
            }
            values = [required_defaults.get(col) if payload.get(col) is None and col in required_defaults else payload.get(col)
                      for col in ORDER_COLUMNS]
            placeholders = ", ".join("?" for _ in ORDER_COLUMNS)
            cursor = conn.execute(
                f"INSERT INTO orders ({', '.join(ORDER_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid), order_no

    def update_order(self, order_id: int, payload: dict[str, Any]) -> bool:
        assignments = ", ".join(f"{column} = ?" for column in ORDER_COLUMNS)
        with self.connect(write=True) as conn:
            prefix_no = int(payload.get("customer_code") or payload.get("order_prefix_no") or 0)
            customer = self._customer_for_code(conn, prefix_no)
            payload["order_prefix_no"] = prefix_no
            payload["customer_code"] = prefix_no
            payload["customer_name"] = str(customer["name"])
            values = [payload.get(column) for column in ORDER_COLUMNS]
            cursor = conn.execute(
                f"UPDATE orders SET {assignments} WHERE id = ?",
                (*values, order_id),
            )
            return cursor.rowcount == 1

    def delete_order(self, order_id: int) -> str:
        with self.connect(write=True) as conn:
            row = conn.execute(
                "SELECT order_no FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if not row:
                raise ValueError("订单不存在")
            linked = int(conn.execute(
                "SELECT COUNT(*) FROM outsource_records WHERE order_id = ?", (order_id,)
            ).fetchone()[0])
            if linked:
                raise ValueError(
                    f"该订单存在 {linked} 条外发记录，请先删除外发记录"
                )
            conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            return str(row["order_no"])

    def finance_orders(
        self,
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        paid_status: str = "",
        page: int = 1,
        page_size: int = 40,
    ) -> dict[str, Any]:
        keyword = keyword.strip()
        date_from = date_from.strip()
        date_to = date_to.strip()
        paid_status = paid_status.strip()
        page = max(page, 1)
        offset = (page - 1) * page_size
        where = """WHERE (? = '' OR order_no LIKE ? OR customer_name LIKE ? OR bi_no LIKE ? OR production_no LIKE ?)
                   AND (? = '' OR order_date >= ?)
                   AND (? = '' OR order_date <= ?)"""
        like = f"%{keyword}%"
        args: list[Any] = [keyword, like, like, like, like, date_from, date_from, date_to, date_to]
        if paid_status in {"paid", "unpaid"}:
            where += " AND paid_status = ?"
            args.append(1 if paid_status == "paid" else 0)
        amount_sql = "(COALESCE(quantity, 0) * COALESCE(unit_price, 0) + COALESCE(extra_fee, 0))"
        with self.connect() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM orders {where}", args).fetchone()[0])
            unpaid_total = float(conn.execute(
                f"SELECT COALESCE(SUM(CASE WHEN paid_status = 0 THEN {amount_sql} ELSE 0 END), 0) FROM orders {where}",
                args,
            ).fetchone()[0] or 0)
            rows = conn.execute(
                f"""SELECT id, order_no, customer_code, customer_name, bi_no,
                           production_no, quantity, quantity_unit,
                           unit_price, extra_fee, paid_status, invoice_status, order_date,
                           {amount_sql} AS amount
                    FROM orders {where} ORDER BY order_date DESC, id DESC LIMIT ? OFFSET ?""",
                (*args, page_size, offset),
            ).fetchall()
        return {"rows": [dict(row) for row in rows], "total": total, "page": page,
                "pages": max(1, (total + page_size - 1) // page_size),
                "unpaid_total": unpaid_total}

    @staticmethod
    def _normalized_ids(values: list[int]) -> list[int]:
        return sorted({int(value) for value in values if int(value) > 0})[:1000]

    def finance_order_rows(self, order_ids: list[int]) -> list[dict[str, Any]]:
        ids = self._normalized_ids(order_ids)
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT id, order_no, customer_code, customer_name, bi_no,
                           production_no, product_name, quantity, quantity_unit,
                           unit_price, extra_fee, paid_status, invoice_status, order_date,
                           (COALESCE(quantity, 0) * COALESCE(unit_price, 0) + COALESCE(extra_fee, 0)) AS amount
                    FROM orders WHERE id IN ({placeholders})
                    ORDER BY order_date DESC, id DESC""",
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def order_pdf_rows(self, order_ids: list[int]) -> list[dict[str, Any]]:
        ids = self._normalized_ids(order_ids)
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM orders WHERE id IN ({placeholders}) ORDER BY order_date DESC, id DESC",
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def set_order_paid_many(self, order_ids: list[int], paid: bool) -> int:
        ids = self._normalized_ids(order_ids)
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                f"UPDATE orders SET paid_status = ? WHERE id IN ({placeholders})",
                (int(paid), *ids),
            )
            return int(cursor.rowcount)

    def set_order_paid(self, order_id: int, paid: bool) -> None:
        self.set_order_paid_many([order_id], paid)

    def set_order_invoice_many(self, order_ids: list[int], invoiced: bool) -> int:
        ids = self._normalized_ids(order_ids)
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                f"UPDATE orders SET invoice_status = ? WHERE id IN ({placeholders})",
                (int(invoiced), *ids),
            )
            return cursor.rowcount

    def set_order_shipped(self, order_id: int, shipped: bool) -> None:
        with self.connect(write=True) as conn:
            conn.execute(
                "UPDATE orders SET shipped_status = ? WHERE id = ?",
                (int(shipped), order_id),
            )
    def outsource_records(self, keyword: str = "", page: int = 1, page_size: int = 40) -> dict[str, Any]:
        keyword = keyword.strip()
        page = max(page, 1)
        offset = (page - 1) * page_size
        where = "WHERE (? = '' OR r.order_no LIKE ? OR r.factory_name LIKE ? OR r.process_name LIKE ?)"
        like = f"%{keyword}%"
        args = (keyword, like, like, like)
        with self.connect() as conn:
            total = int(conn.execute(
                f"SELECT COUNT(*) FROM outsource_records r {where}", args
            ).fetchone()[0])
            rows = conn.execute(
                f"""SELECT r.*, o.product_name FROM outsource_records r
                    LEFT JOIN orders o ON o.id = r.order_id {where}
                    ORDER BY r.id DESC LIMIT ? OFFSET ?""",
                (*args, page_size, offset),
            ).fetchall()
        return {"rows": [dict(row) for row in rows], "total": total, "page": page,
                "pages": max(1, (total + page_size - 1) // page_size)}

    def order_outsource_records(self, order_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.*, o.product_name FROM outsource_records r
                   LEFT JOIN orders o ON o.id = r.order_id
                   WHERE r.order_id = ?
                   ORDER BY r.outsource_date DESC, r.id DESC""",
                (order_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_outsource_record(self, record_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT r.*, o.product_name FROM outsource_records r
                   LEFT JOIN orders o ON o.id = r.order_id WHERE r.id = ?""",
                (record_id,),
            ).fetchone()
        return dict(row) if row else None

    def latest_outsource_for_order_process(self, order_no: str, process_name: str) -> dict[str, Any] | None:
        order_no = order_no.strip()
        process_name = process_name.strip()
        if not order_no or not process_name:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id, order_no, process_name, factory_name, quantity, outsource_date, created_at
                   FROM outsource_records
                   WHERE order_no = ? AND process_name = ?
                     AND COALESCE(remake_flag, 0) = 0
                     AND COALESCE(replenishment_flag, 0) = 0
                   ORDER BY outsource_date DESC, created_at DESC, id DESC
                   LIMIT 1""",
                (order_no, process_name),
            ).fetchone()
        return dict(row) if row else None

    def update_outsource_record(self, record_id: int, payload: dict[str, Any]) -> bool:
        columns = [
            "process_name", "factory_name", "quantity", "product_quantity",
            "spare_quantity", "unit_price", "processing_fee", "length_mm",
            "width_mm", "thickness_mm", "density", "weight",
            "material_unit_price", "color_count", "plate_fee", "outsource_date",
            "remark", "amount", "remake_flag", "replenishment_flag", "paid_status",
        ]
        assignments = ", ".join(f"{column} = ?" for column in columns)
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                f"UPDATE outsource_records SET {assignments} WHERE id = ?",
                (*[payload.get(column) for column in columns], record_id),
            )
            return cursor.rowcount == 1

    def delete_outsource_record(self, record_id: int) -> str:
        with self.connect(write=True) as conn:
            row = conn.execute(
                "SELECT order_no FROM outsource_records WHERE id = ?", (record_id,)
            ).fetchone()
            if not row:
                raise ValueError("外发记录不存在")
            conn.execute("DELETE FROM outsource_records WHERE id = ?", (record_id,))
            return str(row["order_no"])

    def finance_outsource_records(
        self,
        keyword: str = "",
        factory_name: str = "",
        date_from: str = "",
        date_to: str = "",
        page: int = 1,
        page_size: int = 40,
    ) -> dict[str, Any]:
        keyword = keyword.strip()
        factory_name = factory_name.strip()
        date_from = date_from.strip()
        date_to = date_to.strip()
        page = max(page, 1)
        offset = (page - 1) * page_size
        where = """WHERE (? = '' OR r.order_no LIKE ? OR r.process_name LIKE ? OR r.factory_name LIKE ?)
                   AND (? = '' OR r.factory_name = ?)
                   AND (? = '' OR r.outsource_date >= ?)
                   AND (? = '' OR r.outsource_date <= ?)"""
        like = f"%{keyword}%"
        args = (
            keyword, like, like, like, factory_name, factory_name,
            date_from, date_from, date_to, date_to,
        )
        with self.connect() as conn:
            total = int(conn.execute(
                f"SELECT COUNT(*) FROM outsource_records r {where}", args
            ).fetchone()[0])
            rows = conn.execute(
                f"""SELECT r.*, o.product_name FROM outsource_records r
                    LEFT JOIN orders o ON o.id = r.order_id {where}
                    ORDER BY r.outsource_date DESC, r.id DESC LIMIT ? OFFSET ?""",
                (*args, page_size, offset),
            ).fetchall()
        return {"rows": [dict(row) for row in rows], "total": total, "page": page,
                "pages": max(1, (total + page_size - 1) // page_size)}

    def finance_outsource_rows(self, record_ids: list[int]) -> list[dict[str, Any]]:
        ids = self._normalized_ids(record_ids)
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT r.*, o.product_name FROM outsource_records r
                    LEFT JOIN orders o ON o.id = r.order_id
                    WHERE r.id IN ({placeholders})
                    ORDER BY r.outsource_date DESC, r.id DESC""",
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def set_outsource_paid_many(self, record_ids: list[int], paid: bool) -> int:
        ids = self._normalized_ids(record_ids)
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                f"UPDATE outsource_records SET paid_status = ? WHERE id IN ({placeholders})",
                (int(paid), *ids),
            )
            return int(cursor.rowcount)

    def finance_factory_names(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT factory_name FROM outsource_records
                   WHERE TRIM(COALESCE(factory_name, '')) <> '' ORDER BY factory_name"""
            ).fetchall()
        return [str(row[0]) for row in rows]
    def create_outsource(self, payload: dict[str, Any]) -> int:
        columns = [
            "order_id", "order_no", "process_name", "factory_name", "quantity",
            "product_quantity", "spare_quantity", "unit_price", "processing_fee",
            "length_mm", "width_mm", "thickness_mm", "density", "weight",
            "material_unit_price", "color_count", "plate_fee", "outsource_date",
            "remark", "amount", "remake_flag", "replenishment_flag", "paid_status",
        ]
        with self.connect(write=True) as conn:
            cursor = conn.execute(
                f"INSERT INTO outsource_records ({', '.join(columns)}) VALUES "
                f"({', '.join('?' for _ in columns)})",
                [payload.get(col, 0) for col in columns],
            )
            return int(cursor.lastrowid)

    def create_outsource_batch(
        self,
        shared: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> list[int]:
        if not rows:
            raise ValueError("请至少录入一个订单号")
        normalized = [str(row.get("order_no") or "").strip() for row in rows]
        if any(not order_no for order_no in normalized):
            raise ValueError("订单号不能为空")
        if len(normalized) != len(set(normalized)):
            raise ValueError("同一批次中存在重复订单号，请检查扫码结果")

        process_name = str(shared.get("process_name") or "").strip()
        columns = [
            "order_id", "order_no", "process_name", "factory_name", "quantity",
            "product_quantity", "spare_quantity", "unit_price", "processing_fee",
            "length_mm", "width_mm", "thickness_mm", "density", "weight",
            "material_unit_price", "color_count", "plate_fee", "outsource_date",
            "remark", "amount", "remake_flag", "replenishment_flag", "paid_status",
        ]
        placeholders = ", ".join("?" for _ in columns)
        inserted: list[int] = []
        with self.connect(write=True) as conn:
            for row, order_no in zip(rows, normalized):
                order = conn.execute(
                    "SELECT id, order_no FROM orders WHERE order_no = ? ORDER BY id DESC LIMIT 1",
                    (order_no,),
                ).fetchone()
                if not order:
                    raise ValueError(f"订单号不存在：{order_no}")

                product_quantity = float(row.get("product_quantity") or 0)
                spare_quantity = float(row.get("spare_quantity") or 0)
                unit_price = float(row.get("unit_price") or 0)
                quantity = product_quantity + spare_quantity
                if min(product_quantity, spare_quantity, unit_price) < 0 or quantity <= 0:
                    raise ValueError(f"订单 {order_no} 的数量和加工单价必须为非负数，合计数量须大于 0")

                processing_fee = 0.0
                length_mm = width_mm = thickness_mm = 0.0
                density = 0.00785
                weight = 0.0055
                material_unit_price = 0.0
                color_count = None
                plate_fee = 0.0
                amount: float | None

                if process_name == "冲压":
                    processing_fee = float(row.get("processing_fee") or 0)
                    length_mm = float(row.get("length_mm") or 0)
                    width_mm = float(row.get("width_mm") or 0)
                    thickness_mm = float(row.get("thickness_mm") or 0)
                    density = float(row.get("density") or 0.00785)
                    weight = float(row.get("weight") or 0.0055)
                    if min(processing_fee, length_mm, width_mm, thickness_mm, density, weight) < 0:
                        raise ValueError(f"订单 {order_no} 的冲压参数不能为负数")
                    if min(length_mm, width_mm, thickness_mm, density, weight) <= 0:
                        raise ValueError(f"订单 {order_no} 的长、宽、厚、密度和重量必须大于 0")
                    material_unit_price = (
                        (length_mm + 3) * (width_mm + 3) * thickness_mm * density * weight
                    )
                    amount = quantity * (unit_price + material_unit_price) + processing_fee
                elif process_name == "上色":
                    try:
                        color_count = int(row.get("color_count"))
                    except (TypeError, ValueError):
                        raise ValueError(f"订单 {order_no} 必须填写颜色数量") from None
                    if color_count <= 0:
                        raise ValueError(f"订单 {order_no} 的颜色数量必须大于 0")
                    amount = quantity * unit_price * color_count
                elif process_name == "印刷/UV":
                    plate_fee = float(row.get("plate_fee") or 0)
                    if plate_fee < 0:
                        raise ValueError(f"订单 {order_no} 的版费不能为负数")
                    amount = quantity * unit_price + plate_fee
                else:
                    amount = quantity * unit_price

                manual_amount = row.get("manual_amount")
                if manual_amount is not None:
                    manual_amount = float(manual_amount)
                    if manual_amount < 0:
                        raise ValueError(f"Order {order_no} amount cannot be negative")
                    amount = manual_amount

                payload = {
                    **shared,
                    **row,
                    "order_id": int(order["id"]),
                    "order_no": str(order["order_no"]),
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
                    "amount": amount,
                }
                cursor = conn.execute(
                    f"INSERT INTO outsource_records ({', '.join(columns)}) VALUES ({placeholders})",
                    [payload.get(col, 0) for col in columns],
                )
                inserted.append(int(cursor.lastrowid))
        return inserted

    def set_outsource_paid(self, record_id: int, paid: bool) -> None:
        with self.connect(write=True) as conn:
            conn.execute(
                "UPDATE outsource_records SET paid_status = ? WHERE id = ?",
                (int(paid), record_id),
            )

    def lookup_orders(self, keyword: str = "") -> list[dict[str, Any]]:
        keyword = keyword.strip()
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, order_no, product_name, quantity, spare_quantity, quantity_unit,
                          width_mm, height_mm, thickness_mm
                   FROM orders WHERE (? = '' OR order_no LIKE ?)
                   ORDER BY id DESC LIMIT 50""",
                (keyword, f"%{keyword}%"),
            ).fetchall()
        return [dict(row) for row in rows]

    def processes(self) -> list[dict[str, Any]]:
        return self.legacy.list_outsource_processes()

    def factories(self, process_name: str = "") -> list[dict[str, Any]]:
        return self.legacy.list_outsource_factories(process_name)


