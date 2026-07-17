# TWD Order System MVP

基于 `PySide6 + SQLite + PDF 模板填充` 的单机版电子订单管理系统。

这个项目当前的核心目标不是“网页式后台”，而是：

- 用桌面表单录入订单
- 将订单持久化到本地 SQLite
- 按业务模板生成 PDF 工单
- 在软件内直接预览生成后的 PDF 页面

## 当前能力

- 新建订单表单，覆盖主要工艺模块
- 订单编号支持手动填写或按日期顺序自动生成
- 本地图片附件选择，最多 3 张，自动复制到 `images/`
- 本地订单管理列表，可按订单号 / 交期搜索
- 点击订单后生成真实 PDF，并显示 PDF 渲染结果
- 各工艺备注可单独控制是否显示为红字

## 运行方式

### 1. 安装依赖

系统 Python 仅用于启动桌面程序：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 2. 首次启动会创建的目录

- `data/orders.db`
- `images/`
- `output/pdf/`
- `tmp/pdf_preview/`

## 技术栈

- GUI: `PySide6`
- Database: `SQLite`
- PDF fill/merge: `reportlab` + `pypdf`
- PDF preview render: `pdftoppm`

## 项目结构

### 顶层文件

- [main.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/main.py)
  - 程序入口，只负责调用 `order_system.ui.run()`
- [requirements.txt](C:/Users/LBL99/OneDrive/文档/TWD_order_system/requirements.txt)
  - 当前桌面程序依赖
- [order_temp.pdf](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_temp.pdf)
  - PDF 模板底版，生成工单时会往这个模板上叠加文字和图片

### 核心包

- [order_system/config.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/config.py)
  - 路径配置
  - 例如数据库、图片目录、PDF 模板、输出目录、bundled Python 路径

- [order_system/database.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/database.py)
  - SQLite schema 和数据库读写
  - 负责表初始化、字段迁移、插入订单、查询订单、按日期生成自动订单号
  - 如果后续新增字段，通常从这里开始改

- [order_system/ui.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/ui.py)
  - 主界面和表单逻辑
  - 包含：
    - `OrderFormTab`：新建订单表单
    - `OrderListTab`：订单管理列表
    - `OrderPreviewDialog`：订单 PDF 预览弹窗
  - 如果要改表单字段、列表列、交互行为，主要看这个文件

- [order_system/storage.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/storage.py)
  - 图片文件复制与重命名
  - 保存订单时会把用户选中的图片转存到 `images/`

- [order_system/pdf_service.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_service.py)
  - PDF 预览服务层
  - 负责：
    - 调用模板填充脚本生成 PDF
    - 调用 `pdftoppm` 把 PDF 渲染成 PNG
    - 返回生成的 PDF 路径和预览图片路径
  - UI 不直接处理 PDF 细节，而是通过这里调用

- [order_system/pdf_template_worker.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_template_worker.py)
  - PDF 模板填充核心逻辑
  - 这是“模板坐标调教”的主战场
  - 负责：
    - 在 PDF 模板指定坐标绘制订单头信息
    - 绘制工艺文字与备注
    - 控制备注是否红字
    - 绘制订单图片
    - 合并 overlay 和模板生成最终 PDF

## 数据流

### 保存订单

1. 用户在 `OrderFormTab` 填写表单
2. UI 组装 payload
3. 图片通过 `storage.py` 复制到 `images/`
4. 订单通过 `database.py` 写入 `data/orders.db`

### 预览订单

1. 用户在 `OrderListTab` 点击订单
2. UI 读取数据库记录
3. `pdf_service.py` 调用 `pdf_template_worker.py`
4. `pdf_template_worker.py` 在 `order_temp.pdf` 上叠加文字/图片生成 PDF
5. `pdf_service.py` 调用 `pdftoppm` 把生成后的 PDF 渲染成 PNG
6. `OrderPreviewDialog` 展示渲染后的页面图

## SQLite 字段说明

订单表 `orders` 目前大致分为几类字段：

- 基础信息
  - `order_type`
  - `salesman`
  - `order_no`
  - `product_name`
  - `order_date`
  - `delivery_date`
  - `quantity`
  - `production_no`
  - `bi_no`：界面和 PDF 显示为 `PO编号`

- 尺寸信息
  - `width_mm`
  - `height_mm`
  - `thickness_mm`
  - `size_as_sample`

- 工艺勾选项
  - `materials_json`
  - `plating_json`
  - `accessories_json`
  - `polishing_json`
  - `coloring_json`
  - `resin_json`
  - `packaging_json`

- 工艺备注
  - `material_note`
  - `plating_note`
  - `accessories_note`
  - `polishing_note`
  - `coloring_note`
  - `resin_note`
  - `packaging_note`
  - `back_mode_note`
  - `global_note`

- 备注颜色开关
  - `material_note_red`
  - `plating_note_red`
  - `accessories_note_red`
  - `polishing_note_red`
  - `coloring_note_red`
  - `resin_note_red`
  - `packaging_note_red`
  - `back_mode_note_red`
  - `global_note_red`

- 其他
  - `packaging_rule`
  - `back_mode`
  - `image_paths_json`

## 开发时最常见的修改入口

### 1. 改表单字段

优先看 [order_system/ui.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/ui.py)

重点函数：

- `_build_basic_info_group`
- `_build_options_group`
- `_build_coloring_group`
- `_build_resin_group`
- `_build_packaging_group`
- `_build_back_mode_group`
- `_build_global_note_group`
- `_collect_payload`
- `reset_form`

### 2. 改数据库字段

优先看 [order_system/database.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/database.py)

通常需要同步改三处：

1. `SCHEMA`
2. `initialize()` 里的迁移逻辑
3. `insert_order()` 的 `columns`

如果字段要在界面中录入，还要同步修改 `ui.py`。

### 3. 改 PDF 版式 / 坐标 / 字号 / 颜色

优先看 [order_system/pdf_template_worker.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_template_worker.py)

最重要的函数：

- `_draw_header`
  - 控制订单头、日期、尺寸、订单号位置
- `_draw_process_table`
  - 控制材质、电镀、焊针、抛光、上色、树脂、包装、背模、全局备注
- `_draw_images`
  - 控制图片插入和布局
- `_draw_footer`
  - 控制生产制号 / PO号 / 审核位置

如果只是“某一行文字太高/太低/太小/太大”，通常只需要改这里的坐标参数或字号参数。

### 4. 改 PDF 预览流程

优先看 [order_system/pdf_service.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_service.py)

它负责把：

- 数据记录
- PDF 填充
- PDF 渲染
- 预览图片路径

串成一条完整链路。

## 生成产物说明

- `images/`
  - 保存用户上传并转存后的图片

- `data/orders.db`
  - 本地 SQLite 数据库

- `output/pdf/`
  - 生成后的正式 PDF 工单

- `tmp/pdf_preview/`
  - 预览用中间文件
  - 每个订单会有自己的渲染目录

## 维护建议

### 修改模板时

如果 `order_temp.pdf` 的版式发生变化：

1. 先替换模板文件
2. 用一条真实订单生成 PDF
3. 对照预览结果调整 `pdf_template_worker.py` 坐标
4. 重点检查：
   - 订单编号换行
   - 尺寸数字位置
   - 材质与工艺区文字是否越界
   - 图片是否遮挡
   - 备注红字是否只影响对应备注

### 新增工艺模块时

一般要同时修改：

1. `database.py` 中 schema 和 insert columns
2. `ui.py` 中表单构建和 `_collect_payload`
3. `pdf_template_worker.py` 中工艺输出逻辑

## 已知注意点

- 当前界面显示为 `PO编号`，数据库字段名仍保留为 `bi_no`，这是为了兼容现有数据结构。
- PDF 生成依赖 Windows 中文字体文件，例如 `msyh.ttc`。
- PDF 渲染依赖 `pdftoppm` 可用。
- `tmp/` 和 `output/` 下会不断产生预览与导出文件，长期运行后可以考虑加清理策略。

## 建议的接手顺序

如果是第一次接手这个项目，建议按这个顺序读代码：

1. [README.md](C:/Users/LBL99/OneDrive/文档/TWD_order_system/README.md)
2. [main.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/main.py)
3. [order_system/ui.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/ui.py)
4. [order_system/database.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/database.py)
5. [order_system/pdf_service.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_service.py)
6. [order_system/pdf_template_worker.py](C:/Users/LBL99/OneDrive/文档/TWD_order_system/order_system/pdf_template_worker.py)

这样基本能在最短时间里理解这套系统是怎么串起来的。
