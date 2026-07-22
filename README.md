# TWD Order System

TWD Order System 是一个面向订单录入、工单生成、财务收付款、外发加工和内部审批的轻量级订单管理系统。项目同时保留早期桌面端入口，并以 FastAPI Web 端作为当前主要使用和协作开发版本。

当前部署形态适合十几人规模的内部团队使用：FastAPI 单进程、SQLite WAL、Nginx 反向代理、systemd 托管服务，不依赖 Docker、Redis 或 Celery。

## 功能概览

- 业务下单：创建、预览、查看和打印订单 PDF。
- AI 客单识别：支持 DOCX、Excel、CSV、TSV、HTML、PDF 客单；识别后自动填入下单表单；识别到的繁体字会转换为简体字。
- 产品图片：支持上传或在指定输入框获得焦点时按 `Ctrl+V` 粘贴 JPG / PNG / WEBP 图片；单张最大 5 MB，最多 6 张。
- 制作工艺：按“表面工艺 + 材质”两行选择并组合输出，例如 `铜  烤漆`；冲压、压铸、材质等字样会在识别/归一化时省略。
- 订单权限：管理员可直接修改/删除订单；业务只能申请修改，审批通过后从消息页进入修改。
- 消息中心：管理员处理业务修改申请；业务查看审批结果、批注和可修改入口。
- 财务页拆分：应收和应付分开管理，支持状态更新、筛选、导出和 PDF 汇总。
- 外发加工：支持批量录入外发工序、加工厂、数量、单价、材料和版费等扩展字段。
- PDF 工单：基于 `order_temp.pdf` 模板生成正式工单。
- 数据备份：服务器部署包含 SQLite 备份脚本和 systemd timer。

## 技术栈

- Web: FastAPI, Jinja2, Starlette sessions
- Desktop: PySide6
- Database: SQLite
- PDF: reportlab, pypdf
- Office import: python-docx, openpyxl, xlrd
- AI import: Qwen OpenAI-compatible Chat Completions API
- Traditional Chinese conversion: opencc-python-reimplemented

## 目录结构

```text
.
├── main.py                         # 桌面端入口
├── web_main.py                     # Web 端入口
├── order_temp.pdf                  # 工单 PDF 模板
├── requirements.txt                # 桌面端/通用依赖
├── requirements-server.txt         # Web 服务器依赖
├── order_system/
│   ├── config.py                   # 路径、环境变量和运行目录配置
│   ├── database.py                 # 早期桌面端 SQLite 访问层
│   ├── order_import.py             # 客单读取、AI 识别、字段归一化
│   ├── pdf_template_worker.py      # PDF 模板绘制核心
│   ├── pdf_service.py              # 桌面端 PDF 生成/预览服务
│   ├── ui.py                       # 桌面端 PySide UI
│   └── web/
│       ├── app.py                  # Web 路由和业务流程
│       ├── repository.py           # Web 端 SQLite schema 和数据访问
│       ├── catalogs.py             # 下拉/多选目录值
│       ├── manage.py               # 创建账号、重置密码
│       ├── pdf.py                  # Web PDF 生成
│       ├── static/                 # CSS/JS
│       └── templates/              # Jinja2 页面模板
├── deploy/                         # systemd 和 Nginx 配置
├── scripts/backup_sqlite.py        # SQLite 在线备份脚本
└── tests/                          # smoke tests
```

运行时目录不会提交到 Git：

- `data/`: SQLite 数据库
- `images/`: 用户上传/粘贴的产品图片
- `output/`: 导出的 PDF、Excel 等文件
- `tmp/`: 临时文件
- `.deploy-backups/`: 服务器部署备份

## 本地开发

### 1. 创建虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-server.txt
```

### 2. 配置环境变量

复制 `.env.example`，按需设置 Qwen API：

```powershell
Copy-Item .env.example .env
```

常用变量：

- `QWEN_API_KEY`: AI 客单识别 API Key。
- `QWEN_BASE_URL`: 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `QWEN_MODEL`: 默认 `qwen3.7-plus`。
- `TWD_DATA_DIR`: 数据目录；不设置时使用项目内默认目录。
- `TWD_SESSION_SECRET`: Web session 密钥，生产环境必须设置。

不要把真实 API Key 或生产密钥提交到 Git。

### 3. 初始化账号

```powershell
python -m order_system.web.manage create-user admin --role admin
python -m order_system.web.manage create-user sales01 --role sales
python -m order_system.web.manage create-user finance01 --role finance
python -m order_system.web.manage create-user outsource01 --role outsource
```

角色说明：

- `admin`: 全部权限，包含订单修改/删除、审批、财务、外发。
- `sales`: 下单、AI 导入、申请修改、查看审批消息。
- `finance`: 财务应收管理。
- `outsource`: 外发和应付相关查看/录入。

### 4. 启动 Web 服务

```powershell
python web_main.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

### 5. 启动桌面端

```powershell
python main.py
```

桌面端是早期入口，当前新功能优先在 Web 端维护。

## 测试

当前测试以 smoke test 为主，覆盖关键业务流程：

```powershell
python -m compileall order_system
python tests\web_smoke.py
python tests\finance_web_smoke.py
python tests\outsource_batch_smoke.py
python tests\concurrency_smoke.py
python tests\order_import_traditional_smoke.py
```

测试说明：

- `web_smoke.py`: 登录、下单、预览标记、编辑、删除、PDF 等基础 Web 流程。
- `finance_web_smoke.py`: 应收/应付拆分页、导出和状态逻辑。
- `outsource_batch_smoke.py`: 外发批量录入和金额计算。
- `concurrency_smoke.py`: 自动订单号并发生成和回收。
- `order_import_traditional_smoke.py`: AI 导入归一化中的繁体转简体。

## 服务器部署

详细步骤见 [WEB_DEPLOY.md](WEB_DEPLOY.md)。核心流程如下：

```bash
sudo apt update
sudo apt install -y python3-venv nginx fonts-noto-cjk
sudo mkdir -p /opt/twd-order /var/lib/twd-order/{data,images,backups,tmp/web,output/pdf}
cd /opt/twd-order
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-server.txt
```

配置生产环境变量：

```bash
sudo cp .env.server.example /etc/twd-order.env
sudo nano /etc/twd-order.env
```

创建管理员：

```bash
sudo -u twdorder bash -c 'set -a; source /etc/twd-order.env; set +a; cd /opt/twd-order; .venv/bin/python -m order_system.web.manage create-user admin --role admin'
```

启用服务：

```bash
sudo cp deploy/twd-order.service /etc/systemd/system/
sudo cp deploy/twd-order-backup.service deploy/twd-order-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now twd-order twd-order-backup.timer
sudo systemctl status twd-order --no-pager
```

常用运维命令：

```bash
sudo journalctl -u twd-order -f
curl http://127.0.0.1:8000/health
sudo systemctl start twd-order-backup.service
```

## 重要业务规则

### 订单编号

自动订单号按客户编码和日期生成，例如：

```text
TWD1-260715001
```

系统允许手工订单号；自动生成逻辑通过 SQLite 事务保证并发唯一。

### 制作工艺

Web 表单分两行选择：

1. 表面工艺：烤漆、珐琅、UV、镭雕
2. 材质：铜、铁质、锌合金等

保存和 PDF 输出时组合成：

```text
铜  烤漆
```

AI 识别中出现“铜冲压烤漆”“锌合金压铸UV”等写法时，会省略“冲压/压铸/材质”等字样并匹配到目录项。

### 图片上传和粘贴

下单页和修改订单页都支持：

- 文件选择上传
- 点击“按 Ctrl+V 粘贴图片”的输入框后粘贴图片

限制：

- 只在该输入框获得焦点时响应粘贴
- 剪贴板不是图片时不添加
- 只接受 JPG / PNG / WEBP
- 单张最大 5 MB
- 最多 6 张

### 订单修改审批

- 管理员可在订单列表直接右键修改/删除订单。
- 业务在订单列表只能右键申请修改。
- 管理员在消息页审批申请，可填写批注。
- 业务在消息页查看结果；审批通过后，从该消息上的“修改”按钮进入订单修改页。

## Git 协作规范

这个项目已经建立本地 Git 基线。多人协作时建议：

1. 每个需求单独开分支。
2. 修改前先 `git pull --rebase`。
3. 修改后至少运行相关 smoke test。
4. 提交信息写清楚业务功能，例如：

```bash
git checkout -b feature/order-preview
git status
git diff
git add README.md order_system tests
git commit -m "Add order preview workflow"
```

不要提交以下内容：

- `.env`
- `data/*.db`
- `images/`
- `output/`
- `tmp/`
- 服务器备份目录
- API Key、登录密码、真实客户敏感资料

## GitHub 同步

首次同步到 GitHub 时，需要一个目标仓库，例如：

```text
https://github.com/<owner>/<repo>.git
```

拿到仓库地址后，在本地执行：

```bash
git remote add origin https://github.com/<owner>/<repo>.git
git branch -M main
git push -u origin main
```

如果仓库已经存在 remote：

```bash
git remote -v
git push
```

建议在 GitHub 上开启：

- branch protection
- pull request review
- secret scanning
- required status checks

## 常见修改入口

- 表单字段/页面流程：`order_system/web/templates/` 和 `order_system/web/app.py`
- 前端交互：`order_system/web/static/app.js`
- 页面样式：`order_system/web/static/app.css`
- 数据库 schema 和迁移：`order_system/web/repository.py`
- AI 客单识别：`order_system/order_import.py`
- 下拉/多选目录：`order_system/web/catalogs.py`
- PDF 输出：`order_system/web/pdf.py` 和 `order_system/pdf_template_worker.py`
- 账号管理命令：`order_system/web/manage.py`
- 服务器服务配置：`deploy/`

## 维护建议

- 修改数据库字段时，同步更新 schema、读写方法、表单模板、PDF 输出和 smoke tests。
- 修改 PDF 模板 `order_temp.pdf` 后，务必用真实订单生成 PDF 对照坐标。
- 修改 AI 识别 prompt 或目录值后，补充对应归一化测试。
- 部署前先备份服务器当前代码和数据库。
- 生产环境应使用 HTTPS，并设置 `TWD_COOKIE_HTTPS_ONLY=1`。
