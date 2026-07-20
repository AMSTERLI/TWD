import json
import sqlite3
from pathlib import Path
from typing import Any

from order_system.customers import CUSTOMERS


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    code INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_type TEXT NOT NULL,
    salesman TEXT,
    order_no TEXT NOT NULL,
    product_name TEXT,
    order_date TEXT,
    delivery_date TEXT,
    quantity INTEGER,
    spare_quantity INTEGER NOT NULL DEFAULT 0,
    quantity_unit TEXT NOT NULL DEFAULT '\u4e2a',
    unit_price REAL,
    price_tiers_json TEXT NOT NULL DEFAULT '[]',
    extra_fee REAL,
    paid_status INTEGER NOT NULL DEFAULT 0,
    shipped_status INTEGER NOT NULL DEFAULT 0,
    invoice_status INTEGER NOT NULL DEFAULT 0,
    order_prefix_no INTEGER NOT NULL DEFAULT 1,
    customer_code INTEGER,
    customer_name TEXT,
    production_no TEXT,
    bi_no TEXT,
    width_mm TEXT,
    height_mm TEXT,
    thickness_mm TEXT,
    size_as_sample INTEGER NOT NULL DEFAULT 0,
    materials_json TEXT NOT NULL,
    material_note TEXT,
    material_note_red INTEGER NOT NULL DEFAULT 0,
    plating_json TEXT NOT NULL,
    plating_note TEXT,
    plating_note_red INTEGER NOT NULL DEFAULT 0,
    accessories_json TEXT NOT NULL,
    accessories_note TEXT,
    accessories_note_red INTEGER NOT NULL DEFAULT 0,
    polishing_json TEXT NOT NULL,
    polishing_note TEXT,
    polishing_note_red INTEGER NOT NULL DEFAULT 0,
    coloring_json TEXT NOT NULL DEFAULT '[]',
    coloring_text TEXT,
    coloring_note TEXT,
    coloring_note_red INTEGER NOT NULL DEFAULT 0,
    resin_json TEXT NOT NULL,
    resin_note TEXT,
    resin_note_red INTEGER NOT NULL DEFAULT 0,
    packaging_json TEXT NOT NULL,
    packaging_rule TEXT,
    packaging_note TEXT,
    packaging_note_red INTEGER NOT NULL DEFAULT 0,
    back_mode TEXT,
    back_mode_note TEXT,
    back_mode_note_red INTEGER NOT NULL DEFAULT 0,
    global_note TEXT,
    global_note_red INTEGER NOT NULL DEFAULT 0,
    image_paths_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outsource_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    order_no TEXT NOT NULL,
    process_name TEXT NOT NULL,
    factory_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    product_quantity REAL NOT NULL DEFAULT 0,
    spare_quantity REAL NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL,
    processing_fee REAL NOT NULL DEFAULT 0,
    length_mm REAL NOT NULL DEFAULT 0,
    width_mm REAL NOT NULL DEFAULT 0,
    thickness_mm REAL NOT NULL DEFAULT 0,
    density REAL NOT NULL DEFAULT 0.00785,
    weight REAL NOT NULL DEFAULT 0.0055,
    material_unit_price REAL NOT NULL DEFAULT 0,
    color_count INTEGER,
    plate_fee REAL NOT NULL DEFAULT 0,
    outsource_date TEXT,
    remark TEXT,
    amount REAL,
    remake_flag INTEGER NOT NULL DEFAULT 0,
    replenishment_flag INTEGER NOT NULL DEFAULT 0,
    paid_status INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS outsource_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outsource_factories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_name TEXT NOT NULL,
    factory_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_OUTSOURCE_PROCESSES = [
    "压铸",
    "冲压",
    "低温锌合金",
    "咬板",
    "电镀电泳",
    "焊针",
    "抛光",
    "上色",
    "树脂",
    "包装",
    "印刷/UV",
]


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.execute("DROP INDEX IF EXISTS idx_orders_order_no_unique")
            self._ensure_column(conn, "orders", "back_mode_note", "TEXT")
            self._ensure_column(conn, "orders", "coloring_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "orders", "material_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "plating_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "accessories_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "polishing_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "coloring_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "resin_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "packaging_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "back_mode_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "global_note_red", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "spare_quantity", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "quantity_unit", "TEXT NOT NULL DEFAULT '\u4e2a'")
            self._ensure_column(conn, "orders", "unit_price", "REAL")
            self._ensure_column(conn, "orders", "price_tiers_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "orders", "extra_fee", "REAL")
            self._ensure_column(conn, "orders", "paid_status", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "shipped_status", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "invoice_status", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "orders", "order_prefix_no", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "orders", "customer_code", "INTEGER")
            self._ensure_column(conn, "orders", "customer_name", "TEXT")
            self._ensure_column(conn, "orders", "coloring_text", "TEXT")
            self._ensure_column(conn, "outsource_records", "product_quantity", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "spare_quantity", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "processing_fee", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "length_mm", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "width_mm", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "thickness_mm", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "density", "REAL NOT NULL DEFAULT 0.00785")
            self._ensure_column(conn, "outsource_records", "weight", "REAL NOT NULL DEFAULT 0.0055")
            self._ensure_column(conn, "outsource_records", "material_unit_price", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "color_count", "INTEGER")
            self._ensure_column(conn, "outsource_records", "plate_fee", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "outsource_date", "TEXT")
            self._ensure_column(conn, "outsource_records", "remark", "TEXT")
            self._ensure_column(conn, "outsource_records", "amount", "REAL")
            self._ensure_column(conn, "outsource_records", "remake_flag", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "replenishment_flag", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "outsource_records", "paid_status", "INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                UPDATE outsource_records
                SET product_quantity = COALESCE(product_quantity, 0),
                    spare_quantity = CASE
                        WHEN COALESCE(product_quantity, 0) = 0 THEN COALESCE(quantity, 0)
                        ELSE COALESCE(spare_quantity, 0)
                    END
                WHERE COALESCE(product_quantity, 0) = 0 AND COALESCE(spare_quantity, 0) = 0
                """
            )
            conn.execute(
                """
                UPDATE outsource_records
                SET amount = COALESCE(quantity, 0) * COALESCE(unit_price, 0)
                WHERE amount IS NULL
                """
            )
            self._seed_outsource_processes(conn)
            conn.execute(
                "UPDATE outsource_records SET process_name = '印刷/UV' WHERE process_name IN ('印刷', 'UV')"
            )
            conn.execute(
                "UPDATE outsource_factories SET process_name = '印刷/UV' WHERE process_name IN ('印刷', 'UV')"
            )
            conn.execute("DELETE FROM outsource_processes WHERE process_name IN ('印刷', 'UV')")
            conn.execute(
                "INSERT OR IGNORE INTO outsource_processes (process_name) VALUES ('印刷/UV')"
            )
            conn.execute(
                """
                UPDATE outsource_records
                SET amount = (COALESCE(product_quantity, 0) + COALESCE(spare_quantity, 0))
                           * COALESCE(unit_price, 0) + COALESCE(plate_fee, 0)
                WHERE process_name = '印刷/UV'
                """
            )
            self._seed_customers(conn)
            conn.execute(
                """
                UPDATE orders
                SET customer_code = 15,
                    customer_name = '优品',
                    order_prefix_no = 15
                WHERE customer_code = 63 OR order_prefix_no = 63
                """
            )
            conn.execute(
                """
                UPDATE orders
                SET customer_code = order_prefix_no
                WHERE customer_code IS NULL
                  AND EXISTS (SELECT 1 FROM customers c WHERE c.code = orders.order_prefix_no)
                """
            )
            conn.execute(
                """
                UPDATE orders
                SET customer_name = (
                    SELECT c.name FROM customers c WHERE c.code = orders.customer_code
                )
                WHERE (customer_name IS NULL OR TRIM(customer_name) = '')
                  AND customer_code IS NOT NULL
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name, code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_name, customer_code)")
            conn.commit()

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )

    def _seed_outsource_processes(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT OR IGNORE INTO outsource_processes (process_name) VALUES (?)",
            [(name,) for name in DEFAULT_OUTSOURCE_PROCESSES],
        )

    def _seed_customers(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            """
            INSERT INTO customers (code, name, active)
            VALUES (?, ?, 1)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            CUSTOMERS,
        )
        conn.execute("DELETE FROM customers WHERE code = 63")

    def list_customers(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT code, name FROM customers WHERE active = 1 ORDER BY code"
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_order(self, payload: dict[str, Any]) -> None:
        columns = [
            "order_type",
            "salesman",
            "order_no",
            "product_name",
            "order_date",
            "delivery_date",
            "quantity",
            "spare_quantity",
            "quantity_unit",
            "unit_price",
            "price_tiers_json",
            "extra_fee",
            "paid_status",
            "shipped_status",
            "invoice_status",
            "order_prefix_no",
            "customer_code",
            "customer_name",
            "production_no",
            "bi_no",
            "width_mm",
            "height_mm",
            "thickness_mm",
            "size_as_sample",
            "materials_json",
            "material_note",
            "material_note_red",
            "plating_json",
            "plating_note",
            "plating_note_red",
            "accessories_json",
            "accessories_note",
            "accessories_note_red",
            "polishing_json",
            "polishing_note",
            "polishing_note_red",
            "coloring_json",
            "coloring_text",
            "coloring_note",
            "coloring_note_red",
            "resin_json",
            "resin_note",
            "resin_note_red",
            "packaging_json",
            "packaging_rule",
            "packaging_note",
            "packaging_note_red",
            "back_mode",
            "back_mode_note",
            "back_mode_note_red",
            "global_note",
            "global_note_red",
            "image_paths_json",
        ]
        customer_code = int(payload.get("customer_code") or payload.get("order_prefix_no") or 0)
        with sqlite3.connect(self.db_path) as conn:
            customer = conn.execute(
                "SELECT code, name FROM customers WHERE code = ? AND active = 1",
                (customer_code,),
            ).fetchone()
        if not customer:
            raise ValueError("请选择有效客户")
        payload["order_prefix_no"] = int(customer[0])
        payload["customer_code"] = int(customer[0])
        payload["customer_name"] = str(customer[1])
        defaults = {"paid_status": 0, "shipped_status": 0, "invoice_status": 0, "spare_quantity": 0, "price_tiers_json": "[]"}
        values = [
            defaults[column] if column in defaults and payload.get(column) is None else payload.get(column)
            for column in columns
        ]
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO orders ({', '.join(columns)}) VALUES ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, values)
            conn.commit()

    def search_orders(
        self,
        order_no_keyword: str = "",
        salesman_keyword: str = "",
        delivery_date: str = "",
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            order_type,
            salesman,
            order_no,
            product_name,
            quantity,
            spare_quantity,
            quantity_unit,
            delivery_date,
            created_at
        FROM orders
        WHERE (? = '' OR order_no LIKE ?)
          AND (? = '' OR salesman LIKE ?)
          AND (? = '' OR delivery_date = ?)
        ORDER BY created_at DESC, id DESC
        """
        order_keyword = f"%{order_no_keyword.strip()}%"
        salesman_like = f"%{salesman_keyword.strip()}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                sql,
                (
                    order_no_keyword.strip(),
                    order_keyword,
                    salesman_keyword.strip(),
                    salesman_like,
                    delivery_date.strip(),
                    delivery_date.strip(),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_finance_orders(
        self,
        order_no_keyword: str = "",
        bi_no_keyword: str = "",
        production_no_keyword: str = "",
        order_date_from: str = "",
        order_date_to: str = "",
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            id,
            order_no,
            bi_no,
            production_no,
            product_name,
            quantity,
            quantity_unit,
            unit_price,
            paid_status,
            order_date,
            delivery_date,
            created_at
        FROM orders
        WHERE (? = '' OR order_no LIKE ? OR customer_name LIKE ?)
          AND (? = '' OR bi_no LIKE ?)
          AND (? = '' OR production_no LIKE ?)
          AND (? = '' OR order_date >= ?)
          AND (? = '' OR order_date <= ?)
        ORDER BY order_date DESC, id DESC
        """
        order_no_keyword = order_no_keyword.strip()
        bi_no_keyword = bi_no_keyword.strip()
        production_no_keyword = production_no_keyword.strip()
        order_date_from = order_date_from.strip()
        order_date_to = order_date_to.strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                sql,
                (
                    order_no_keyword,
                    f"%{order_no_keyword}%",
                    f"%{order_no_keyword}%",
                    bi_no_keyword,
                    f"%{bi_no_keyword}%",
                    production_no_keyword,
                    f"%{production_no_keyword}%",
                    order_date_from,
                    order_date_from,
                    order_date_to,
                    order_date_to,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_paid_status(self, order_ids: list[int], paid_status: int) -> None:
        if not order_ids:
            return
        placeholders = ", ".join("?" for _ in order_ids)
        sql = f"UPDATE orders SET paid_status = ? WHERE id IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, [paid_status, *order_ids])
            conn.commit()

    def get_paid_order_profit_rows(
        self,
        order_no_keyword: str = "",
        order_date_from: str = "",
        order_date_to: str = "",
    ) -> list[dict[str, Any]]:
        order_sql = """
        SELECT
            id,
            order_no,
            product_name,
            quantity,
            quantity_unit,
            unit_price,
            order_date,
            delivery_date,
            created_at
        FROM orders
        WHERE paid_status = 1
          AND (? = '' OR order_no LIKE ?)
          AND (? = '' OR order_date >= ?)
          AND (? = '' OR order_date <= ?)
        ORDER BY order_date DESC, id DESC
        """
        order_no_keyword = order_no_keyword.strip()
        order_date_from = order_date_from.strip()
        order_date_to = order_date_to.strip()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            order_rows = conn.execute(
                order_sql,
                (
                    order_no_keyword,
                    f"%{order_no_keyword}%",
                    order_date_from,
                    order_date_from,
                    order_date_to,
                    order_date_to,
                ),
            ).fetchall()

            orders = [dict(row) for row in order_rows]
            if not orders:
                return []

            order_ids = [int(row["id"]) for row in orders]
            placeholders = ", ".join("?" for _ in order_ids)
            outsource_rows = conn.execute(
                f"""
                SELECT
                    id,
                    order_id,
                    order_no,
                    process_name,
                    factory_name,
                    quantity,
                    product_quantity,
                    spare_quantity,
                    unit_price,
                    amount,
                    outsource_date,
                    remark,
                    created_at
                FROM outsource_records
                WHERE order_id IN ({placeholders})
                ORDER BY outsource_date DESC, id DESC
                """,
                order_ids,
            ).fetchall()

        records_by_order: dict[int, list[dict[str, Any]]] = {}
        for row in outsource_rows:
            record = dict(row)
            order_id = int(record["order_id"])
            records_by_order.setdefault(order_id, []).append(record)

        result: list[dict[str, Any]] = []
        for order in orders:
            quantity = float(order["quantity"] or 0)
            unit_price = float(order["unit_price"] or 0)
            receivable_amount = quantity * unit_price

            outsource_records = records_by_order.get(int(order["id"]), [])
            total_outsource_cost = 0.0
            for record in outsource_records:
                if record.get("amount") not in (None, ""):
                    total_outsource_cost += float(record["amount"])
                else:
                    total_outsource_cost += float(record.get("quantity") or 0) * float(
                        record.get("unit_price") or 0
                    )

            result.append(
                {
                    **order,
                    "receivable_amount": receivable_amount,
                    "total_outsource_cost": total_outsource_cost,
                    "profit_amount": receivable_amount - total_outsource_cost,
                    "outsource_records": outsource_records,
                }
            )

        return result

    def get_finance_export_rows(
        self,
        order_date_from: str = "",
        order_date_to: str = "",
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            order_no,
            bi_no,
            production_no,
            quantity,
            quantity_unit,
            unit_price,
            extra_fee,
            delivery_date
        FROM orders
        WHERE (? = '' OR order_date >= ?)
          AND (? = '' OR order_date <= ?)
        ORDER BY order_date DESC, id DESC
        """
        order_date_from = order_date_from.strip()
        order_date_to = order_date_to.strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                sql,
                (
                    order_date_from,
                    order_date_from,
                    order_date_to,
                    order_date_to,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_order_by_order_no(self, order_no: str) -> dict[str, Any] | None:
        normalized_order_no = order_no.strip()
        if not normalized_order_no:
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM orders
                WHERE order_no = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized_order_no,),
            ).fetchone()
        return dict(row) if row else None

    def order_no_exists(self, order_no: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM orders WHERE order_no = ? LIMIT 1",
                (order_no,),
            ).fetchone()
        return row is not None

    def get_next_order_no(self, order_date: str, order_prefix_no: int = 1) -> str:
        suffix_prefix = order_date[2:].replace("-", "")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) + 1
                FROM orders
                WHERE order_date = ?
                """,
                (order_date,),
            ).fetchone()
        sequence = int(row[0]) if row else 1
        candidate = f"TWD{int(order_prefix_no)}-{suffix_prefix}{sequence:03d}"
        while self.order_no_exists(candidate):
            sequence += 1
            candidate = f"TWD{int(order_prefix_no)}-{suffix_prefix}{sequence:03d}"
        return candidate

    def insert_outsource_record(self, payload: dict[str, Any]) -> None:
        columns = [
            "order_id",
            "order_no",
            "process_name",
            "factory_name",
            "quantity",
            "product_quantity",
            "spare_quantity",
            "unit_price",
            "processing_fee",
            "length_mm",
            "width_mm",
            "thickness_mm",
            "density",
            "weight",
            "material_unit_price",
            "color_count",
            "plate_fee",
            "outsource_date",
            "remark",
            "amount",
            "remake_flag",
            "replenishment_flag",
            "paid_status",
        ]
        values = [
            0 if column == "paid_status" and payload.get(column) is None else payload.get(column)
            for column in columns
        ]
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO outsource_records ({', '.join(columns)}) VALUES ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, values)
            conn.commit()

    def search_outsource_records(
        self,
        order_no_keyword: str = "",
        factory_keyword: str = "",
        process_keyword: str = "",
        outsource_date_from: str = "",
        outsource_date_to: str = "",
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            r.id,
            r.order_id,
            r.order_no,
            r.process_name,
            r.factory_name,
            r.quantity,
            r.product_quantity,
            r.spare_quantity,
            r.unit_price,
            r.processing_fee,
            r.length_mm,
            r.width_mm,
            r.thickness_mm,
            r.density,
            r.weight,
            r.material_unit_price,
            r.color_count,
            r.plate_fee,
            r.outsource_date,
            r.remark,
            r.amount,
            r.remake_flag,
            r.replenishment_flag,
            r.paid_status,
            r.created_at,
            o.product_name,
            o.delivery_date
        FROM outsource_records r
        LEFT JOIN orders o ON o.id = r.order_id
        WHERE (? = '' OR r.order_no LIKE ?)
          AND (? = '' OR r.factory_name LIKE ?)
          AND (? = '' OR r.process_name LIKE ?)
          AND (? = '' OR r.outsource_date >= ?)
          AND (? = '' OR r.outsource_date <= ?)
        ORDER BY r.created_at DESC, r.id DESC
        """
        order_no_keyword = order_no_keyword.strip()
        factory_keyword = factory_keyword.strip()
        process_keyword = process_keyword.strip()
        outsource_date_from = outsource_date_from.strip()
        outsource_date_to = outsource_date_to.strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                sql,
                (
                    order_no_keyword,
                    f"%{order_no_keyword}%",
                    factory_keyword,
                    f"%{factory_keyword}%",
                    process_keyword,
                    f"%{process_keyword}%",
                    outsource_date_from,
                    outsource_date_from,
                    outsource_date_to,
                    outsource_date_to,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_outsource_record_for_order_process(
        self,
        order_no: str,
        process_name: str,
    ) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM outsource_records
                WHERE order_no = ?
                  AND process_name = ?
                  AND COALESCE(remake_flag, 0) = 0
                  AND COALESCE(replenishment_flag, 0) = 0
                ORDER BY outsource_date DESC, created_at DESC, id DESC
                LIMIT 1
                """,
                (order_no.strip(), process_name.strip()),
            ).fetchone()
        return dict(row) if row else None

    def update_outsource_paid_status(self, record_ids: list[int], paid_status: int) -> None:
        if not record_ids:
            return
        placeholders = ", ".join("?" for _ in record_ids)
        sql = f"UPDATE outsource_records SET paid_status = ? WHERE id IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, [paid_status, *record_ids])
            conn.commit()

    def get_outsource_record(self, record_id: int) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                    r.*,
                    o.product_name,
                    o.quantity AS order_quantity,
                    o.quantity_unit
                FROM outsource_records r
                LEFT JOIN orders o ON o.id = r.order_id
                WHERE r.id = ?
                """,
                (record_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_outsource_record(self, record_id: int, payload: dict[str, Any]) -> None:
        columns = [
            "process_name",
            "factory_name",
            "quantity",
            "product_quantity",
            "spare_quantity",
            "unit_price",
            "processing_fee",
            "length_mm",
            "width_mm",
            "thickness_mm",
            "density",
            "weight",
            "material_unit_price",
            "color_count",
            "plate_fee",
            "outsource_date",
            "remark",
            "amount",
            "remake_flag",
            "replenishment_flag",
        ]
        assignments = ", ".join(f"{column} = ?" for column in columns)
        values = [payload.get(column) for column in columns]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE outsource_records SET {assignments} WHERE id = ?",
                [*values, record_id],
            )
            conn.commit()

    def delete_outsource_record(self, record_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM outsource_records WHERE id = ?", (record_id,))
            conn.commit()

    def list_outsource_processes(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, process_name, created_at
                FROM outsource_processes
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_outsource_process(self, process_name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO outsource_processes (process_name) VALUES (?)",
                (process_name.strip(),),
            )
            conn.commit()

    def update_outsource_process(self, process_id: int, process_name: str) -> None:
        normalized_name = process_name.strip()
        with sqlite3.connect(self.db_path) as conn:
            old_row = conn.execute(
                "SELECT process_name FROM outsource_processes WHERE id = ?",
                (process_id,),
            ).fetchone()
            if not old_row:
                return
            old_name = str(old_row[0])
            conn.execute(
                "UPDATE outsource_processes SET process_name = ? WHERE id = ?",
                (normalized_name, process_id),
            )
            conn.execute(
                "UPDATE outsource_factories SET process_name = ? WHERE process_name = ?",
                (normalized_name, old_name),
            )
            conn.execute(
                "UPDATE outsource_records SET process_name = ? WHERE process_name = ?",
                (normalized_name, old_name),
            )
            conn.commit()

    def delete_outsource_process(self, process_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT process_name FROM outsource_processes WHERE id = ?",
                (process_id,),
            ).fetchone()
            if not row:
                return
            process_name = str(row[0])
            conn.execute("DELETE FROM outsource_processes WHERE id = ?", (process_id,))
            conn.execute(
                "DELETE FROM outsource_factories WHERE process_name = ?",
                (process_name,),
            )
            conn.commit()

    def list_outsource_factories(self, process_name: str = "") -> list[dict[str, Any]]:
        normalized_process_name = process_name.strip()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, process_name, factory_name, created_at
                FROM outsource_factories
                WHERE (? = '' OR process_name = ?)
                ORDER BY process_name ASC, id ASC
                """,
                (normalized_process_name, normalized_process_name),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_outsource_factory(self, process_name: str, factory_name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO outsource_factories (process_name, factory_name)
                VALUES (?, ?)
                """,
                (process_name.strip(), factory_name.strip()),
            )
            conn.commit()

    def update_outsource_factory(self, factory_id: int, process_name: str, factory_name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE outsource_factories
                SET process_name = ?, factory_name = ?
                WHERE id = ?
                """,
                (process_name.strip(), factory_name.strip(), factory_id),
            )
            conn.commit()

    def delete_outsource_factory(self, factory_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM outsource_factories WHERE id = ?", (factory_id,))
            conn.commit()


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads_json(value: str) -> Any:
    return json.loads(value) if value else []


