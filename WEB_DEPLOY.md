# TWD 订单系统服务器部署

该版本面向约 10–20 人浏览器访问和 2 GB 内存服务器：FastAPI 单进程、SQLite WAL、Nginx 静态文件与反向代理，不依赖 Redis、Celery 或 Docker。原桌面版 `data/orders.db` 可直接迁移。

## 1. 准备 Ubuntu/Debian 服务器

```bash
sudo apt update
sudo apt install -y python3-venv nginx fonts-noto-cjk
sudo useradd --system --home /var/lib/twd-order --shell /usr/sbin/nologin twdorder
sudo mkdir -p /opt/twd-order /var/lib/twd-order/{data,images,backups,tmp/web,output/pdf}
sudo chown -R twdorder:twdorder /var/lib/twd-order
```

把项目复制到 `/opt/twd-order`。首次迁移时，在停止桌面版写入后复制数据库和图片：

```bash
sudo cp data/orders.db /var/lib/twd-order/data/orders.db
sudo cp -a images/. /var/lib/twd-order/images/
sudo chown -R twdorder:twdorder /var/lib/twd-order
cd /opt/twd-order
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-server.txt
```

## 2. 配置密钥和账号

```bash
sudo cp .env.server.example /etc/twd-order.env
sudo chown root:twdorder /etc/twd-order.env
sudo chmod 640 /etc/twd-order.env
sudo nano /etc/twd-order.env
sudo -u twdorder bash -c 'set -a; source /etc/twd-order.env; set +a; cd /opt/twd-order; .venv/bin/python -m order_system.web.manage create-user admin --role admin'
```

请不要把 API Key 写入代码或提交到 Git。此前在聊天或截图中出现过的 Key 应在 DeepSeek 控制台撤销并生成新 Key，再写入 `/etc/twd-order.env`。

角色：`sales` 可下单和 AI 导入，`finance` 可管理收款，`outsource` 可管理外发，`admin` 拥有全部权限。按实际员工分别创建账号，不共用管理员账号。

## 3. 启动服务

```bash
sudo cp deploy/twd-order.service /etc/systemd/system/
sudo cp deploy/twd-order-backup.service deploy/twd-order-backup.timer /etc/systemd/system/
sudo cp deploy/nginx-twd-order.conf /etc/nginx/sites-available/twd-order
sudo ln -s /etc/nginx/sites-available/twd-order /etc/nginx/sites-enabled/twd-order
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now twd-order nginx twd-order-backup.timer
sudo systemctl status twd-order --no-pager
```

浏览器访问服务器 IP。若通过公网访问，应配置域名和 HTTPS，并把 `TWD_COOKIE_HTTPS_ONLY=1`。若只在公司内网使用，防火墙只允许内网网段访问 80/443 端口。

## 4. 运维

```bash
# 日志
sudo journalctl -u twd-order -f

# 健康检查
curl http://127.0.0.1:8000/health

# 手动备份
sudo systemctl start twd-order-backup.service

# 更新程序（先备份）
sudo systemctl stop twd-order
sudo -u twdorder /opt/twd-order/.venv/bin/python /opt/twd-order/scripts/backup_sqlite.py
sudo systemctl start twd-order
```

每天凌晨会用 SQLite 在线备份 API 生成一致性备份，并默认保留 30 天。还应定期把 `/var/lib/twd-order/backups` 同步到另一台机器或对象存储；同一块硬盘上的备份不能防硬盘损坏。

## 资源配置说明

- 只运行 1 个 Uvicorn worker，避免每个进程重复占用内存。
- AI 识别最多并发 2 个，其他请求仍可响应。
- 列表分页读取，PDF 在内存中生成并直接交给浏览器预览。
- SQLite 使用 WAL、10 秒 busy timeout 和短事务，适合当前十多人规模。
- systemd 将应用内存上限设为 1.1 GB，为 Nginx、系统和磁盘缓存留出空间。
