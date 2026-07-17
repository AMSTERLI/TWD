from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


root = Path(os.environ.get("TWD_DATA_DIR", Path(__file__).resolve().parents[1]))
source = root / "data" / "orders.db"
backup_dir = root / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
target = backup_dir / f"orders-{datetime.now():%Y%m%d-%H%M%S}.db"

if not source.exists():
    raise SystemExit(f"数据库不存在：{source}")

with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
    src.backup(dst)

cutoff = datetime.now() - timedelta(days=int(os.environ.get("TWD_BACKUP_DAYS", "30")))
for path in backup_dir.glob("orders-*.db"):
    if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
        path.unlink()
print(target)
