import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QThread, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from order_system.config import DB_PATH, IMAGES_DIR, LOGIN_PASSWORD, LOGIN_USERS
from order_system.database import Database, dumps_json, loads_json
from order_system.excel_export import export_rows_to_excel
from order_system.order_import import OrderImportError, analyze_order_document
from order_system.pdf_service import OrderPreviewError, generate_order_preview_artifacts
from order_system.storage import copy_images


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class NoWheelDateEdit(QDateEdit):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


QComboBox = NoWheelComboBox
QDateEdit = NoWheelDateEdit


ORDER_TYPES = ["新订单", "样品单", "重做单", "打样下单", "复订单", "赔做单"]
QUANTITY_UNITS = ["\u4e2a", "\u5957"]
ORDER_PREFIX_VALUES = [str(i) for i in range(1, 101)]
MATERIALS = [
    "青铜咬板烤漆",
    "铜冲压烤漆",
    "铁质冲压烤漆",
    "铜冲假珐琅",
    "铁冲假珐琅",
    "锌合金压铸烤漆",
    "锌合金压铸软珐琅",
    "低温锌合金压铸烤漆",
    "铝材质",
    "不锈钢材质",
]
PLATING = [
    "如样",
    "银",
    "镍",
    "古银",
    "黑镍",
    "雾镍",
    "古镍",
    "红铜",
    "青铜",
    "古红铜",
    "古金",
    "古青铜",
    "雾金",
    "刷线封油",
    "仿金",
    "染黑",
    "真金",
    "金+镍",
]
ACCESSORIES = [
    "10mm 刺马针",
    "8mm 刺马针",
    "安全别针",
    "银锡",
    "焊锡",
    "焊胶",
    "简针",
    "磁铁",
    "宝石",
    "柳针",
]
POLISHING = ["正面", "侧面", "背面", "三面", "喷砂"]
COLORING_OPTIONS = ["说明", "样品", "彩图", "分色图"]
RESIN_OPTIONS = ["一般", "厚", "薄", "双面", "单面"]
PACKAGING = ["空白袋", "夹链袋", "胶帽", "白纸卷", "蝴蝶帽", "MIC袋", "OPP袋", "气泡袋", "PVC袋", "装订"]
BACK_MODES = ["光平", "布纹", "砂面", "团模", "双面模"]
OPTION_LABELS = {
    "materials_json": "材质及做法",
    "plating_json": "电镀工艺",
    "accessories_json": "焊针配件",
    "polishing_json": "抛光工艺",
    "resin_json": "树脂(滴胶)",
    "packaging_json": "包装方式",
}
OPTION_CATALOG = {
    "materials_json": MATERIALS,
    "plating_json": PLATING,
    "accessories_json": ACCESSORIES,
    "polishing_json": POLISHING,
    "resin_json": RESIN_OPTIONS,
    "packaging_json": PACKAGING,
}
NOTE_LABELS = {
    "material_note": "材质备注",
    "plating_note": "电镀备注",
    "accessories_note": "配件备注",
    "polishing_note": "抛光备注",
    "coloring_json": "上色选项",
    "coloring_note": "上色说明",
    "resin_note": "树脂备注",
    "packaging_rule": "组合包装规则",
    "packaging_note": "包装备注",
    "back_mode_note": "背模备注",
    "global_note": "全局注意事项",
    "material_note_red": "材质备注红字",
    "plating_note_red": "电镀备注红字",
    "accessories_note_red": "配件备注红字",
    "polishing_note_red": "抛光备注红字",
    "coloring_note_red": "上色备注红字",
    "resin_note_red": "树脂备注红字",
    "packaging_note_red": "包装备注红字",
    "back_mode_note_red": "背模备注红字",
    "global_note_red": "全局备注红字",
}


PROCESS_FIELD_SEQUENCE = [
    ("materials_json", "material_note"),
    ("plating_json", "plating_note"),
    ("accessories_json", "accessories_note"),
    ("polishing_json", "polishing_note"),
    ("coloring_json", "coloring_note"),
    ("resin_json", "resin_note"),
    ("packaging_json", "packaging_note"),
    ("back_mode", "back_mode_note"),
]
OUTSOURCE_PROCESS_OPTIONS = [
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
OUTSOURCE_TABLE_COLUMNS = {
    "order_no": 0,
    "product_name": 1,
    "order_quantity": 2,
    "product_quantity": 3,
    "spare_quantity": 4,
    "unit_price": 5,
    "processing_fee": 6,
    "length_mm": 7,
    "width_mm": 8,
    "thickness_mm": 9,
    "density": 10,
    "weight": 11,
    "material_unit_price": 12,
    "color_count": 13,
    "plate_fee": 14,
    "outsource_date": 15,
    "remark": 16,
    "remake_flag": 17,
    "replenishment_flag": 18,
    "amount": 19,
}


def image_absolute_paths(image_names: list[str]) -> list[Path]:
    return [IMAGES_DIR / name for name in image_names]


def extract_order_process_options(record: dict) -> list[str]:
    options: list[str] = []
    for selection_key, note_key in PROCESS_FIELD_SEQUENCE:
        label = (
            OPTION_LABELS.get(selection_key)
            or NOTE_LABELS.get(selection_key)
            or NOTE_LABELS.get(note_key)
            or selection_key
        )
        raw_value = record.get(selection_key)

        values: list[str] = []
        if selection_key.endswith("_json"):
            decoded = loads_json(raw_value or "[]")
            if isinstance(decoded, list):
                values = [str(item).strip() for item in decoded if str(item).strip()]
        elif raw_value not in (None, ""):
            values = [str(raw_value).strip()]

        note_value = str(record.get(note_key) or "").strip()

        if values:
            for value in values:
                candidate = f"{label} - {value}"
                if candidate not in options:
                    options.append(candidate)
        if note_value:
            candidate = f"{label} - {note_value}"
            if candidate not in options:
                options.append(candidate)
    return options


def safe_float(value: str | float | int | None, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def apply_outsource_row_style(items: list[QTableWidgetItem | None], row: dict) -> None:
    color: QColor | None = None
    if row.get("remake_flag"):
        color = QColor("#c62828")
    elif row.get("replenishment_flag"):
        color = QColor("#1565c0")

    if not color:
        return
    for item in items:
        if item is not None:
            item.setForeground(color)


class PreviewSection(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewSection")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        self.layout.addWidget(title_label)

    def add_row(self, label: str, value: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        key_label = QLabel(label)
        key_label.setObjectName("fieldLabel")
        key_label.setMinimumWidth(110)
        value_label = QLabel(value or "未填写")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_label.setObjectName("fieldValue")

        row_layout.addWidget(key_label)
        row_layout.addWidget(value_label, 1)
        self.layout.addWidget(row)

    def add_multiline(self, label: str, value: str) -> None:
        wrapper = QVBoxLayout()
        wrapper.setSpacing(6)
        key_label = QLabel(label)
        key_label.setObjectName("fieldLabel")
        value_label = QLabel(value or "未填写")
        value_label.setWordWrap(True)
        value_label.setObjectName("noteValue")
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        wrapper.addWidget(key_label)
        wrapper.addWidget(value_label)
        container = QWidget()
        container.setLayout(wrapper)
        self.layout.addWidget(container)

    def add_tag_list(self, label: str, values: list[str]) -> None:
        self.add_multiline(label, "、".join(values) if values else "未勾选")

    def add_widget(self, widget: QWidget) -> None:
        self.layout.addWidget(widget)


class OrderPreviewDialog(QDialog):
    def __init__(self, record: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = record
        self.pdf_path: Path | None = None
        self.setWindowTitle(f"PDF 订单预览 - {record.get('order_no', '')}")
        self.resize(980, 900)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("订单 PDF 预览")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #213547;")
        root.addWidget(title)

        self.status_label = QLabel("正在生成填好的 PDF...")
        self.status_label.setStyleSheet("color: #5c6b7a;")
        root.addWidget(self.status_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.export_button = QPushButton("导出 PDF")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_pdf)
        close_button = QPushButton("关闭预览")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(self.export_button)
        button_row.addWidget(close_button)
        root.addLayout(button_row)

        try:
            artifacts = generate_order_preview_artifacts(self.record)
        except OrderPreviewError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"生成预览失败：{exc}")
            return

        self.pdf_path = artifacts.pdf_path
        self.export_button.setEnabled(self.pdf_path.exists())
        self.status_label.setText(f"当前预览来自生成后的 PDF：{artifacts.pdf_path.name}")
        self._show_pages(artifacts.page_images)

    def _show_pages(self, page_images: list[Path]) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        for page_index, image_path in enumerate(page_images, start=1):
            page_frame = QFrame()
            page_frame.setStyleSheet(
                "QFrame { background: white; border: 1px solid #d4dbe3; border-radius: 10px; }"
            )
            page_layout = QVBoxLayout(page_frame)
            page_layout.setContentsMargins(16, 16, 16, 16)
            page_layout.setSpacing(10)

            page_label = QLabel(f"第 {page_index} 页")
            page_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #51606f;")
            image_label = QLabel()
            image_label.setAlignment(Qt.AlignCenter)
            pixmap = QPixmap(str(image_path))
            image_label.setPixmap(
                pixmap.scaledToWidth(820, Qt.SmoothTransformation)
                if not pixmap.isNull()
                else QPixmap()
            )
            if pixmap.isNull():
                image_label.setText(f"无法加载预览图：{image_path.name}")

            page_layout.addWidget(page_label)
            page_layout.addWidget(image_label)
            layout.addWidget(page_frame)

        self.scroll.setWidget(container)

    def _show_error(self, message: str) -> None:
        error = QLabel(message)
        error.setWordWrap(True)
        error.setStyleSheet(
            "background: #fff3f0; color: #7e2b1f; border: 1px solid #efc1b8; padding: 14px;"
        )
        self.scroll.setWidget(error)
        self.status_label.setText("PDF 预览生成失败")

    def _export_pdf(self) -> None:
        if not self.pdf_path or not self.pdf_path.exists():
            QMessageBox.warning(self, "无法导出", "当前订单的 PDF 文件不存在。")
            return
        try:
            target_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出 PDF",
                str(self.pdf_path),
                "PDF Files (*.pdf)",
            )
            if not target_path:
                return
            destination = Path(target_path)
            if destination.suffix.lower() != ".pdf":
                destination = destination.with_suffix(".pdf")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.pdf_path, destination)
            QMessageBox.information(self, "导出成功", f"PDF 已导出到：{destination}")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", f"导出 PDF 失败：{exc}")


class OrderImportWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        file_path: str,
        api_key: str,
        catalogs: dict[str, list[str]],
        supplemental_prompt: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.api_key = api_key
        self.catalogs = catalogs
        self.supplemental_prompt = supplemental_prompt

    def run(self) -> None:
        try:
            result = analyze_order_document(
                self.file_path,
                self.api_key,
                self.catalogs,
                self.supplemental_prompt,
            )
        except OrderImportError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"分析客单时发生未知错误：{exc}")
        else:
            self.completed.emit(result)

class OrderFormTab(QWidget):
    def __init__(self, db: Database, refresh_callback) -> None:
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self.selected_images: list[str] = []
        self.option_boxes: dict[str, list[QCheckBox]] = {}
        self.note_fields: dict[str, QPlainTextEdit] = {}
        self.note_red_boxes: dict[str, QCheckBox] = {}
        self.import_worker: OrderImportWorker | None = None
        self._build_ui()
        self.refresh_auto_order_no()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)

        layout.addWidget(self._build_import_group())
        layout.addWidget(self._build_basic_info_group())
        layout.addWidget(self._build_options_group("2. 材质及做法", "materials", MATERIALS))
        layout.addWidget(self._build_options_group("3. 电镀工艺", "plating", PLATING))
        layout.addWidget(self._build_options_group("4. 焊针配件", "accessories", ACCESSORIES))
        layout.addWidget(self._build_options_group("5. 抛光工艺", "polishing", POLISHING))
        layout.addWidget(self._build_coloring_group())
        layout.addWidget(self._build_resin_group())
        layout.addWidget(self._build_packaging_group())
        layout.addWidget(self._build_back_mode_group())
        layout.addWidget(self._build_global_note_group())
        layout.addWidget(self._build_images_group())

        button_row = QHBoxLayout()
        button_row.addStretch()
        reset_button = QPushButton("清空表单")
        reset_button.clicked.connect(self.reset_form)
        save_button = QPushButton("保存订单")
        save_button.clicked.connect(self.save_order)
        save_button.setStyleSheet(
            "QPushButton { background: #183153; color: white; padding: 8px 18px; border-radius: 8px; }"
        )
        button_row.addWidget(reset_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)
        layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _build_import_group(self) -> QGroupBox:
        group = QGroupBox("客单智能导入")
        layout = QVBoxLayout(group)
        description = QLabel(
            "上传 Word 或表格客单，由 DeepSeek V4 Flash 识别后展示摘要，确认后自动回填。"
            "原始文件不会保存到系统中。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key"))
        self.deepseek_api_key = QLineEdit(os.environ.get("DEEPSEEK_API_KEY", ""))
        self.deepseek_api_key.setEchoMode(QLineEdit.Password)
        self.deepseek_api_key.setPlaceholderText("仅用于本次运行；也可设置 DEEPSEEK_API_KEY")
        key_row.addWidget(self.deepseek_api_key, 1)
        layout.addLayout(key_row)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("补充提示词"))
        self.import_supplemental_prompt = QPlainTextEdit()
        self.import_supplemental_prompt.setPlaceholderText(
            "可选，例如：客户把“仿金”写作 FG；本单数量以装箱清单为准。"
        )
        self.import_supplemental_prompt.setMaximumHeight(70)
        prompt_row.addWidget(self.import_supplemental_prompt, 1)
        layout.addLayout(prompt_row)

        action_row = QHBoxLayout()
        self.import_order_button = QPushButton("上传客单并自动分析")
        self.import_order_button.clicked.connect(self.start_order_import)
        action_row.addWidget(self.import_order_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.import_status = QLabel(
            "支持 .docx、.xlsx、.xlsm、.xls、.csv、.tsv、.html、.htm，单个文件不超过 20 MB。"
        )
        self.import_status.setWordWrap(True)
        self.import_status.setStyleSheet("color: #66758a;")
        layout.addWidget(self.import_status)
        return group

    def _import_catalogs(self) -> dict[str, list[str]]:
        return {
            "order_type": ORDER_TYPES,
            "quantity_unit": QUANTITY_UNITS,
            "materials": MATERIALS,
            "plating": PLATING,
            "accessories": ACCESSORIES,
            "polishing": POLISHING,
            "coloring": COLORING_OPTIONS,
            "resin": RESIN_OPTIONS,
            "packaging": PACKAGING,
            "back_mode": BACK_MODES,
        }

    def start_order_import(self) -> None:
        if self.import_worker and self.import_worker.isRunning():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择客户订单",
            "",
            "客户订单 (*.docx *.xlsx *.xlsm *.xls *.csv *.tsv *.html *.htm)",
        )
        if not file_path:
            return
        api_key = self.deepseek_api_key.text().strip()
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先填写 DeepSeek API Key。")
            self.deepseek_api_key.setFocus()
            return

        self.import_order_button.setEnabled(False)
        self.import_status.setText(f"正在读取并分析：{Path(file_path).name} …")
        self.import_status.setStyleSheet("color: #1565c0;")
        worker = OrderImportWorker(
            file_path,
            api_key,
            self._import_catalogs(),
            self.import_supplemental_prompt.toPlainText().strip(),
            self,
        )
        self.import_worker = worker
        worker.completed.connect(self._on_order_import_completed)
        worker.failed.connect(self._on_order_import_failed)
        worker.finished.connect(self._finish_order_import)
        worker.start()

    def _finish_order_import(self) -> None:
        self.import_order_button.setEnabled(True)
        worker = self.import_worker
        self.import_worker = None
        if worker:
            worker.deleteLater()

    def _on_order_import_failed(self, message: str) -> None:
        self.import_status.setText("客单分析失败。")
        self.import_status.setStyleSheet("color: #c62828;")
        QMessageBox.critical(self, "自动填写失败", message)

    def _on_order_import_completed(self, data: dict) -> None:
        labels = {
            "order_type": "订单类型", "salesman": "业务员", "product_name": "品名",
            "order_date": "下单日期", "delivery_date": "交货日期", "quantity": "数量",
            "quantity_unit": "单位", "unit_price": "单价", "extra_fee": "附加费用",
            "production_no": "生产制号", "bi_no": "PO编号", "materials": "材质及做法",
            "plating": "电镀工艺", "accessories": "焊针配件", "polishing": "抛光工艺",
            "coloring": "上色", "resin": "树脂", "packaging": "包装", "back_mode": "背模",
        }
        summary: list[str] = []
        for key, label in labels.items():
            value = data.get(key)
            if value not in (None, "", []):
                rendered = "、".join(value) if isinstance(value, list) else str(value)
                summary.append(f"{label}：{rendered}")
        if not summary:
            self.import_status.setText("未识别到可回填的订单字段。")
            QMessageBox.warning(self, "没有可用结果", "客单已分析，但未识别到可回填字段。")
            return
        preview = "\n".join(summary[:18])
        if len(summary) > 18:
            preview += f"\n…另有 {len(summary) - 18} 项备注或工艺信息"
        answer = QMessageBox.question(
            self,
            "确认自动填写",
            f"已识别以下内容：\n\n{preview}\n\n是否回填到当前表单？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            self.import_status.setText("分析完成，已取消回填。")
            self.import_status.setStyleSheet("color: #66758a;")
            return
        self._apply_imported_order(data)
        self.import_status.setText("客单分析完成，识别结果已回填；请核对后保存订单。")
        self.import_status.setStyleSheet("color: #2e7d32;")

    @staticmethod
    def _set_checked_values(boxes: list[QCheckBox], values: list[str]) -> None:
        selected = set(values)
        for box in boxes:
            box.setChecked(box.text() in selected)

    def _apply_imported_order(self, data: dict) -> None:
        line_edits = {
            "salesman": self.salesman, "product_name": self.product_name,
            "unit_price": self.unit_price, "extra_fee": self.extra_fee,
            "production_no": self.production_no, "bi_no": self.bi_no,
            "width_mm": self.width_mm, "height_mm": self.height_mm,
            "thickness_mm": self.thickness_mm, "packaging_rule": self.packaging_rule,
        }
        for key, widget in line_edits.items():
            if data.get(key) not in (None, ""):
                widget.setText(str(data[key]))
        if data.get("quantity") is not None:
            self.quantity.setText(str(data["quantity"]))
        if data.get("order_type"):
            self.order_type.setCurrentText(data["order_type"])
        if data.get("quantity_unit"):
            self.quantity_unit.setCurrentText(data["quantity_unit"])

        for key, widget in (("delivery_date", self.delivery_date),):
            if data.get(key):
                parsed = QDate.fromString(data[key], "yyyy-MM-dd")
                if parsed.isValid():
                    widget.setDate(parsed)
        if "size_as_sample" in data:
            self.size_as_sample.setChecked(bool(data["size_as_sample"]))

        for key in ("materials", "plating", "accessories", "polishing"):
            if key in data:
                self._set_checked_values(self.option_boxes[key], data[key])
        for key, boxes in (
            ("coloring", self.coloring_boxes),
            ("resin", self.resin_options),
            ("packaging", self.packaging_boxes),
        ):
            if key in data:
                self._set_checked_values(boxes, data[key])
        if data.get("back_mode"):
            self.back_mode.setCurrentText(data["back_mode"])

        note_fields = {
            "material_note": self.note_fields["materials"],
            "plating_note": self.note_fields["plating"],
            "accessories_note": self.note_fields["accessories"],
            "polishing_note": self.note_fields["polishing"],
            "coloring_note": self.coloring_note,
            "resin_note": self.resin_note, "packaging_note": self.packaging_note,
            "back_mode_note": self.back_mode_note, "global_note": self.global_note,
        }
        for key, widget in note_fields.items():
            if data.get(key) not in (None, ""):
                widget.setPlainText(str(data[key]))
        self.refresh_auto_order_no()
    def _build_basic_info_group(self) -> QGroupBox:
        group = QGroupBox("1. 抬头与基础信息")
        form = QFormLayout(group)

        self.order_type = QComboBox()
        self.order_type.addItems(ORDER_TYPES)
        self.salesman = QLineEdit()
        self.order_prefix_no = QComboBox()
        self.order_prefix_no.addItems(ORDER_PREFIX_VALUES)
        self.order_prefix_no.setCurrentText("1")
        self.order_prefix_no.currentIndexChanged.connect(self.refresh_auto_order_no)
        self.order_no = QLineEdit()
        self.product_name = QLineEdit()
        self.order_date = QDateEdit(QDate.currentDate())
        self.order_date.setCalendarPopup(True)
        self.order_date.setDisplayFormat("yyyy-MM-dd")
        self.order_date.dateChanged.connect(self.refresh_auto_order_no)
        self.delivery_date = QDateEdit(QDate.currentDate())
        self.delivery_date.setCalendarPopup(True)
        self.delivery_date.setDisplayFormat("yyyy-MM-dd")
        self.quantity = QLineEdit()
        self.quantity_unit = QComboBox()
        self.quantity_unit.addItems(QUANTITY_UNITS)
        self.unit_price = QLineEdit()
        self.extra_fee = QLineEdit()
        self.unit_price.setPlaceholderText("仅保存到数据库，不打印")
        self.extra_fee.setPlaceholderText("\u4ec5\u4fdd\u5b58\u5230\u6570\u636e\u5e93\uff0c\u4e0d\u6253\u5370")
        self.production_no = QLineEdit()
        self.bi_no = QLineEdit()
        self.width_mm = QLineEdit()
        self.height_mm = QLineEdit()
        self.thickness_mm = QLineEdit()
        self.size_as_sample = QCheckBox("如样")

        self.manual_order_no = QRadioButton("手动填写")
        self.auto_order_no = QRadioButton("自动生成")
        self.auto_order_no.setChecked(True)
        self.order_no_mode = QButtonGroup(self)
        self.order_no_mode.addButton(self.manual_order_no)
        self.order_no_mode.addButton(self.auto_order_no)
        self.manual_order_no.toggled.connect(self._update_order_no_mode)
        self.auto_order_no.toggled.connect(self._update_order_no_mode)
        self.generate_order_no_button = QPushButton("重新生成")
        self.generate_order_no_button.clicked.connect(self.refresh_auto_order_no)

        order_no_mode_row = QWidget()
        order_no_mode_layout = QHBoxLayout(order_no_mode_row)
        order_no_mode_layout.setContentsMargins(0, 0, 0, 0)
        order_no_mode_layout.addWidget(self.manual_order_no)
        order_no_mode_layout.addWidget(self.auto_order_no)
        order_no_mode_layout.addStretch()

        order_no_row = QWidget()
        order_no_layout = QHBoxLayout(order_no_row)
        order_no_layout.setContentsMargins(0, 0, 0, 0)
        order_no_layout.addWidget(self.order_no)
        order_no_layout.addWidget(self.generate_order_no_button)

        quantity_row = QWidget()
        quantity_layout = QHBoxLayout(quantity_row)
        quantity_layout.setContentsMargins(0, 0, 0, 0)
        quantity_layout.addWidget(self.quantity)
        quantity_layout.addWidget(self.quantity_unit)

        prefix_row = QWidget()
        prefix_layout = QHBoxLayout(prefix_row)
        prefix_layout.setContentsMargins(0, 0, 0, 0)
        prefix_layout.addWidget(QLabel("TWD"))
        prefix_layout.addWidget(self.order_prefix_no)
        prefix_layout.addStretch()

        form.addRow("订单类型", self.order_type)
        form.addRow("业务员", self.salesman)
        form.addRow("订单前缀", prefix_row)
        form.addRow("订单编号方式", order_no_mode_row)
        form.addRow("订单编号", order_no_row)
        form.addRow("品名", self.product_name)
        form.addRow("下单日期", self.order_date)
        form.addRow("交货日期", self.delivery_date)
        form.addRow("数量", quantity_row)
        form.addRow("单价", self.unit_price)
        form.addRow("附加费用", self.extra_fee)
        form.addRow("PO编号", self.bi_no)
        form.addRow("生产制号", self.production_no)

        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(QLabel("宽"))
        size_layout.addWidget(self.width_mm)
        size_layout.addWidget(QLabel("高"))
        size_layout.addWidget(self.height_mm)
        size_layout.addWidget(QLabel("厚度"))
        size_layout.addWidget(self.thickness_mm)
        size_layout.addWidget(self.size_as_sample)
        form.addRow("尺寸信息 (mm)", size_row)

        self._update_order_no_mode()
        return group

    def _build_options_group(self, title: str, key: str, options: list[str]) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        grid = QGridLayout()
        boxes: list[QCheckBox] = []
        for index, option in enumerate(options):
            box = QCheckBox(option)
            grid.addWidget(box, index // 3, index % 3)
            boxes.append(box)
        layout.addLayout(grid)

        note = QPlainTextEdit()
        note.setPlaceholderText("补充说明 / 特殊要求")
        note.setFixedHeight(70)
        note_row = QHBoxLayout()
        note_row.addWidget(QLabel("备注"))
        note_red = QCheckBox("红字")
        note_red.setChecked(True)
        note_row.addStretch()
        note_row.addWidget(note_red)
        layout.addLayout(note_row)
        layout.addWidget(note)

        self.option_boxes[key] = boxes
        self.note_fields[key] = note
        self.note_red_boxes[key] = note_red
        return group

    def _build_coloring_group(self) -> QGroupBox:
        group = QGroupBox("6. 上色模块")
        layout = QVBoxLayout(group)
        self.coloring_boxes = [QCheckBox(option) for option in COLORING_OPTIONS]
        row = QHBoxLayout()
        for box in self.coloring_boxes:
            row.addWidget(box)
        row.addStretch()
        layout.addLayout(row)

        coloring_note_row = QHBoxLayout()
        coloring_note_row.addWidget(QLabel("备注"))
        self.coloring_note_red = QCheckBox("红字")
        self.coloring_note_red.setChecked(True)
        coloring_note_row.addStretch()
        coloring_note_row.addWidget(self.coloring_note_red)
        layout.addLayout(coloring_note_row)
        self.coloring_note = QPlainTextEdit()
        self.coloring_note.setPlaceholderText("填写上色补充要求")
        layout.addWidget(self.coloring_note)
        return group

    def _build_resin_group(self) -> QGroupBox:
        group = QGroupBox("7. 树脂(滴胶)模块")
        layout = QVBoxLayout(group)
        self.resin_options = [QCheckBox(option) for option in RESIN_OPTIONS]
        grid = QGridLayout()
        for index, box in enumerate(self.resin_options):
            grid.addWidget(box, index // 3, index % 3)
        layout.addLayout(grid)
        resin_note_row = QHBoxLayout()
        resin_note_row.addWidget(QLabel("备注"))
        self.resin_note_red = QCheckBox("红字")
        self.resin_note_red.setChecked(True)
        resin_note_row.addStretch()
        resin_note_row.addWidget(self.resin_note_red)
        layout.addLayout(resin_note_row)
        self.resin_note = QPlainTextEdit()
        self.resin_note.setPlaceholderText("树脂工艺补充说明")
        self.resin_note.setFixedHeight(70)
        layout.addWidget(self.resin_note)
        return group

    def _build_packaging_group(self) -> QGroupBox:
        group = QGroupBox("8. 包装模块")
        layout = QVBoxLayout(group)
        self.packaging_boxes = [QCheckBox(option) for option in PACKAGING]
        grid = QGridLayout()
        for index, box in enumerate(self.packaging_boxes):
            grid.addWidget(box, index // 4, index % 4)
        layout.addLayout(grid)
        self.packaging_rule = QLineEdit()
        self.packaging_rule.setPlaceholderText("例如：每一个小袋装 10 个大袋")
        self.packaging_note = QPlainTextEdit()
        self.packaging_note.setPlaceholderText("特殊包装要求")
        self.packaging_note.setFixedHeight(70)
        layout.addWidget(QLabel("组合包装规则"))
        layout.addWidget(self.packaging_rule)
        packaging_note_row = QHBoxLayout()
        packaging_note_row.addWidget(QLabel("备注"))
        self.packaging_note_red = QCheckBox("红字")
        self.packaging_note_red.setChecked(True)
        packaging_note_row.addStretch()
        packaging_note_row.addWidget(self.packaging_note_red)
        layout.addLayout(packaging_note_row)
        layout.addWidget(self.packaging_note)
        return group

    def _build_back_mode_group(self) -> QGroupBox:
        group = QGroupBox("9. 背模要求")
        layout = QVBoxLayout(group)
        self.back_mode = QComboBox()
        self.back_mode.addItems(BACK_MODES)
        self.back_mode_note = QPlainTextEdit()
        self.back_mode_note.setPlaceholderText("背模工艺补充说明")
        self.back_mode_note.setFixedHeight(70)
        layout.addWidget(self.back_mode)
        back_mode_note_row = QHBoxLayout()
        back_mode_note_row.addWidget(QLabel("备注"))
        self.back_mode_note_red = QCheckBox("红字")
        self.back_mode_note_red.setChecked(True)
        back_mode_note_row.addStretch()
        back_mode_note_row.addWidget(self.back_mode_note_red)
        layout.addLayout(back_mode_note_row)
        layout.addWidget(self.back_mode_note)
        return group

    def _build_global_note_group(self) -> QGroupBox:
        group = QGroupBox("10. 高级备注与图样说明")
        layout = QVBoxLayout(group)
        self.global_note_red = QCheckBox("备注字体变红")
        self.global_note_red.setChecked(True)
        self.global_note = QPlainTextEdit()
        self.global_note.setPlaceholderText("全局注意事项")
        self.global_note.setFixedHeight(100)
        layout.addWidget(self.global_note_red)
        layout.addWidget(QLabel("注意事项"))
        layout.addWidget(self.global_note)
        return group

    def _build_images_group(self) -> QGroupBox:
        group = QGroupBox("图样附件区（最多 3 张）")
        layout = QVBoxLayout(group)

        button_row = QHBoxLayout()
        add_button = QPushButton("选择图片")
        add_button.clicked.connect(self.pick_images)
        clear_button = QPushButton("清空图片")
        clear_button.clicked.connect(self.clear_images)
        button_row.addWidget(add_button)
        button_row.addWidget(clear_button)
        button_row.addStretch()

        self.image_tip = QLabel("未选择图片")
        self.preview_list = QListWidget()
        self.preview_list.setViewMode(QListWidget.IconMode)
        self.preview_list.setIconSize(QSize(120, 120))
        self.preview_list.setResizeMode(QListWidget.Adjust)
        self.preview_list.setMovement(QListWidget.Static)
        self.preview_list.setMinimumHeight(160)

        layout.addLayout(button_row)
        layout.addWidget(self.image_tip)
        layout.addWidget(self.preview_list)
        return group

    def _update_order_no_mode(self) -> None:
        is_auto = self.auto_order_no.isChecked()
        self.order_no.setReadOnly(is_auto)
        self.generate_order_no_button.setEnabled(is_auto)
        if is_auto:
            self.refresh_auto_order_no()
        else:
            self.order_no.setPlaceholderText("手动输入订单编号")

    def refresh_auto_order_no(self) -> None:
        if not getattr(self, "auto_order_no", None) or not self.auto_order_no.isChecked():
            return
        order_date = self.order_date.date().toString("yyyy-MM-dd")
        order_prefix_no = int(self.order_prefix_no.currentText())
        self.order_no.setText(self.db.get_next_order_no(order_date, order_prefix_no))

    def pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图样附件",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not files:
            return
        combined = self.selected_images + files
        deduplicated: list[str] = []
        for path in combined:
            if path not in deduplicated:
                deduplicated.append(path)
        if len(deduplicated) > 3:
            QMessageBox.warning(self, "图片数量超限", "最多只能选择 3 张图片。")
            deduplicated = deduplicated[:3]
        self.selected_images = deduplicated
        self.refresh_previews()

    def clear_images(self) -> None:
        self.selected_images = []
        self.refresh_previews()

    def refresh_previews(self) -> None:
        self.preview_list.clear()
        if not self.selected_images:
            self.image_tip.setText("未选择图片")
            return

        self.image_tip.setText(f"已选择 {len(self.selected_images)} / 3 张图片")
        for image_path in self.selected_images:
            pixmap = QPixmap(image_path)
            item = QListWidgetItem(Path(image_path).name)
            item.setToolTip(image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item.setIcon(QIcon(scaled))
            self.preview_list.addItem(item)

    def _selected_values(self, key: str) -> list[str]:
        return [box.text() for box in self.option_boxes[key] if box.isChecked()]

    def _selected_checkboxes(self, boxes: list[QCheckBox]) -> list[str]:
        return [box.text() for box in boxes if box.isChecked()]

    def _collect_payload(self) -> dict:
        order_date = self.order_date.date().toString("yyyy-MM-dd")
        order_no = self.order_no.text().strip()
        order_prefix_no = int(self.order_prefix_no.currentText())
        if self.auto_order_no.isChecked():
            order_no = self.db.get_next_order_no(order_date, order_prefix_no)
            self.order_no.setText(order_no)
        if not order_no:
            raise ValueError("订单编号不能为空。")
        quantity_text = self.quantity.text().strip()
        quantity_value = int(quantity_text) if quantity_text else None
        unit_price_text = self.unit_price.text().strip()
        unit_price_value = float(unit_price_text) if unit_price_text else None
        extra_fee_text = self.extra_fee.text().strip()
        extra_fee_value = float(extra_fee_text) if extra_fee_text else None

        return {
            "order_type": self.order_type.currentText(),
            "salesman": self.salesman.text().strip(),
            "order_no": order_no,
            "order_prefix_no": order_prefix_no,
            "product_name": self.product_name.text().strip(),
            "order_date": order_date,
            "delivery_date": self.delivery_date.date().toString("yyyy-MM-dd"),
            "quantity": quantity_value,
            "quantity_unit": self.quantity_unit.currentText(),
            "unit_price": unit_price_value,
            "extra_fee": extra_fee_value,
            "production_no": self.production_no.text().strip(),
            "bi_no": self.bi_no.text().strip(),
            "width_mm": self.width_mm.text().strip(),
            "height_mm": self.height_mm.text().strip(),
            "thickness_mm": self.thickness_mm.text().strip(),
            "size_as_sample": 1 if self.size_as_sample.isChecked() else 0,
            "materials_json": dumps_json(self._selected_values("materials")),
            "material_note": self.note_fields["materials"].toPlainText().strip(),
            "material_note_red": 1 if self.note_red_boxes["materials"].isChecked() else 0,
            "plating_json": dumps_json(self._selected_values("plating")),
            "plating_note": self.note_fields["plating"].toPlainText().strip(),
            "plating_note_red": 1 if self.note_red_boxes["plating"].isChecked() else 0,
            "accessories_json": dumps_json(self._selected_values("accessories")),
            "accessories_note": self.note_fields["accessories"].toPlainText().strip(),
            "accessories_note_red": 1 if self.note_red_boxes["accessories"].isChecked() else 0,
            "polishing_json": dumps_json(self._selected_values("polishing")),
            "polishing_note": self.note_fields["polishing"].toPlainText().strip(),
            "polishing_note_red": 1 if self.note_red_boxes["polishing"].isChecked() else 0,
            "coloring_json": dumps_json(self._selected_checkboxes(self.coloring_boxes)),
            "coloring_text": "",
            "coloring_note": self.coloring_note.toPlainText().strip(),
            "coloring_note_red": 1 if self.coloring_note_red.isChecked() else 0,
            "resin_json": dumps_json(self._selected_checkboxes(self.resin_options)),
            "resin_note": self.resin_note.toPlainText().strip(),
            "resin_note_red": 1 if self.resin_note_red.isChecked() else 0,
            "packaging_json": dumps_json(self._selected_checkboxes(self.packaging_boxes)),
            "packaging_rule": self.packaging_rule.text().strip(),
            "packaging_note": self.packaging_note.toPlainText().strip(),
            "packaging_note_red": 1 if self.packaging_note_red.isChecked() else 0,
            "back_mode": self.back_mode.currentText(),
            "back_mode_note": self.back_mode_note.toPlainText().strip(),
            "back_mode_note_red": 1 if self.back_mode_note_red.isChecked() else 0,
            "global_note": self.global_note.toPlainText().strip(),
            "global_note_red": 1 if self.global_note_red.isChecked() else 0,
        }

    def save_order(self) -> None:
        try:
            payload = self._collect_payload()
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))
            return

        try:
            saved_images = copy_images(payload["order_no"], self.selected_images, IMAGES_DIR)
            payload["image_paths_json"] = dumps_json(saved_images)
            self.db.insert_order(payload)
        except ValueError:
            QMessageBox.warning(self, "\u6821\u9a8c\u5931\u8d25", "\u6570\u91cf\u5fc5\u987b\u662f\u6574\u6570\uff0c\u5355\u4ef7\u548c\u9644\u52a0\u8d39\u7528\u5fc5\u987b\u662f\u6570\u5b57\u3002")
            return
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "保存失败", f"数据库写入失败：{exc}")
            self.refresh_auto_order_no()
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", f"保存订单时出错：{exc}")
            return

        QMessageBox.information(self, "保存成功", "订单已保存到本地数据库。")
        self.reset_form()
        self.refresh_callback()

    def reset_form(self) -> None:
        self.order_type.setCurrentIndex(0)
        self.salesman.clear()
        self.order_prefix_no.setCurrentText("1")
        self.manual_order_no.setChecked(False)
        self.auto_order_no.setChecked(True)
        self.product_name.clear()
        self.order_date.setDate(QDate.currentDate())
        self.delivery_date.setDate(QDate.currentDate())
        self.quantity.clear()
        self.quantity_unit.setCurrentIndex(0)
        self.unit_price.clear()
        self.extra_fee.clear()
        self.production_no.clear()
        self.bi_no.clear()
        self.width_mm.clear()
        self.height_mm.clear()
        self.thickness_mm.clear()
        self.size_as_sample.setChecked(False)

        for boxes in self.option_boxes.values():
            for box in boxes:
                box.setChecked(False)
        for note in self.note_fields.values():
            note.clear()
        for note_red in self.note_red_boxes.values():
            note_red.setChecked(True)

        for box in self.resin_options:
            box.setChecked(False)
        self.resin_note.clear()
        self.resin_note_red.setChecked(True)
        for box in self.coloring_boxes:
            box.setChecked(False)
        self.coloring_note_red.setChecked(True)
        for box in self.packaging_boxes:
            box.setChecked(False)
        self.packaging_rule.clear()
        self.packaging_note.clear()
        self.packaging_note_red.setChecked(True)
        self.coloring_note.clear()
        self.back_mode.setCurrentIndex(0)
        self.back_mode_note.clear()
        self.back_mode_note_red.setChecked(True)
        self.global_note_red.setChecked(True)
        self.global_note.clear()
        self.clear_images()
        self.refresh_auto_order_no()


class OrderListTab(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()
        self.load_orders()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单号搜索")
        self.search_salesman = QLineEdit()
        self.search_salesman.setPlaceholderText("按业务员搜索")
        self.search_delivery_date = QDateEdit(QDate.currentDate())
        self.search_delivery_date.setCalendarPopup(True)
        self.search_delivery_date.setDisplayFormat("yyyy-MM-dd")
        self.search_delivery_date.setSpecialValueText("全部")
        self.search_delivery_date.setDate(QDate(2000, 1, 1))
        self.search_delivery_date.setMinimumDate(QDate(2000, 1, 1))
        self.search_delivery_date.setCurrentSection(QDateEdit.YearSection)
        search_button = QPushButton("搜索")
        search_button.clicked.connect(self.load_orders)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        preview_button = QPushButton("预览选中订单")
        preview_button.clicked.connect(self.preview_selected_order)
        export_button = QPushButton("批量导出 PDF")
        export_button.clicked.connect(self.export_selected_orders)

        filters.addWidget(QLabel("订单号"))
        filters.addWidget(self.search_order_no)
        filters.addWidget(QLabel("业务员"))
        filters.addWidget(self.search_salesman)
        filters.addWidget(QLabel("交期"))
        filters.addWidget(self.search_delivery_date)
        filters.addWidget(search_button)
        filters.addWidget(reset_button)
        filters.addWidget(preview_button)
        filters.addWidget(export_button)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "订单类型", "业务员", "订单编号", "品名", "数量", "交货日期"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_detail)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("可多选订单批量导出，双击行或使用按钮打开预览")
        tip.setStyleSheet("color: #66758a;")
        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addWidget(self.table)

    def _delivery_filter_value(self) -> str:
        minimum = self.search_delivery_date.minimumDate()
        selected = self.search_delivery_date.date()
        return "" if selected == minimum else selected.toString("yyyy-MM-dd")

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_salesman.clear()
        self.search_delivery_date.setDate(self.search_delivery_date.minimumDate())
        self.load_orders()

    def load_orders(self) -> None:
        rows = self.db.search_orders(
            order_no_keyword=self.search_order_no.text(),
            salesman_keyword=self.search_salesman.text(),
            delivery_date=self._delivery_filter_value(),
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            quantity_text = ""
            if row["quantity"] not in (None, ""):
                quantity_unit = row.get("quantity_unit") or "个"
                quantity_text = f"{row['quantity']}{quantity_unit}"
            values = [
                row["id"],
                row["order_type"],
                row["salesman"] or "",
                row["order_no"],
                row["product_name"] or "",
                quantity_text,
                row["delivery_date"] or "",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def show_detail(self, row: int, _column: int) -> None:
        order_id_item = self.table.item(row, 0)
        if not order_id_item:
            return
        record = self.db.get_order(int(order_id_item.text()))
        if not record:
            return
        dialog = OrderPreviewDialog(record, self)
        dialog.exec()

    def preview_selected_order(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            QMessageBox.warning(self, "无法预览", "请只选择一条订单后再预览。")
            return
        self.show_detail(selected_rows[0].row(), 0)

    def export_selected_orders(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "无法导出", "请先选择至少一条订单。")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        if not target_dir:
            return

        export_dir = Path(target_dir)
        success_count = 0
        failed_orders: list[str] = []
        for model_index in selected_rows:
            order_id_item = self.table.item(model_index.row(), 0)
            if not order_id_item:
                continue
            record = self.db.get_order(int(order_id_item.text()))
            if not record:
                continue
            try:
                artifacts = generate_order_preview_artifacts(record)
                destination = export_dir / artifacts.pdf_path.name
                shutil.copy2(artifacts.pdf_path, destination)
                success_count += 1
            except Exception:
                failed_orders.append(record.get("order_no") or str(order_id_item.text()))

        if failed_orders:
            QMessageBox.warning(
                self,
                "部分导出失败",
                f"成功导出 {success_count} 份，失败 {len(failed_orders)} 份：{', '.join(failed_orders)}",
            )
            return

        QMessageBox.information(
            self,
            "导出成功",
            f"已导出 {success_count} 份 PDF 到：{export_dir}",
        )


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None, logout_callback=None) -> None:
        super().__init__()
        self.db = db or Database(DB_PATH)
        self.db.initialize()
        self.logout_callback = logout_callback

        self.setWindowTitle("泰威德五金工艺品厂 - 电子订单管理系统 MVP")
        self.resize(1280, 860)

        container = QWidget()
        layout = QVBoxLayout(container)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        logout_button = QPushButton("退出登录")
        logout_button.clicked.connect(self.logout)
        top_bar.addWidget(logout_button)
        layout.addLayout(top_bar)

        tabs = QTabWidget()
        self.order_list_tab = OrderListTab(self.db)
        self.order_form_tab = OrderFormTab(self.db, self.order_list_tab.load_orders)
        tabs.addTab(self.order_form_tab, "新建订单")
        tabs.addTab(self.order_list_tab, "本地订单管理")
        layout.addWidget(tabs)
        self.setCentralWidget(container)

    def logout(self) -> None:
        if self.logout_callback:
            self.logout_callback(self)
            return
        self.close()


class FinanceOrderListTab(QWidget):
    EXPORT_HEADERS = ["订单编号", "PO号", "生产制号", "数量", "单价", "附加费用", "出货日期"]

    def __init__(self, db: Database, refresh_callback=None) -> None:
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self._build_ui()
        self.load_orders()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号检索")
        self.search_bi_no = QLineEdit()
        self.search_bi_no.setPlaceholderText("按 PO 号检索")
        self.search_production_no = QLineEdit()
        self.search_production_no.setPlaceholderText("按生产制号检索")
        self.search_order_date_from = QDateEdit(QDate(2000, 1, 1))
        self.search_order_date_from.setCalendarPopup(True)
        self.search_order_date_from.setDisplayFormat("yyyy-MM-dd")
        self.search_order_date_to = QDateEdit(QDate.currentDate())
        self.search_order_date_to.setCalendarPopup(True)
        self.search_order_date_to.setDisplayFormat("yyyy-MM-dd")

        search_button = QPushButton("检索")
        search_button.clicked.connect(self.load_orders)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        export_button = QPushButton("按下单日期导出 Excel")
        export_button.clicked.connect(self.export_excel)
        select_all_button = QPushButton("全选")
        select_all_button.clicked.connect(self.select_all_rows)
        clear_selection_button = QPushButton("取消全选")
        clear_selection_button.clicked.connect(self.clear_all_rows)
        mark_paid_button = QPushButton("批量设为已支付")
        mark_paid_button.clicked.connect(lambda: self.update_selected_paid_status(1))
        mark_unpaid_button = QPushButton("批量设为未支付")
        mark_unpaid_button.clicked.connect(lambda: self.update_selected_paid_status(0))

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("PO号"), 0, 2)
        filters.addWidget(self.search_bi_no, 0, 3)
        filters.addWidget(QLabel("生产制号"), 1, 0)
        filters.addWidget(self.search_production_no, 1, 1)
        filters.addWidget(QLabel("下单日期从"), 1, 2)
        filters.addWidget(self.search_order_date_from, 1, 3)
        filters.addWidget(QLabel("下单日期到"), 2, 0)
        filters.addWidget(self.search_order_date_to, 2, 1)
        filters.addWidget(search_button, 2, 2)
        filters.addWidget(reset_button, 2, 3)

        actions = QHBoxLayout()
        actions.addWidget(select_all_button)
        actions.addWidget(clear_selection_button)
        actions.addWidget(mark_paid_button)
        actions.addWidget(mark_unpaid_button)
        actions.addStretch()
        actions.addWidget(export_button)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            ["选择", "ID", "支付状态", "订单编号", "PO号", "生产制号", "品名", "数量", "单价", "下单日期", "出货日期"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_detail)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("财务端支持查看订单、导出 Excel，并可勾选订单批量修改支付状态")
        tip.setStyleSheet("color: #66758a;")
        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addLayout(actions)
        layout.addWidget(self.table)

    def _format_quantity(self, row: dict) -> str:
        if row["quantity"] in (None, ""):
            return ""
        return f"{row['quantity']}{row.get('quantity_unit') or '个'}"

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_bi_no.clear()
        self.search_production_no.clear()
        self.search_order_date_from.setDate(QDate(2000, 1, 1))
        self.search_order_date_to.setDate(QDate.currentDate())
        self.load_orders()

    def load_orders(self) -> None:
        rows = self.db.search_finance_orders(
            order_no_keyword=self.search_order_no.text(),
            bi_no_keyword=self.search_bi_no.text(),
            production_no_keyword=self.search_production_no.text(),
            order_date_from=self.search_order_date_from.date().toString("yyyy-MM-dd"),
            order_date_to=self.search_order_date_to.date().toString("yyyy-MM-dd"),
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            checkbox_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row_index, 0, checkbox_item)

            values = [
                row["id"],
                "已支付" if row.get("paid_status") else "未支付",
                row["order_no"] or "",
                row["bi_no"] or "",
                row["production_no"] or "",
                row["product_name"] or "",
                self._format_quantity(row),
                "" if row["unit_price"] in (None, "") else str(row["unit_price"]),
                row["order_date"] or "",
                row["delivery_date"] or "",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index + 1, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def show_detail(self, row: int, _column: int) -> None:
        order_id_item = self.table.item(row, 1)
        if not order_id_item:
            return
        record = self.db.get_order(int(order_id_item.text()))
        if not record:
            return
        dialog = OrderPreviewDialog(record, self)
        dialog.exec()

    def _selected_order_ids(self) -> list[int]:
        selected_ids: list[int] = []
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            order_id_item = self.table.item(row_index, 1)
            if (
                check_item
                and order_id_item
                and check_item.checkState() == Qt.Checked
            ):
                selected_ids.append(int(order_id_item.text()))
        return selected_ids

    def select_all_rows(self) -> None:
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Checked)

    def clear_all_rows(self) -> None:
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Unchecked)

    def update_selected_paid_status(self, paid_status: int) -> None:
        order_ids = self._selected_order_ids()
        if not order_ids:
            QMessageBox.warning(self, "无法修改", "请先勾选至少一条订单。")
            return
        self.db.update_paid_status(order_ids, paid_status)
        self.load_orders()
        if self.refresh_callback:
            self.refresh_callback()
        status_text = "已支付" if paid_status else "未支付"
        QMessageBox.information(
            self,
            "修改成功",
            f"已将 {len(order_ids)} 条订单更新为“{status_text}”。",
        )

    def export_excel(self) -> None:
        order_date_from = self.search_order_date_from.date().toString("yyyy-MM-dd")
        order_date_to = self.search_order_date_to.date().toString("yyyy-MM-dd")
        if order_date_from > order_date_to:
            QMessageBox.warning(self, "导出失败", "下单开始日期不能晚于结束日期。")
            return

        rows = self.db.get_finance_export_rows(order_date_from, order_date_to)
        if not rows:
            QMessageBox.information(self, "没有数据", "当前下单日期范围内没有可导出的订单。")
            return

        default_name = f"财务订单导出_{order_date_from}_{order_date_to}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出财务订单 Excel",
            str(Path.cwd() / default_name),
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        export_rows: list[list] = []
        for row in rows:
            quantity_text = ""
            if row["quantity"] not in (None, ""):
                quantity_text = f"{row['quantity']}{row.get('quantity_unit') or '个'}"
            export_rows.append(
                [
                    row["order_no"] or "",
                    row["bi_no"] or "",
                    row["production_no"] or "",
                    quantity_text,
                    "" if row["unit_price"] in (None, "") else row["unit_price"],
                    "" if row.get("extra_fee") in (None, "") else row["extra_fee"],
                    row["delivery_date"] or "",
                ]
            )

        export_rows_to_excel(file_path, "对外收款对账", self.EXPORT_HEADERS, export_rows)
        QMessageBox.information(self, "导出成功", f"Excel 已导出到：\n{file_path}")


class OutsourcePaymentTab(QWidget):
    EXPORT_HEADERS = [
        "支付状态",
        "订单编号",
        "品名",
        "工艺",
        "加工厂",
        "产品数量",
        "备品数量",
        "合计数量",
        "加工单价",
        "应付金额",
        "日期",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()
        self.refresh_filter_options()
        self.load_records()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号检索")
        self.search_process_name = QComboBox()
        self.search_process_name.currentIndexChanged.connect(self.refresh_factory_options)
        self.search_factory_name = QComboBox()
        self.unpaid_only_checkbox = QCheckBox("仅显示未支付项")
        self.unpaid_only_checkbox.toggled.connect(self.load_records)

        search_button = QPushButton("检索")
        search_button.clicked.connect(self.load_records)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        select_all_button = QPushButton("全选")
        select_all_button.clicked.connect(self.select_all_rows)
        clear_selection_button = QPushButton("取消全选")
        clear_selection_button.clicked.connect(self.clear_all_rows)
        mark_paid_button = QPushButton("批量设为已支付")
        mark_paid_button.clicked.connect(lambda: self.update_selected_paid_status(1))
        mark_unpaid_button = QPushButton("批量设为未支付")
        mark_unpaid_button.clicked.connect(lambda: self.update_selected_paid_status(0))
        export_button = QPushButton("导出 Excel")
        export_button.clicked.connect(self.export_excel)

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("加工厂"), 0, 2)
        filters.addWidget(self.search_factory_name, 0, 3)
        filters.addWidget(QLabel("工艺"), 1, 0)
        filters.addWidget(self.search_process_name, 1, 1)
        filters.addWidget(self.unpaid_only_checkbox, 1, 2)
        filters.addWidget(search_button, 2, 2)
        filters.addWidget(reset_button, 2, 3)

        actions = QHBoxLayout()
        actions.addWidget(select_all_button)
        actions.addWidget(clear_selection_button)
        actions.addWidget(mark_paid_button)
        actions.addWidget(mark_unpaid_button)
        actions.addStretch()
        self.total_amount_label = QLabel("选中待付款总金额：0.00")
        self.total_amount_label.setStyleSheet("font-weight: 700; color: #213547;")
        actions.addWidget(self.total_amount_label)
        actions.addWidget(export_button)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            ["选择", "ID", "支付状态", "订单编号", "品名", "工艺", "加工厂", "外发数量", "加工单价", "应付金额", "出货日期"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_detail)
        self.table.itemChanged.connect(self._handle_item_changed)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("该页与外发登记系统共享外发记录，可按加工厂名称检索，并批量维护对外支付状态。")
        tip.setStyleSheet("color: #66758a;")
        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addLayout(actions)
        layout.addWidget(self.table)

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_factory_name.clear()
        self.search_process_name.clear()
        self.unpaid_only_checkbox.setChecked(False)
        self.load_records()

    def load_records(self) -> None:
        rows = self.db.search_outsource_records(
            order_no_keyword=self.search_order_no.text(),
            factory_keyword=self.search_factory_name.text(),
            process_keyword=self.search_process_name.text(),
        )
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            checkbox_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row_index, 0, checkbox_item)
            payable_amount = float(row["quantity"]) * float(row["unit_price"])

            values = [
                row["id"],
                "已支付" if row.get("paid_status") else "未支付",
                row["order_no"] or "",
                row.get("product_name") or "",
                row["process_name"] or "",
                row["factory_name"] or "",
                row["quantity"],
                row["unit_price"],
                f"{payable_amount:.2f}",
                row.get("delivery_date") or "",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index + 1, QTableWidgetItem(str(value)))
        self.table.blockSignals(False)
        self._update_total_amount()
        self.table.resizeColumnsToContents()

    def show_detail(self, row: int, _column: int) -> None:
        order_no_item = self.table.item(row, 3)
        if not order_no_item:
            return
        record = self.db.get_order_by_order_no(order_no_item.text())
        if not record:
            return
        dialog = OrderPreviewDialog(record, self)
        dialog.exec()

    def _selected_record_ids(self) -> list[int]:
        record_ids: list[int] = []
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            record_id_item = self.table.item(row_index, 1)
            if check_item and record_id_item and check_item.checkState() == Qt.Checked:
                record_ids.append(int(record_id_item.text()))
        return record_ids

    def select_all_rows(self) -> None:
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Checked)
        self.table.blockSignals(False)
        self._update_total_amount()

    def clear_all_rows(self) -> None:
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_total_amount()

    def update_selected_paid_status(self, paid_status: int) -> None:
        record_ids = self._selected_record_ids()
        if not record_ids:
            QMessageBox.warning(self, "无法修改", "请先勾选至少一条外发记录。")
            return
        self.db.update_outsource_paid_status(record_ids, paid_status)
        self.load_records()
        status_text = "已支付" if paid_status else "未支付"
        QMessageBox.information(
            self,
            "修改成功",
            f"已将 {len(record_ids)} 条外发记录更新为“{status_text}”。",
        )

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_total_amount()

    def _update_total_amount(self) -> None:
        total_amount = 0.0
        selected_count = 0
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            status_item = self.table.item(row_index, 2)
            amount_item = self.table.item(row_index, 9)
            if not check_item or not status_item or not amount_item:
                continue
            if check_item.checkState() != Qt.Checked:
                continue
            if status_item.text() != "未支付":
                continue
            selected_count += 1
            try:
                total_amount += float(amount_item.text())
            except ValueError:
                continue
        self.total_amount_label.setText(
            f"选中待付款总金额：{total_amount:.2f}（{selected_count}条）"
        )


class FinanceMainWindow(QMainWindow):
    def __init__(self, db: Database, logout_callback=None) -> None:
        super().__init__()
        self.logout_callback = logout_callback
        self.setWindowTitle("财务管理系统")
        self.resize(1200, 800)

        container = QWidget()
        layout = QVBoxLayout(container)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        logout_button = QPushButton("退出登录")
        logout_button.clicked.connect(self.logout)
        top_bar.addWidget(logout_button)
        layout.addLayout(top_bar)

        tabs = QTabWidget()
        self.profit_tab = FinanceProfitTab(db)
        tabs.addTab(OutsourcePaymentTab(db), "对外支付对账")
        tabs.addTab(FinanceOrderListTab(db, refresh_callback=self.profit_tab.load_rows), "对外收款对账")
        tabs.addTab(self.profit_tab, "盈亏统计")
        layout.addWidget(tabs)
        self.setCentralWidget(container)

    def logout(self) -> None:
        if self.logout_callback:
            self.logout_callback(self)
            return
        self.close()


class FinanceProfitTab(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()
        self.load_rows()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号检索")
        self.search_order_date_from = QDateEdit(QDate(2000, 1, 1))
        self.search_order_date_from.setCalendarPopup(True)
        self.search_order_date_from.setDisplayFormat("yyyy-MM-dd")
        self.search_order_date_to = QDateEdit(QDate.currentDate())
        self.search_order_date_to.setCalendarPopup(True)
        self.search_order_date_to.setDisplayFormat("yyyy-MM-dd")

        search_button = QPushButton("检索")
        search_button.clicked.connect(self.load_rows)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("下单日期从"), 0, 2)
        filters.addWidget(self.search_order_date_from, 0, 3)
        filters.addWidget(QLabel("下单日期到"), 1, 0)
        filters.addWidget(self.search_order_date_to, 1, 1)
        filters.addWidget(search_button, 1, 2)
        filters.addWidget(reset_button, 1, 3)

        tip = QLabel("仅展示已完成收款的订单，并列出该订单全部外发支出、总成本和盈亏。")
        tip.setStyleSheet("color: #66758a;")

        self.summary_label = QLabel("已收款订单：0 单，收款总额：0.00，外发总成本：0.00，总盈亏：0.00")
        self.summary_label.setStyleSheet("font-weight: 700; color: #213547;")

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            ["订单编号", "品名", "数量", "单价", "收款金额", "外发工艺", "加工厂", "外发数量", "外发金额", "外发日期", "总成本", "盈亏"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_detail)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_order_date_from.setDate(QDate(2000, 1, 1))
        self.search_order_date_to.setDate(QDate.currentDate())
        self.load_rows()

    def load_rows(self) -> None:
        rows = self.db.get_paid_order_profit_rows(
            order_no_keyword=self.search_order_no.text(),
            order_date_from=self.search_order_date_from.date().toString("yyyy-MM-dd"),
            order_date_to=self.search_order_date_to.date().toString("yyyy-MM-dd"),
        )

        display_rows: list[list[str]] = []
        row_spans: list[tuple[int, int]] = []
        total_receivable = 0.0
        total_cost = 0.0
        total_profit = 0.0

        for order in rows:
            quantity_text = ""
            if order.get("quantity") not in (None, ""):
                quantity_text = f"{order['quantity']}{order.get('quantity_unit') or '个'}"

            receivable_amount = safe_float(order.get("receivable_amount"))
            total_outsource_cost = safe_float(order.get("total_outsource_cost"))
            profit_amount = safe_float(order.get("profit_amount"))

            total_receivable += receivable_amount
            total_cost += total_outsource_cost
            total_profit += profit_amount

            outsource_records = order.get("outsource_records") or []
            span_start = len(display_rows)
            if not outsource_records:
                display_rows.append(
                    [
                        str(order.get("order_no") or ""),
                        str(order.get("product_name") or ""),
                        quantity_text,
                        f"{safe_float(order.get('unit_price')):.2f}",
                        f"{receivable_amount:.2f}",
                        "",
                        "",
                        "",
                        "0.00",
                        "",
                        f"{total_outsource_cost:.2f}",
                        f"{profit_amount:.2f}",
                    ]
                )
            else:
                for record in outsource_records:
                    outsource_amount = safe_float(record.get("amount"))
                    if record.get("amount") in (None, ""):
                        outsource_amount = safe_float(record.get("quantity")) * safe_float(record.get("unit_price"))
                    display_rows.append(
                        [
                            str(order.get("order_no") or ""),
                            str(order.get("product_name") or ""),
                            quantity_text,
                            f"{safe_float(order.get('unit_price')):.2f}",
                            f"{receivable_amount:.2f}",
                            str(record.get("process_name") or ""),
                            str(record.get("factory_name") or ""),
                            str(record.get("quantity") or ""),
                            f"{outsource_amount:.2f}",
                            str(record.get("outsource_date") or ""),
                            f"{total_outsource_cost:.2f}",
                            f"{profit_amount:.2f}",
                        ]
                    )
            row_spans.append((span_start, len(display_rows) - span_start))

        self.table.setRowCount(len(display_rows))
        for row_index, row_values in enumerate(display_rows):
            for column_index, value in enumerate(row_values):
                self.table.setItem(row_index, column_index, QTableWidgetItem(value))
        merge_columns = [0, 1, 2, 3, 4, 10, 11]
        for span_start, span_size in row_spans:
            if span_size <= 1:
                continue
            for column_index in merge_columns:
                self.table.setSpan(span_start, column_index, span_size, 1)
        self.table.resizeColumnsToContents()
        self.summary_label.setText(
            f"已收款订单：{len(rows)} 单，收款总额：{total_receivable:.2f}，外发总成本：{total_cost:.2f}，总盈亏：{total_profit:.2f}"
        )

    def show_detail(self, row: int, _column: int) -> None:
        order_no_item = self.table.item(row, 0)
        if not order_no_item:
            return
        record = self.db.get_order_by_order_no(order_no_item.text())
        if not record:
            return
        dialog = OrderPreviewDialog(record, self)
        dialog.exec()


class OutsourceFormTab(QWidget):
    def __init__(self, db: Database, refresh_callback) -> None:
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self.current_order: dict | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form_group = QGroupBox("外发登记")
        form = QFormLayout(form_group)

        order_lookup_row = QWidget()
        order_lookup_layout = QHBoxLayout(order_lookup_row)
        order_lookup_layout.setContentsMargins(0, 0, 0, 0)
        self.order_no_input = QLineEdit()
        self.order_no_input.setPlaceholderText("请输入订单编号")
        self.order_no_input.returnPressed.connect(self.load_order_by_order_no)
        lookup_button = QPushButton("读取订单")
        lookup_button.clicked.connect(self.load_order_by_order_no)
        order_lookup_layout.addWidget(self.order_no_input)
        order_lookup_layout.addWidget(lookup_button)

        self.order_summary = QLabel("请输入订单编号后读取订单信息。")
        self.order_summary.setWordWrap(True)
        self.order_summary.setStyleSheet("color: #5c6b7a;")

        self.process_combo = QComboBox()
        self.process_combo.setEditable(True)
        self.process_combo.setInsertPolicy(QComboBox.NoInsert)

        self.factory_name_input = QLineEdit()
        self.factory_name_input.setPlaceholderText("请输入加工厂名称")

        self.outsource_quantity_input = QLineEdit()
        self.outsource_quantity_input.setPlaceholderText("请输入发出数量")

        self.outsource_unit_price_input = QLineEdit()
        self.outsource_unit_price_input.setPlaceholderText("请输入加工单价")

        form.addRow("订单编号", order_lookup_row)
        form.addRow("订单信息", self.order_summary)
        form.addRow("工艺", self.process_combo)
        form.addRow("加工厂名称", self.factory_name_input)
        form.addRow("发出数量", self.outsource_quantity_input)
        form.addRow("加工单价", self.outsource_unit_price_input)

        button_row = QHBoxLayout()
        button_row.addStretch()
        reset_button = QPushButton("清空")
        reset_button.clicked.connect(self.reset_form)
        save_button = QPushButton("保存外发记录")
        save_button.clicked.connect(self.save_record)
        save_button.setStyleSheet(
            "QPushButton { background: #183153; color: white; padding: 8px 18px; border-radius: 8px; }"
        )
        button_row.addWidget(reset_button)
        button_row.addWidget(save_button)

        tip = QLabel("工艺下拉会优先读取该订单里已勾选或已填写的工艺内容，也支持直接手工补充。")
        tip.setStyleSheet("color: #66758a;")

        layout.addWidget(form_group)
        layout.addWidget(tip)
        layout.addLayout(button_row)
        layout.addStretch()
        self.reset_form()

    def reset_form(self) -> None:
        self.current_order = None
        self.order_no_input.clear()
        self.order_summary.setText("请输入订单编号后读取订单信息。")
        self.process_combo.clear()
        self.process_combo.addItem("")
        self.process_combo.setCurrentIndex(0)
        self.process_combo.setEditText("")
        self.factory_name_input.clear()
        self.outsource_quantity_input.clear()
        self.outsource_unit_price_input.clear()
        self.order_no_input.setFocus()

    def load_order_by_order_no(self) -> None:
        order_no = self.order_no_input.text().strip()
        if not order_no:
            QMessageBox.warning(self, "无法读取", "请先输入订单编号。")
            return

        record = self.db.get_order_by_order_no(order_no)
        if not record:
            self.current_order = None
            self.order_summary.setText("未找到对应订单，请确认订单编号。")
            self.process_combo.clear()
            self.process_combo.addItem("")
            self.process_combo.setEditText("")
            QMessageBox.warning(self, "未找到订单", f"系统中没有订单编号为 {order_no} 的订单。")
            return

        self.current_order = record
        summary_parts = [
            f"品名：{record.get('product_name') or '未填写'}",
            f"数量：{record.get('quantity') or ''}{record.get('quantity_unit') or ''}",
            f"交货日期：{record.get('delivery_date') or '未填写'}",
        ]
        self.order_summary.setText("  |  ".join(summary_parts))

        process_options = extract_order_process_options(record)
        self.process_combo.clear()
        self.process_combo.addItem("")
        for option in process_options:
            self.process_combo.addItem(option)
        if process_options:
            self.process_combo.setCurrentIndex(1)
        else:
            self.process_combo.setEditText("")

    def save_record(self) -> None:
        if not self.current_order:
            QMessageBox.warning(self, "无法保存", "请先输入订单编号并读取订单。")
            return

        process_name = self.process_combo.currentText().strip()
        factory_name = self.factory_name_input.text().strip()
        quantity_text = self.outsource_quantity_input.text().strip()
        unit_price_text = self.outsource_unit_price_input.text().strip()

        if not process_name:
            QMessageBox.warning(self, "无法保存", "请选择或输入工艺。")
            return
        if not factory_name:
            QMessageBox.warning(self, "无法保存", "请输入加工厂名称。")
            return
        try:
            quantity = float(quantity_text)
        except ValueError:
            QMessageBox.warning(self, "无法保存", "发出数量必须是数字。")
            return
        try:
            unit_price = float(unit_price_text)
        except ValueError:
            QMessageBox.warning(self, "无法保存", "加工单价必须是数字。")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "无法保存", "发出数量必须大于 0。")
            return
        if unit_price < 0:
            QMessageBox.warning(self, "无法保存", "加工单价不能小于 0。")
            return

        self.db.insert_outsource_record(
            {
                "order_id": self.current_order["id"],
                "order_no": self.current_order["order_no"],
                "process_name": process_name,
                "factory_name": factory_name,
                "quantity": quantity,
                "unit_price": unit_price,
            }
        )
        self.refresh_callback()
        QMessageBox.information(self, "保存成功", "外发记录已保存。")

        preserved_order_no = self.current_order["order_no"]
        self.reset_form()
        self.order_no_input.setText(preserved_order_no)
        self.load_order_by_order_no()


class OutsourceListTab(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号搜索")
        self.search_factory_name = QLineEdit()
        self.search_factory_name.setPlaceholderText("按加工厂搜索")
        self.search_process_name = QLineEdit()
        self.search_process_name.setPlaceholderText("按工艺搜索")

        search_button = QPushButton("搜索")
        search_button.clicked.connect(self.load_records)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        edit_button = QPushButton("修改选中记录")
        edit_button.clicked.connect(self.edit_selected_record)
        delete_button = QPushButton("删除选中记录")
        delete_button.clicked.connect(self.delete_selected_record)

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("加工厂"), 0, 2)
        filters.addWidget(self.search_factory_name, 0, 3)
        filters.addWidget(QLabel("工艺"), 1, 0)
        filters.addWidget(self.search_process_name, 1, 1)
        filters.addWidget(search_button, 1, 2)
        filters.addWidget(reset_button, 1, 3)
        filters.addWidget(edit_button, 2, 2)
        filters.addWidget(delete_button, 2, 3)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "订单编号", "品名", "工艺", "加工厂", "发出数量", "加工单价", "交货日期"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("这里会显示已经保存的外发记录，方便按订单、工艺和加工厂回查。")
        tip.setStyleSheet("color: #66758a;")

        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addWidget(self.table)

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_factory_name.clear()
        self.search_process_name.clear()
        self.load_records()

    def load_records(self) -> None:
        rows = self.db.search_outsource_records(
            order_no_keyword=self.search_order_no.text(),
            factory_keyword=self.search_factory_name.text(),
            process_keyword=self.search_process_name.text(),
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["order_no"] or "",
                row.get("product_name") or "",
                row["process_name"] or "",
                row["factory_name"] or "",
                row["quantity"],
                row["unit_price"],
                row.get("delivery_date") or "",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()


class OutsourceConfigTab(QWidget):
    def __init__(self, db: Database, form_tab: OutsourceFormTab) -> None:
        super().__init__()
        self.db = db
        self.form_tab = form_tab
        self._build_ui()
        self.load_processes()
        self.load_factories()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_process_tab(), "工艺管理")
        tabs.addTab(self._build_factory_tab(), "加工厂管理")
        layout.addWidget(tabs)

    def _build_process_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QGridLayout()
        self.process_name_input = QLineEdit()
        self.process_name_input.setPlaceholderText("输入工艺名称")
        add_button = QPushButton("新增工艺")
        add_button.clicked.connect(self.add_process)
        update_button = QPushButton("修改选中工艺")
        update_button.clicked.connect(self.update_process)
        delete_button = QPushButton("删除选中工艺")
        delete_button.clicked.connect(self.delete_process)

        form.addWidget(QLabel("工艺名称"), 0, 0)
        form.addWidget(self.process_name_input, 0, 1)
        form.addWidget(add_button, 0, 2)
        form.addWidget(update_button, 0, 3)
        form.addWidget(delete_button, 0, 4)

        self.process_table = QTableWidget(0, 2)
        self.process_table.setHorizontalHeaderLabels(["ID", "工艺名称"])
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.process_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.process_table.horizontalHeader().setStretchLastSection(True)
        self.process_table.itemSelectionChanged.connect(self._sync_selected_process)

        layout.addLayout(form)
        layout.addWidget(self.process_table)
        return widget

    def _build_factory_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QGridLayout()
        self.factory_process_combo = QComboBox()
        self.factory_name_manage_input = QLineEdit()
        self.factory_name_manage_input.setPlaceholderText("输入加工厂名称")
        add_button = QPushButton("新增加工厂")
        add_button.clicked.connect(self.add_factory)
        update_button = QPushButton("修改选中加工厂")
        update_button.clicked.connect(self.update_factory)
        delete_button = QPushButton("删除选中加工厂")
        delete_button.clicked.connect(self.delete_factory)

        form.addWidget(QLabel("所属工艺"), 0, 0)
        form.addWidget(self.factory_process_combo, 0, 1)
        form.addWidget(QLabel("加工厂名称"), 0, 2)
        form.addWidget(self.factory_name_manage_input, 0, 3)
        form.addWidget(add_button, 0, 4)
        form.addWidget(update_button, 0, 5)
        form.addWidget(delete_button, 0, 6)

        self.factory_table = QTableWidget(0, 3)
        self.factory_table.setHorizontalHeaderLabels(["ID", "所属工艺", "加工厂名称"])
        self.factory_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.factory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.factory_table.horizontalHeader().setStretchLastSection(True)
        self.factory_table.itemSelectionChanged.connect(self._sync_selected_factory)

        layout.addLayout(form)
        layout.addWidget(self.factory_table)
        return widget

    def load_processes(self) -> None:
        rows = self.db.list_outsource_processes()
        self.process_table.setRowCount(len(rows))
        self.factory_process_combo.clear()
        self.factory_process_combo.addItems([row["process_name"] for row in rows])
        for row_index, row in enumerate(rows):
            self.process_table.setItem(row_index, 0, QTableWidgetItem(str(row["id"])))
            self.process_table.setItem(row_index, 1, QTableWidgetItem(row["process_name"]))
        self.process_table.resizeColumnsToContents()

    def load_factories(self) -> None:
        rows = self.db.list_outsource_factories()
        self.factory_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.factory_table.setItem(row_index, 0, QTableWidgetItem(str(row["id"])))
            self.factory_table.setItem(row_index, 1, QTableWidgetItem(row["process_name"]))
            self.factory_table.setItem(row_index, 2, QTableWidgetItem(row["factory_name"]))
        self.factory_table.resizeColumnsToContents()

    def _sync_selected_process(self) -> None:
        selected_rows = self.process_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        name_item = self.process_table.item(row, 1)
        if name_item:
            self.process_name_input.setText(name_item.text())

    def _sync_selected_factory(self) -> None:
        selected_rows = self.factory_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        process_item = self.factory_table.item(row, 1)
        factory_item = self.factory_table.item(row, 2)
        if process_item:
            self.factory_process_combo.setCurrentText(process_item.text())
        if factory_item:
            self.factory_name_manage_input.setText(factory_item.text())

    def add_process(self) -> None:
        process_name = self.process_name_input.text().strip()
        if not process_name:
            QMessageBox.warning(self, "无法新增", "请输入工艺名称。")
            return
        try:
            self.db.add_outsource_process(process_name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "无法新增", "该工艺已存在。")
            return
        self._refresh_all_config_views()

    def update_process(self) -> None:
        selected_rows = self.process_table.selectionModel().selectedRows()
        process_name = self.process_name_input.text().strip()
        if not selected_rows:
            QMessageBox.warning(self, "无法修改", "请先选中工艺。")
            return
        if not process_name:
            QMessageBox.warning(self, "无法修改", "请输入工艺名称。")
            return
        process_id = int(self.process_table.item(selected_rows[0].row(), 0).text())
        try:
            self.db.update_outsource_process(process_id, process_name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "无法修改", "该工艺名称已存在。")
            return
        self._refresh_all_config_views()

    def delete_process(self) -> None:
        selected_rows = self.process_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "无法删除", "请先选中工艺。")
            return
        process_id = int(self.process_table.item(selected_rows[0].row(), 0).text())
        self.db.delete_outsource_process(process_id)
        self._refresh_all_config_views()

    def add_factory(self) -> None:
        process_name = self.factory_process_combo.currentText().strip()
        factory_name = self.factory_name_manage_input.text().strip()
        if not process_name or not factory_name:
            QMessageBox.warning(self, "无法新增", "请选择工艺并输入加工厂名称。")
            return
        self.db.add_outsource_factory(process_name, factory_name)
        self._refresh_all_config_views()

    def update_factory(self) -> None:
        selected_rows = self.factory_table.selectionModel().selectedRows()
        process_name = self.factory_process_combo.currentText().strip()
        factory_name = self.factory_name_manage_input.text().strip()
        if not selected_rows:
            QMessageBox.warning(self, "无法修改", "请先选中加工厂。")
            return
        if not process_name or not factory_name:
            QMessageBox.warning(self, "无法修改", "请选择工艺并输入加工厂名称。")
            return
        factory_id = int(self.factory_table.item(selected_rows[0].row(), 0).text())
        self.db.update_outsource_factory(factory_id, process_name, factory_name)
        self._refresh_all_config_views()

    def delete_factory(self) -> None:
        selected_rows = self.factory_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "无法删除", "请先选中加工厂。")
            return
        factory_id = int(self.factory_table.item(selected_rows[0].row(), 0).text())
        self.db.delete_outsource_factory(factory_id)
        self._refresh_all_config_views()

    def _refresh_all_config_views(self) -> None:
        self.load_processes()
        self.load_factories()
        self.form_tab.refresh_process_options()
        self.form_tab.refresh_factory_options()


class OutsourceMainWindow(QMainWindow):
    def __init__(self, db: Database, logout_callback=None) -> None:
        super().__init__()
        self.db = db
        self.logout_callback = logout_callback
        self.setWindowTitle("外发登记系统")
        self.resize(1180, 780)

        container = QWidget()
        layout = QVBoxLayout(container)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        logout_button = QPushButton("退出登录")
        logout_button.clicked.connect(self.logout)
        top_bar.addWidget(logout_button)
        layout.addLayout(top_bar)

        tabs = QTabWidget()
        self.outsource_list_tab = OutsourceListTab(self.db)
        self.outsource_form_tab = OutsourceFormTab(self.db, self.outsource_list_tab.load_records)
        tabs.addTab(self.outsource_form_tab, "新建外发")
        tabs.addTab(self.outsource_list_tab, "外发记录")
        layout.addWidget(tabs)
        self.setCentralWidget(container)

    def logout(self) -> None:
        if self.logout_callback:
            self.logout_callback(self)
            return
        self.close()


class OutsourcePaymentTab(QWidget):
    EXPORT_HEADERS = [
        "支付状态",
        "订单编号",
        "品名",
        "工艺",
        "加工厂",
        "产品数量",
        "备品数量",
        "合计数量",
        "加工单价",
        "重做单",
        "补数单",
        "金额",
        "日期",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()
        self.refresh_filter_options()
        self.load_records()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号检索")
        self.search_process_name = QComboBox()
        self.search_process_name.currentIndexChanged.connect(self.refresh_factory_options)
        self.search_factory_name = QComboBox()
        self.unpaid_only_checkbox = QCheckBox("仅显示未支付项")
        self.unpaid_only_checkbox.toggled.connect(self.load_records)

        search_button = QPushButton("检索")
        search_button.clicked.connect(self.load_records)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        select_all_button = QPushButton("全选")
        select_all_button.clicked.connect(self.select_all_rows)
        clear_selection_button = QPushButton("取消全选")
        clear_selection_button.clicked.connect(self.clear_all_rows)
        mark_paid_button = QPushButton("批量设为已支付")
        mark_paid_button.clicked.connect(lambda: self.update_selected_paid_status(1))
        mark_unpaid_button = QPushButton("批量设为未支付")
        mark_unpaid_button.clicked.connect(lambda: self.update_selected_paid_status(0))
        export_button = QPushButton("导出 Excel")
        export_button.clicked.connect(self.export_excel)

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("加工厂"), 0, 2)
        filters.addWidget(self.search_factory_name, 0, 3)
        filters.addWidget(QLabel("工艺"), 1, 0)
        filters.addWidget(self.search_process_name, 1, 1)
        filters.addWidget(self.unpaid_only_checkbox, 1, 2)
        filters.addWidget(search_button, 2, 2)
        filters.addWidget(reset_button, 2, 3)

        actions = QHBoxLayout()
        actions.addWidget(select_all_button)
        actions.addWidget(clear_selection_button)
        actions.addWidget(mark_paid_button)
        actions.addWidget(mark_unpaid_button)
        actions.addStretch()
        self.total_amount_label = QLabel("选中待付款总金额：0.00")
        self.total_amount_label.setStyleSheet("font-weight: 700; color: #213547;")
        actions.addWidget(self.total_amount_label)
        actions.addWidget(export_button)

        self.table = QTableWidget(0, 15)
        self.table.setHorizontalHeaderLabels(
            ["选择", "ID", "支付状态", "订单编号", "品名", "工艺", "加工厂", "产品数量", "备品数量", "合计数量", "加工单价", "重做单", "补数单", "金额", "日期"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.show_detail)
        self.table.itemChanged.connect(self._handle_item_changed)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("该页与外发登记系统共享外发记录，可按加工厂名称检索，并批量维护对外支付状态。")
        tip.setStyleSheet("color: #66758a;")
        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addLayout(actions)
        layout.addWidget(self.table)

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.unpaid_only_checkbox.setChecked(False)
        if self.search_process_name.count() > 0:
            self.search_process_name.setCurrentIndex(0)
        self.refresh_factory_options()
        if self.search_factory_name.count() > 0:
            self.search_factory_name.setCurrentIndex(0)
        self.load_records()

    def load_records(self) -> None:
        rows = self.db.search_outsource_records(
            order_no_keyword=self.search_order_no.text(),
            factory_keyword=self._selected_filter_value(self.search_factory_name),
            process_keyword=self._selected_filter_value(self.search_process_name),
        )
        if self.unpaid_only_checkbox.isChecked():
            rows = [row for row in rows if not row.get("paid_status")]

        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            checkbox_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row_index, 0, checkbox_item)
            amount_value = "" if row.get("amount") in (None, "") else f"{float(row['amount']):.2f}"

            values = [
                row["id"],
                "已支付" if row.get("paid_status") else "未支付",
                row["order_no"] or "",
                row.get("product_name") or "",
                row["process_name"] or "",
                row["factory_name"] or "",
                row.get("product_quantity", 0),
                row.get("spare_quantity", 0),
                row["quantity"],
                row["unit_price"],
                "是" if row.get("remake_flag") else "",
                "是" if row.get("replenishment_flag") else "",
                amount_value,
                row.get("outsource_date") or "",
            ]
            row_items: list[QTableWidgetItem | None] = [checkbox_item]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row_index, column_index + 1, item)
                row_items.append(item)
            apply_outsource_row_style(row_items, row)
        self.table.blockSignals(False)
        self._update_total_amount()
        self.table.resizeColumnsToContents()

    def show_detail(self, row: int, _column: int) -> None:
        order_no_item = self.table.item(row, 3)
        if not order_no_item:
            return
        record = self.db.get_order_by_order_no(order_no_item.text())
        if not record:
            return
        dialog = OrderPreviewDialog(record, self)
        dialog.exec()

    def _selected_record_ids(self) -> list[int]:
        record_ids: list[int] = []
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            record_id_item = self.table.item(row_index, 1)
            if check_item and record_id_item and check_item.checkState() == Qt.Checked:
                record_ids.append(int(record_id_item.text()))
        return record_ids

    def select_all_rows(self) -> None:
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Checked)
        self.table.blockSignals(False)
        self._update_total_amount()

    def clear_all_rows(self) -> None:
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            if check_item:
                check_item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_total_amount()

    def update_selected_paid_status(self, paid_status: int) -> None:
        record_ids = self._selected_record_ids()
        if not record_ids:
            QMessageBox.warning(self, "无法修改", "请先勾选至少一条外发记录。")
            return
        self.db.update_outsource_paid_status(record_ids, paid_status)
        self.load_records()
        status_text = "已支付" if paid_status else "未支付"
        QMessageBox.information(self, "修改成功", f"已将 {len(record_ids)} 条外发记录更新为“{status_text}”。")

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_total_amount()

    def _update_total_amount(self) -> None:
        total_amount = 0.0
        selected_count = 0
        for row_index in range(self.table.rowCount()):
            check_item = self.table.item(row_index, 0)
            status_item = self.table.item(row_index, 2)
            amount_item = self.table.item(row_index, 13)
            if not check_item or not status_item or not amount_item:
                continue
            if check_item.checkState() != Qt.Checked:
                continue
            if status_item.text() != "未支付":
                continue
            selected_count += 1
            if amount_item.text():
                try:
                    total_amount += float(amount_item.text())
                except ValueError:
                    continue
        self.total_amount_label.setText(f"选中待付款总金额：{total_amount:.2f}（{selected_count}条）")

    def refresh_filter_options(self) -> None:
        current_process = self._selected_filter_value(self.search_process_name)
        process_values = ["全部"] + [row["process_name"] for row in self.db.list_outsource_processes()]
        deduped_processes: list[str] = []
        for value in process_values:
            if value not in deduped_processes:
                deduped_processes.append(value)
        self.search_process_name.blockSignals(True)
        self.search_process_name.clear()
        self.search_process_name.addItems(deduped_processes)
        if current_process and current_process in deduped_processes:
            self.search_process_name.setCurrentText(current_process)
        else:
            self.search_process_name.setCurrentIndex(0)
        self.search_process_name.blockSignals(False)
        self.refresh_factory_options()

    def refresh_factory_options(self) -> None:
        current_factory = self._selected_filter_value(self.search_factory_name)
        process_name = self._selected_filter_value(self.search_process_name)
        factory_rows = self.db.list_outsource_factories(process_name)
        factory_values = ["全部"] + [row["factory_name"] for row in factory_rows]
        deduped_factories: list[str] = []
        for value in factory_values:
            if value not in deduped_factories:
                deduped_factories.append(value)
        self.search_factory_name.blockSignals(True)
        self.search_factory_name.clear()
        self.search_factory_name.addItems(deduped_factories)
        if current_factory and current_factory in deduped_factories:
            self.search_factory_name.setCurrentText(current_factory)
        else:
            self.search_factory_name.setCurrentIndex(0)
        self.search_factory_name.blockSignals(False)

    def _selected_filter_value(self, combo_box: QComboBox) -> str:
        value = combo_box.currentText().strip()
        return "" if value in ("", "全部") else value

    def export_excel(self) -> None:
        rows = self._current_export_rows()
        if not rows:
            QMessageBox.information(self, "没有数据", "当前筛选结果中没有可导出的对外付款记录。")
            return
        default_name = f"对外付款-{QDate.currentDate().toString('yyMMdd')}-{datetime.now().strftime('%H%M')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出对外付款 Excel",
            str(Path.cwd() / default_name),
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        export_rows_to_excel(file_path, "对外支付对账", self.EXPORT_HEADERS, rows)
        QMessageBox.information(self, "导出成功", f"Excel 已导出到：\n{file_path}")

    def _current_export_rows(self) -> list[list]:
        rows: list[list] = []
        for row_index in range(self.table.rowCount()):
            values = []
            for column_index in range(2, 2 + len(self.EXPORT_HEADERS)):
                item = self.table.item(row_index, column_index)
                values.append("" if item is None else item.text())
            rows.append(values)
        return rows


class OutsourceFormTab(QWidget):
    def __init__(self, db: Database, refresh_callback) -> None:
        super().__init__()
        self.db = db
        self.refresh_callback = refresh_callback
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form_group = QGroupBox("批量外发登记")
        form = QFormLayout(form_group)

        self.process_combo = QComboBox()
        self.process_combo.setEditable(False)
        self.process_combo.currentTextChanged.connect(self._handle_process_changed)

        self.factory_name_input = QComboBox()
        self.factory_name_input.setEditable(True)
        self.factory_name_input.setInsertPolicy(QComboBox.NoInsert)

        self.order_no_input = QLineEdit()
        self.order_no_input.setPlaceholderText("请输入订单编号")
        self.order_no_input.returnPressed.connect(self.add_single_order_to_staging)

        import_button = QPushButton("加入暂存列表")
        import_button.clicked.connect(self.add_single_order_to_staging)

        batch_row = QWidget()
        batch_layout = QHBoxLayout(batch_row)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.addWidget(self.order_no_input)
        batch_layout.addWidget(import_button)

        form.addRow("工艺", self.process_combo)
        form.addRow("加工厂名称", self.factory_name_input)
        form.addRow("订单编号", batch_row)

        self.table = QTableWidget(0, 20)
        self.table.setHorizontalHeaderLabels(
            [
                "订单编号",
                "品名",
                "订单数量",
                "产品数量",
                "备品数量",
                "加工单价",
                "加工费",
                "长(mm)",
                "宽(mm)",
                "厚(mm)",
                "密度",
                "重量",
                "材料单价",
                "颜色数量",
                "版费",
                "日期",
                "备注",
                "重做单",
                "补数单",
                "金额",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._handle_table_item_changed)
        self.table.horizontalHeader().setStretchLastSection(True)

        table_actions = QHBoxLayout()
        add_row_button = QPushButton("新增一行")
        add_row_button.clicked.connect(lambda: self._append_empty_row())
        remove_row_button = QPushButton("删除选中行")
        remove_row_button.clicked.connect(self.remove_selected_rows)
        table_actions.addWidget(add_row_button)
        table_actions.addWidget(remove_row_button)
        table_actions.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()
        reset_button = QPushButton("清空")
        reset_button.clicked.connect(self.reset_form)
        save_button = QPushButton("保存批量外发")
        save_button.clicked.connect(self.save_records)
        save_button.setStyleSheet(
            "QPushButton { background: #183153; color: white; padding: 8px 18px; border-radius: 8px; }"
        )
        button_row.addWidget(reset_button)
        button_row.addWidget(save_button)

        tip = QLabel("先录入单个订单并加入暂存列表，确认下方明细后再点击批量保存入库。")
        tip.setStyleSheet("color: #66758a;")

        layout.addWidget(form_group)
        layout.addWidget(tip)
        layout.addLayout(table_actions)
        layout.addWidget(self.table)
        layout.addLayout(button_row)
        self.refresh_process_options()
        self.reset_form()

    def reset_form(self) -> None:
        self.order_no_input.clear()
        if self.process_combo.count() > 0:
            self.process_combo.setCurrentIndex(0)
        self.refresh_factory_options()
        self.factory_name_input.setCurrentIndex(-1)
        self.factory_name_input.setEditText("")
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self._update_table_for_process()
        self.order_no_input.setFocus()

    def refresh_process_options(self) -> None:
        current_text = self.process_combo.currentText().strip()
        processes = [row["process_name"] for row in self.db.list_outsource_processes()]
        if not processes:
            processes = OUTSOURCE_PROCESS_OPTIONS[:]
        self.process_combo.blockSignals(True)
        self.process_combo.clear()
        self.process_combo.addItems(processes)
        if current_text and current_text in processes:
            self.process_combo.setCurrentText(current_text)
        self.process_combo.blockSignals(False)
        self.refresh_factory_options()

    def refresh_factory_options(self) -> None:
        current_text = self.factory_name_input.currentText().strip()
        process_name = self.process_combo.currentText().strip()
        factories = [
            row["factory_name"] for row in self.db.list_outsource_factories(process_name)
        ]
        self.factory_name_input.blockSignals(True)
        self.factory_name_input.clear()
        self.factory_name_input.addItems(factories)
        self.factory_name_input.setCurrentIndex(-1)
        self.factory_name_input.setEditText(current_text)
        self.factory_name_input.blockSignals(False)

    def _append_empty_row(self, order_no: str = "") -> None:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)

        order_item = QTableWidgetItem(order_no)
        product_item = QTableWidgetItem("")
        order_quantity_item = QTableWidgetItem("")
        product_item.setFlags(product_item.flags() & ~Qt.ItemIsEditable)
        order_quantity_item.setFlags(order_quantity_item.flags() & ~Qt.ItemIsEditable)

        self.table.setItem(row_index, 0, order_item)
        self.table.setItem(row_index, 1, product_item)
        self.table.setItem(row_index, 2, order_quantity_item)
        self.table.setItem(row_index, 3, QTableWidgetItem(""))
        self.table.setItem(row_index, 4, QTableWidgetItem("0"))
        self.table.setItem(row_index, 5, QTableWidgetItem(""))
        self.table.setItem(row_index, 6, QTableWidgetItem("0"))
        self.table.setItem(row_index, 7, QTableWidgetItem(""))
        self.table.setItem(row_index, 8, QTableWidgetItem(""))
        self.table.setItem(row_index, 9, QTableWidgetItem(""))
        self.table.setItem(row_index, 10, QTableWidgetItem("0.00785"))
        self.table.setItem(row_index, 11, QTableWidgetItem("0.0055"))
        material_price_item = QTableWidgetItem("0")
        material_price_item.setFlags(material_price_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row_index, 12, material_price_item)
        self.table.setItem(row_index, 13, QTableWidgetItem(""))
        self.table.setItem(row_index, 14, QTableWidgetItem("0"))
        self.table.setItem(row_index, 15, QTableWidgetItem(QDate.currentDate().toString("yyyy-MM-dd")))
        self.table.setItem(row_index, 16, QTableWidgetItem(""))
        remake_item = QTableWidgetItem()
        remake_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
        remake_item.setCheckState(Qt.Unchecked)
        self.table.setItem(row_index, 17, remake_item)
        replenishment_item = QTableWidgetItem()
        replenishment_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
        replenishment_item.setCheckState(Qt.Unchecked)
        self.table.setItem(row_index, 18, replenishment_item)
        amount_item = QTableWidgetItem("")
        amount_item.setFlags(amount_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row_index, 19, amount_item)

        if order_no:
            self._load_order_into_row(row_index, order_no, show_warning=False)
        self._recalculate_row(row_index)

    def import_order_numbers(self) -> None:
        self.add_single_order_to_staging()

    def add_single_order_to_staging(self) -> None:
        order_no = self.order_no_input.text().strip()
        if not order_no:
            QMessageBox.warning(self, "无法加入", "请先输入订单编号。")
            return

        record = self.db.get_order_by_order_no(order_no)
        if not record:
            QMessageBox.warning(self, "未找到订单", f"系统中没有订单编号为 {order_no} 的订单。")
            return

        normalized_order_no = record["order_no"]
        for row_index in range(self.table.rowCount()):
            order_item = self.table.item(row_index, 0)
            if order_item and order_item.text().strip() == normalized_order_no:
                QMessageBox.warning(self, "无法加入", f"{normalized_order_no} 已在暂存列表中。")
                return

        self._show_existing_outsource_warning(normalized_order_no)
        self._append_empty_row(normalized_order_no)
        self.order_no_input.clear()
        self.order_no_input.setFocus()
        self.table.resizeColumnsToContents()

    def _show_existing_outsource_warning(self, order_no: str) -> None:
        process_name = self.process_combo.currentText().strip()
        existing = self.db.get_latest_outsource_record_for_order_process(order_no, process_name)
        if not existing:
            return

        date_text = existing.get("outsource_date") or existing.get("created_at") or ""
        qdate = QDate.fromString(str(date_text)[:10], "yyyy-MM-dd")
        if qdate.isValid():
            date_text = qdate.toString("yyyy年MM月dd日")
        factory_name = existing.get("factory_name") or ""
        quantity = existing.get("quantity") or 0
        QMessageBox.information(
            self,
            "已有相同工艺外发记录",
            f"{order_no}订单于{date_text}向{factory_name}发送了{quantity:g}个。",
        )

    def remove_selected_rows(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        if not selected_rows:
            QMessageBox.warning(self, "无法删除", "请先选中要删除的行。")
            return
        for row_index in selected_rows:
            self.table.removeRow(row_index)
        self.refresh_process_options()

    def _handle_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._load_order_into_row(item.row(), item.text().strip())
            return
        self._recalculate_row(item.row())

    def _handle_process_changed(self) -> None:
        self.refresh_factory_options()
        self._update_table_for_process()
        for row_index in range(self.table.rowCount()):
            self._recalculate_row(row_index)

    def _update_table_for_process(self) -> None:
        process_name = self.process_combo.currentText().strip()
        visible_columns = {
            OUTSOURCE_TABLE_COLUMNS["order_no"],
            OUTSOURCE_TABLE_COLUMNS["product_name"],
            OUTSOURCE_TABLE_COLUMNS["order_quantity"],
            OUTSOURCE_TABLE_COLUMNS["product_quantity"],
            OUTSOURCE_TABLE_COLUMNS["spare_quantity"],
            OUTSOURCE_TABLE_COLUMNS["unit_price"],
            OUTSOURCE_TABLE_COLUMNS["outsource_date"],
            OUTSOURCE_TABLE_COLUMNS["remark"],
            OUTSOURCE_TABLE_COLUMNS["remake_flag"],
            OUTSOURCE_TABLE_COLUMNS["replenishment_flag"],
            OUTSOURCE_TABLE_COLUMNS["amount"],
        }

        if process_name == "冲压":
            visible_columns.update(
                {
                    OUTSOURCE_TABLE_COLUMNS["processing_fee"],
                    OUTSOURCE_TABLE_COLUMNS["length_mm"],
                    OUTSOURCE_TABLE_COLUMNS["width_mm"],
                    OUTSOURCE_TABLE_COLUMNS["thickness_mm"],
                    OUTSOURCE_TABLE_COLUMNS["density"],
                    OUTSOURCE_TABLE_COLUMNS["weight"],
                    OUTSOURCE_TABLE_COLUMNS["material_unit_price"],
                }
            )
        elif process_name == "上色":
            visible_columns.add(OUTSOURCE_TABLE_COLUMNS["color_count"])
        elif process_name == "印刷/UV":
            visible_columns.add(OUTSOURCE_TABLE_COLUMNS["plate_fee"])

        for column_index in range(self.table.columnCount()):
            self.table.setColumnHidden(column_index, column_index not in visible_columns)
        self.table.resizeColumnsToContents()

    def _load_order_into_row(self, row_index: int, order_no: str, show_warning: bool = True) -> None:
        order_item = self.table.item(row_index, 0)
        product_item = self.table.item(row_index, 1)
        order_quantity_item = self.table.item(row_index, 2)
        if not order_item or not product_item or not order_quantity_item:
            return

        self.table.blockSignals(True)
        if not order_no:
            order_item.setData(Qt.UserRole, None)
            product_item.setText("")
            order_quantity_item.setText("")
            self.table.blockSignals(False)
            self.refresh_process_options()
            return

        record = self.db.get_order_by_order_no(order_no)
        if not record:
            order_item.setData(Qt.UserRole, None)
            product_item.setText("未找到订单")
            order_quantity_item.setText("")
            self.table.blockSignals(False)
            self.refresh_process_options()
            if show_warning:
                QMessageBox.warning(self, "未找到订单", f"系统中没有订单编号为 {order_no} 的订单。")
            return

        order_item.setText(record["order_no"])
        order_item.setData(Qt.UserRole, record)
        product_item.setText(record.get("product_name") or "")
        order_quantity_item.setText(f"{record.get('quantity') or ''}{record.get('quantity_unit') or ''}")
        business_quantity = safe_float(record.get("quantity")) + safe_float(record.get("spare_quantity"))
        product_quantity_item = self.table.item(row_index, OUTSOURCE_TABLE_COLUMNS["product_quantity"])
        outsource_spare_item = self.table.item(row_index, OUTSOURCE_TABLE_COLUMNS["spare_quantity"])
        length_item = self.table.item(row_index, OUTSOURCE_TABLE_COLUMNS["length_mm"])
        width_item = self.table.item(row_index, OUTSOURCE_TABLE_COLUMNS["width_mm"])
        thickness_item = self.table.item(row_index, OUTSOURCE_TABLE_COLUMNS["thickness_mm"])
        if product_quantity_item:
            product_quantity_item.setText(f"{business_quantity:g}")
        if outsource_spare_item and not outsource_spare_item.text().strip():
            outsource_spare_item.setText("0")
        if length_item and record.get("width_mm") not in (None, ""):
            length_item.setText(f"{safe_float(record.get('width_mm')):g}")
        if width_item and record.get("height_mm") not in (None, ""):
            width_item.setText(f"{safe_float(record.get('height_mm')):g}")
        if thickness_item and record.get("thickness_mm") not in (None, ""):
            thickness_item.setText(f"{safe_float(record.get('thickness_mm')):g}")
        self.table.blockSignals(False)
        self._recalculate_row(row_index)

    def _recalculate_row(self, row_index: int) -> None:
        process_name = self.process_combo.currentText().strip()
        product_quantity_item = self.table.item(row_index, 3)
        spare_quantity_item = self.table.item(row_index, 4)
        unit_price_item = self.table.item(row_index, 5)
        processing_fee_item = self.table.item(row_index, 6)
        length_item = self.table.item(row_index, 7)
        width_item = self.table.item(row_index, 8)
        thickness_item = self.table.item(row_index, 9)
        density_item = self.table.item(row_index, 10)
        weight_item = self.table.item(row_index, 11)
        material_unit_price_item = self.table.item(row_index, 12)
        color_count_item = self.table.item(row_index, 13)
        plate_fee_item = self.table.item(row_index, 14)
        amount_item = self.table.item(row_index, 19)
        if not all(
            [
                product_quantity_item,
                spare_quantity_item,
                unit_price_item,
                processing_fee_item,
                length_item,
                width_item,
                thickness_item,
                density_item,
                weight_item,
                material_unit_price_item,
                color_count_item,
                plate_fee_item,
                amount_item,
            ]
        ):
            return

        total_quantity = safe_float(product_quantity_item.text()) + safe_float(spare_quantity_item.text())
        unit_price = safe_float(unit_price_item.text())
        processing_fee = safe_float(processing_fee_item.text())
        length_mm = safe_float(length_item.text())
        width_mm = safe_float(width_item.text())
        thickness_mm = safe_float(thickness_item.text())
        density = safe_float(density_item.text(), 0.00785)
        weight = safe_float(weight_item.text(), 0.0055)
        material_unit_price = (length_mm + 3) * (width_mm + 3) * thickness_mm * density * weight
        color_count = safe_float(color_count_item.text())
        plate_fee = safe_float(plate_fee_item.text())

        self.table.blockSignals(True)
        material_unit_price_item.setText(f"{material_unit_price:.6f}".rstrip("0").rstrip(".") or "0")

        if total_quantity <= 0 and unit_price == 0 and processing_fee == 0 and plate_fee == 0:
            amount_item.setText("")
        elif process_name == "冲压":
            amount = total_quantity * ((unit_price if unit_price != 0 else 0) + material_unit_price) + processing_fee
            amount_item.setText(f"{amount:.2f}")
        elif process_name == "上色":
            amount = total_quantity * unit_price * color_count
            amount_item.setText(f"{amount:.2f}")
        elif process_name == "印刷/UV":
            amount = total_quantity * unit_price + plate_fee
            amount_item.setText(f"{amount:.2f}")
        else:
            amount = total_quantity * unit_price
            amount_item.setText(f"{amount:.2f}")
        self.table.blockSignals(False)

    def save_records(self) -> None:
        process_name = self.process_combo.currentText().strip()
        factory_name = self.factory_name_input.currentText().strip()
        if not process_name:
            QMessageBox.warning(self, "无法保存", "请选择或输入工艺。")
            return
        if not factory_name:
            QMessageBox.warning(self, "无法保存", "请输入加工厂名称。")
            return

        payloads: list[dict] = []
        for row_index in range(self.table.rowCount()):
            order_item = self.table.item(row_index, 0)
            product_quantity_item = self.table.item(row_index, 3)
            spare_quantity_item = self.table.item(row_index, 4)
            unit_price_item = self.table.item(row_index, 5)
            processing_fee_item = self.table.item(row_index, 6)
            length_item = self.table.item(row_index, 7)
            width_item = self.table.item(row_index, 8)
            thickness_item = self.table.item(row_index, 9)
            density_item = self.table.item(row_index, 10)
            weight_item = self.table.item(row_index, 11)
            material_unit_price_item = self.table.item(row_index, 12)
            color_count_item = self.table.item(row_index, 13)
            plate_fee_item = self.table.item(row_index, 14)
            outsource_date_item = self.table.item(row_index, 15)
            remark_item = self.table.item(row_index, 16)
            remake_flag_item = self.table.item(row_index, 17)
            replenishment_flag_item = self.table.item(row_index, 18)
            amount_item = self.table.item(row_index, 19)

            order_no = order_item.text().strip() if order_item else ""
            if not order_no:
                continue

            record = order_item.data(Qt.UserRole) if order_item else None
            if not record:
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行订单编号无效，请先改正。")
                return

            try:
                product_quantity = float((product_quantity_item.text() if product_quantity_item else "").strip() or "0")
                spare_quantity = float((spare_quantity_item.text() if spare_quantity_item else "").strip() or "0")
                unit_price = float((unit_price_item.text() if unit_price_item else "").strip())
                processing_fee = float((processing_fee_item.text() if processing_fee_item else "").strip() or "0")
                length_mm = float((length_item.text() if length_item else "").strip() or "0")
                width_mm = float((width_item.text() if width_item else "").strip() or "0")
                thickness_mm = float((thickness_item.text() if thickness_item else "").strip() or "0")
                density = float((density_item.text() if density_item else "").strip() or "0.00785")
                weight = float((weight_item.text() if weight_item else "").strip() or "0.0055")
                material_unit_price = float((material_unit_price_item.text() if material_unit_price_item else "").strip() or "0")
                plate_fee = float((plate_fee_item.text() if plate_fee_item else "").strip() or "0")
            except ValueError:
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行的数量或单价格式不正确。")
                return

            if min(product_quantity, spare_quantity, unit_price, processing_fee, length_mm, width_mm, thickness_mm, density, weight, plate_fee) < 0:
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行的数量不能小于 0。")
                return
            total_quantity = product_quantity + spare_quantity
            if total_quantity <= 0:
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行的产品数量和备品数量不能同时为 0。")
                return
            if process_name == "冲压" and (length_mm <= 0 or width_mm <= 0 or thickness_mm <= 0):
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行冲压工艺必须填写大于 0 的长、宽、厚。")
                return

            outsource_date = (outsource_date_item.text() if outsource_date_item else "").strip()
            if not QDate.fromString(outsource_date, "yyyy-MM-dd").isValid():
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行日期必须是 yyyy-MM-dd。")
                return

            color_count_text = (color_count_item.text() if color_count_item else "").strip()
            color_count = None
            if process_name == "上色":
                if not color_count_text:
                    QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行必须填写颜色数量。")
                    return
                try:
                    color_count = int(color_count_text)
                except ValueError:
                    QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行颜色数量必须是整数。")
                    return
                if color_count < 0:
                    QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行颜色数量不能小于 0。")
                    return

            if process_name == "印刷/UV" and plate_fee < 0:
                QMessageBox.warning(self, "无法保存", f"第 {row_index + 1} 行版费不能小于 0。")
                return

            amount_text = (amount_item.text() if amount_item else "").strip()
            amount = float(amount_text) if amount_text else None
            remake_flag = 1 if remake_flag_item and remake_flag_item.checkState() == Qt.Checked else 0
            replenishment_flag = (
                1 if replenishment_flag_item and replenishment_flag_item.checkState() == Qt.Checked else 0
            )

            if process_name != "冲压":
                processing_fee = 0
                length_mm = 0
                width_mm = 0
                thickness_mm = 0
                density = 0.00785
                weight = 0.0055
                material_unit_price = 0
            if process_name != "上色":
                color_count = None
            if process_name != "印刷/UV":
                plate_fee = 0

            payloads.append(
                {
                    "order_id": record["id"],
                    "order_no": record["order_no"],
                    "process_name": process_name,
                    "factory_name": factory_name,
                    "quantity": total_quantity,
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
                    "outsource_date": outsource_date,
                    "remark": (remark_item.text() if remark_item else "").strip(),
                    "remake_flag": remake_flag,
                    "replenishment_flag": replenishment_flag,
                    "amount": amount,
                }
            )

        if not payloads:
            QMessageBox.warning(self, "无法保存", "请至少填写一条有效的外发明细。")
            return

        for payload in payloads:
            self.db.insert_outsource_record(payload)
        self.refresh_callback()
        QMessageBox.information(self, "保存成功", f"已保存 {len(payloads)} 条外发记录。")
        self.reset_form()


class OutsourceListTab(QWidget):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filters = QGridLayout()
        self.search_order_no = QLineEdit()
        self.search_order_no.setPlaceholderText("按订单编号搜索")
        self.search_factory_name = QLineEdit()
        self.search_factory_name.setPlaceholderText("按加工厂搜索")
        self.search_process_name = QLineEdit()
        self.search_process_name.setPlaceholderText("按工艺搜索")
        self.search_outsource_date_from = QLineEdit()
        self.search_outsource_date_from.setPlaceholderText("yyyy-MM-dd")
        self.search_outsource_date_to = QLineEdit()
        self.search_outsource_date_to.setPlaceholderText("yyyy-MM-dd")

        search_button = QPushButton("搜索")
        search_button.clicked.connect(self.load_records)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self.reset_filters)
        edit_button = QPushButton("修改选中记录")
        edit_button.clicked.connect(self.edit_selected_record)
        delete_button = QPushButton("删除选中记录")
        delete_button.clicked.connect(self.delete_selected_record)

        filters.addWidget(QLabel("订单编号"), 0, 0)
        filters.addWidget(self.search_order_no, 0, 1)
        filters.addWidget(QLabel("加工厂"), 0, 2)
        filters.addWidget(self.search_factory_name, 0, 3)
        filters.addWidget(QLabel("工艺"), 1, 0)
        filters.addWidget(self.search_process_name, 1, 1)
        filters.addWidget(QLabel("外发日期从"), 1, 2)
        filters.addWidget(self.search_outsource_date_from, 1, 3)
        filters.addWidget(QLabel("外发日期到"), 2, 0)
        filters.addWidget(self.search_outsource_date_to, 2, 1)
        filters.addWidget(search_button, 2, 2)
        filters.addWidget(reset_button, 2, 3)
        filters.addWidget(edit_button, 3, 2)
        filters.addWidget(delete_button, 3, 3)

        self.table = QTableWidget(0, 18)
        self.table.setHorizontalHeaderLabels(
            ["ID", "订单编号", "品名", "工艺", "加工厂", "产品数量", "备品数量", "合计数量", "加工单价", "加工费", "材料单价", "颜色数量", "版费", "日期", "备注", "重做单", "补数单", "金额"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        tip = QLabel("这里会显示已经保存的外发记录，方便按订单、工艺和加工厂回查。")
        tip.setStyleSheet("color: #66758a;")

        layout.addLayout(filters)
        layout.addWidget(tip)
        layout.addWidget(self.table)

    def reset_filters(self) -> None:
        self.search_order_no.clear()
        self.search_factory_name.clear()
        self.search_process_name.clear()
        self.search_outsource_date_from.clear()
        self.search_outsource_date_to.clear()
        self.table.setRowCount(0)

    def load_records(self) -> None:
        date_from = self.search_outsource_date_from.text().strip()
        date_to = self.search_outsource_date_to.text().strip()
        if date_from and not QDate.fromString(date_from, "yyyy-MM-dd").isValid():
            QMessageBox.warning(self, "无法搜索", "外发开始日期必须是 yyyy-MM-dd。")
            return
        if date_to and not QDate.fromString(date_to, "yyyy-MM-dd").isValid():
            QMessageBox.warning(self, "无法搜索", "外发结束日期必须是 yyyy-MM-dd。")
            return
        rows = self.db.search_outsource_records(
            order_no_keyword=self.search_order_no.text(),
            factory_keyword=self.search_factory_name.text(),
            process_keyword=self.search_process_name.text(),
            outsource_date_from=date_from,
            outsource_date_to=date_to,
        )
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["order_no"] or "",
                row.get("product_name") or "",
                row["process_name"] or "",
                row["factory_name"] or "",
                row.get("product_quantity", 0),
                row.get("spare_quantity", 0),
                row["quantity"],
                row["unit_price"],
                row.get("processing_fee", 0),
                row.get("material_unit_price", 0),
                row.get("color_count") or "",
                row.get("plate_fee", 0),
                row.get("outsource_date") or "",
                row.get("remark") or "",
                "是" if row.get("remake_flag") else "",
                "是" if row.get("replenishment_flag") else "",
                "" if row.get("amount") in (None, "") else row.get("amount"),
            ]
            row_items: list[QTableWidgetItem | None] = []
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row_index, column_index, item)
                row_items.append(item)
            apply_outsource_row_style(row_items, row)
        self.table.resizeColumnsToContents()

    def _selected_record_id(self) -> int | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        record_id_item = self.table.item(selected_rows[0].row(), 0)
        if not record_id_item:
            return None
        return int(record_id_item.text())

    def edit_selected_record(self) -> None:
        record_id = self._selected_record_id()
        if record_id is None:
            QMessageBox.warning(self, "无法修改", "请先选中一条外发记录。")
            return
        record = self.db.get_outsource_record(record_id)
        if not record:
            QMessageBox.warning(self, "无法修改", "未找到对应的外发记录。")
            return
        dialog = OutsourceRecordEditDialog(self.db, record, self)
        if dialog.exec() == QDialog.Accepted:
            self.load_records()

    def delete_selected_record(self) -> None:
        record_id = self._selected_record_id()
        if record_id is None:
            QMessageBox.warning(self, "无法删除", "请先选中一条外发记录。")
            return
        result = QMessageBox.question(self, "确认删除", "确定要删除这条外发记录吗？")
        if result != QMessageBox.Yes:
            return
        self.db.delete_outsource_record(record_id)
        self.load_records()
        QMessageBox.information(self, "删除成功", "外发记录已删除。")


class OutsourceRecordEditDialog(QDialog):
    def __init__(self, db: Database, record: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.record = record
        self.setWindowTitle(f"修改外发记录 - {record.get('order_no', '')}")
        self.resize(720, 760)
        self._build_ui()
        self._load_record()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.process_combo = QComboBox()
        self.process_combo.addItems([row["process_name"] for row in self.db.list_outsource_processes()])
        self.process_combo.currentTextChanged.connect(self._refresh_factory_options)
        self.factory_combo = QComboBox()
        self.factory_combo.setEditable(True)
        self.factory_combo.setInsertPolicy(QComboBox.NoInsert)

        self.order_no_label = QLabel()
        self.product_name_label = QLabel()
        self.product_quantity_input = QLineEdit()
        self.spare_quantity_input = QLineEdit()
        self.unit_price_input = QLineEdit()
        self.processing_fee_input = QLineEdit()
        self.length_input = QLineEdit()
        self.width_input = QLineEdit()
        self.thickness_input = QLineEdit()
        self.density_input = QLineEdit()
        self.weight_input = QLineEdit()
        self.material_unit_price_label = QLabel()
        self.color_count_input = QLineEdit()
        self.plate_fee_input = QLineEdit()
        self.outsource_date_input = QLineEdit()
        self.remark_input = QLineEdit()
        self.remake_checkbox = QCheckBox("重做单")
        self.replenishment_checkbox = QCheckBox("补数单")
        self.amount_label = QLabel()

        for field in [
            self.product_quantity_input,
            self.spare_quantity_input,
            self.unit_price_input,
            self.processing_fee_input,
            self.length_input,
            self.width_input,
            self.thickness_input,
            self.density_input,
            self.weight_input,
            self.color_count_input,
            self.plate_fee_input,
            self.outsource_date_input,
        ]:
            field.textChanged.connect(self._recalculate_amount)
        self.process_combo.currentTextChanged.connect(self._recalculate_amount)

        flags_row = QWidget()
        flags_layout = QHBoxLayout(flags_row)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        flags_layout.addWidget(self.remake_checkbox)
        flags_layout.addWidget(self.replenishment_checkbox)
        flags_layout.addStretch()

        form.addRow("订单编号", self.order_no_label)
        form.addRow("品名", self.product_name_label)
        form.addRow("工艺", self.process_combo)
        form.addRow("加工厂", self.factory_combo)
        form.addRow("产品数量", self.product_quantity_input)
        form.addRow("备品数量", self.spare_quantity_input)
        form.addRow("加工单价", self.unit_price_input)
        form.addRow("加工费", self.processing_fee_input)
        form.addRow("长(mm)", self.length_input)
        form.addRow("宽(mm)", self.width_input)
        form.addRow("厚(mm)", self.thickness_input)
        form.addRow("密度", self.density_input)
        form.addRow("重量", self.weight_input)
        form.addRow("材料单价", self.material_unit_price_label)
        form.addRow("颜色数量", self.color_count_input)
        form.addRow("版费", self.plate_fee_input)
        form.addRow("日期", self.outsource_date_input)
        form.addRow("备注", self.remark_input)
        form.addRow("标记", flags_row)
        form.addRow("金额", self.amount_label)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()
        save_button = QPushButton("保存修改")
        save_button.clicked.connect(self.save)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

    def _load_record(self) -> None:
        self.order_no_label.setText(self.record.get("order_no") or "")
        self.product_name_label.setText(self.record.get("product_name") or "")
        self.process_combo.setCurrentText(self.record.get("process_name") or "")
        self._refresh_factory_options()
        self.factory_combo.setCurrentText(self.record.get("factory_name") or "")
        self.product_quantity_input.setText(str(self.record.get("product_quantity") or 0))
        self.spare_quantity_input.setText(str(self.record.get("spare_quantity") or 0))
        self.unit_price_input.setText(str(self.record.get("unit_price") or 0))
        self.processing_fee_input.setText(str(self.record.get("processing_fee") or 0))
        self.length_input.setText(str(self.record.get("length_mm") or 0))
        self.width_input.setText(str(self.record.get("width_mm") or 0))
        self.thickness_input.setText(str(self.record.get("thickness_mm") or 0))
        self.density_input.setText(str(self.record.get("density") or 0.00785))
        self.weight_input.setText(str(self.record.get("weight") or 0.0055))
        self.color_count_input.setText("" if self.record.get("color_count") in (None, "") else str(self.record.get("color_count")))
        self.plate_fee_input.setText(str(self.record.get("plate_fee") or 0))
        self.outsource_date_input.setText(self.record.get("outsource_date") or "")
        self.remark_input.setText(self.record.get("remark") or "")
        self.remake_checkbox.setChecked(bool(self.record.get("remake_flag")))
        self.replenishment_checkbox.setChecked(bool(self.record.get("replenishment_flag")))
        self._recalculate_amount()

    def _refresh_factory_options(self) -> None:
        current_text = self.factory_combo.currentText().strip()
        self.factory_combo.clear()
        self.factory_combo.addItems(
            [row["factory_name"] for row in self.db.list_outsource_factories(self.process_combo.currentText())]
        )
        self.factory_combo.setCurrentText(current_text)

    def _recalculate_amount(self) -> None:
        process_name = self.process_combo.currentText().strip()
        product_quantity = safe_float(self.product_quantity_input.text())
        spare_quantity = safe_float(self.spare_quantity_input.text())
        total_quantity = product_quantity + spare_quantity
        unit_price = safe_float(self.unit_price_input.text())
        processing_fee = safe_float(self.processing_fee_input.text())
        length_mm = safe_float(self.length_input.text())
        width_mm = safe_float(self.width_input.text())
        thickness_mm = safe_float(self.thickness_input.text())
        density = safe_float(self.density_input.text(), 0.00785)
        weight = safe_float(self.weight_input.text(), 0.0055)
        plate_fee = safe_float(self.plate_fee_input.text())
        material_unit_price = (length_mm + 3) * (width_mm + 3) * thickness_mm * density * weight
        self.material_unit_price_label.setText(
            f"{material_unit_price:.6f}".rstrip('0').rstrip('.') or "0"
        )

        if process_name == "冲压":
            amount = total_quantity * ((unit_price if unit_price != 0 else 0) + material_unit_price) + processing_fee
            self.amount_label.setText(f"{amount:.2f}")
        elif process_name == "上色":
            color_count = safe_float(self.color_count_input.text())
            self.amount_label.setText(f"{(total_quantity * unit_price * color_count):.2f}")
        elif process_name == "印刷/UV":
            self.amount_label.setText(f"{(total_quantity * unit_price + plate_fee):.2f}")
        else:
            self.amount_label.setText(f"{(total_quantity * unit_price):.2f}")

    def save(self) -> None:
        process_name = self.process_combo.currentText().strip()
        factory_name = self.factory_combo.currentText().strip()
        if not process_name or not factory_name:
            QMessageBox.warning(self, "无法保存", "请填写工艺和加工厂。")
            return
        try:
            product_quantity = float(self.product_quantity_input.text().strip() or "0")
            spare_quantity = float(self.spare_quantity_input.text().strip() or "0")
            unit_price = float(self.unit_price_input.text().strip() or "0")
            processing_fee = float(self.processing_fee_input.text().strip() or "0")
            length_mm = float(self.length_input.text().strip() or "0")
            width_mm = float(self.width_input.text().strip() or "0")
            thickness_mm = float(self.thickness_input.text().strip() or "0")
            density = float(self.density_input.text().strip() or "0.00785")
            weight = float(self.weight_input.text().strip() or "0.0055")
            plate_fee = float(self.plate_fee_input.text().strip() or "0")
        except ValueError:
            QMessageBox.warning(self, "无法保存", "请输入有效数字。")
            return
        total_quantity = product_quantity + spare_quantity
        if total_quantity <= 0:
            QMessageBox.warning(self, "无法保存", "产品数量和备品数量不能同时为 0。")
            return
        if not QDate.fromString(self.outsource_date_input.text().strip(), "yyyy-MM-dd").isValid():
            QMessageBox.warning(self, "无法保存", "日期必须是 yyyy-MM-dd。")
            return
        color_count = None
        if process_name == "上色":
            color_count_text = self.color_count_input.text().strip()
            if not color_count_text:
                QMessageBox.warning(self, "无法保存", "上色工艺必须填写颜色数量。")
                return
            try:
                color_count = int(color_count_text)
            except ValueError:
                QMessageBox.warning(self, "无法保存", "颜色数量必须是整数。")
                return
        material_unit_price = safe_float(self.material_unit_price_label.text())
        amount_text = self.amount_label.text().strip()
        self.db.update_outsource_record(
            self.record["id"],
            {
                "process_name": process_name,
                "factory_name": factory_name,
                "quantity": total_quantity,
                "product_quantity": product_quantity,
                "spare_quantity": spare_quantity,
                "unit_price": unit_price,
                "processing_fee": processing_fee if process_name == "冲压" else 0,
                "length_mm": length_mm if process_name == "冲压" else 0,
                "width_mm": width_mm if process_name == "冲压" else 0,
                "thickness_mm": thickness_mm if process_name == "冲压" else 0,
                "density": density if process_name == "冲压" else 0.00785,
                "weight": weight if process_name == "冲压" else 0.0055,
                "material_unit_price": material_unit_price if process_name == "冲压" else 0,
                "color_count": color_count if process_name == "上色" else None,
                "plate_fee": plate_fee if process_name == "印刷/UV" else 0,
                "outsource_date": self.outsource_date_input.text().strip(),
                "remark": self.remark_input.text().strip(),
                "amount": float(amount_text) if amount_text else None,
                "remake_flag": 1 if self.remake_checkbox.isChecked() else 0,
                "replenishment_flag": 1 if self.replenishment_checkbox.isChecked() else 0,
            },
        )
        self.accept()


class OutsourceMainWindow(QMainWindow):
    def __init__(self, db: Database, logout_callback=None) -> None:
        super().__init__()
        self.db = db
        self.logout_callback = logout_callback
        self.setWindowTitle("外发登记系统")
        self.resize(1280, 820)

        container = QWidget()
        layout = QVBoxLayout(container)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        logout_button = QPushButton("退出登录")
        logout_button.clicked.connect(self.logout)
        top_bar.addWidget(logout_button)
        layout.addLayout(top_bar)

        tabs = QTabWidget()
        self.outsource_list_tab = OutsourceListTab(self.db)
        self.outsource_form_tab = OutsourceFormTab(self.db, self.outsource_list_tab.load_records)
        self.outsource_config_tab = OutsourceConfigTab(self.db, self.outsource_form_tab)
        tabs.addTab(self.outsource_form_tab, "批量新建外发")
        tabs.addTab(self.outsource_list_tab, "外发记录")
        tabs.addTab(self.outsource_config_tab, "工艺及加工厂管理")
        layout.addWidget(tabs)
        self.setCentralWidget(container)

    def logout(self) -> None:
        if self.logout_callback:
            self.logout_callback(self)
            return
        self.close()


class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.authenticated_system: str | None = None
        self.setWindowTitle("系统登录")
        self.setModal(True)
        self.resize(360, 180)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("请输入账号密码登录")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #213547;")
        layout.addWidget(title)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("账号")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.try_login)
        form.addRow("账号", self.username_input)
        form.addRow("密码", self.password_input)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()
        login_button = QPushButton("登录")
        login_button.clicked.connect(self.try_login)
        button_row.addWidget(login_button)
        layout.addLayout(button_row)

    def try_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        target_system = LOGIN_USERS.get(username)
        if target_system and password == LOGIN_PASSWORD:
            self.authenticated_system = target_system
            self.accept()
            return
        QMessageBox.warning(self, "登录失败", "账号或密码错误，请重新输入。")
        self.password_input.clear()
        self.password_input.setFocus()


class SystemLauncherWindow(QMainWindow):
    def __init__(self, db: Database, open_business_callback=None, open_finance_callback=None) -> None:
        super().__init__()
        self.db = db
        self.open_business_callback = open_business_callback
        self.open_finance_callback = open_finance_callback
        self.setWindowTitle("系统入口")
        self.resize(520, 300)
        self._build_ui()

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("请选择要进入的系统")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #213547;")
        subtitle = QLabel("支持业务订单系统、财务管理系统和外发登记系统入口。")
        subtitle.setStyleSheet("color: #66758a;")

        business_button = QPushButton("进入业务订单系统")
        business_button.setMinimumHeight(44)
        business_button.clicked.connect(self.open_business_system)
        finance_button = QPushButton("进入财务管理系统")
        finance_button.setMinimumHeight(44)
        finance_button.clicked.connect(self.open_finance_system)
        outsource_button = QPushButton("进入外发登记系统")
        outsource_button.setMinimumHeight(44)
        outsource_button.clicked.connect(self.open_outsource_system)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
        layout.addWidget(business_button)
        layout.addWidget(finance_button)
        layout.addWidget(outsource_button)
        layout.addStretch()
        self.setCentralWidget(container)

    def open_business_system(self) -> None:
        if self.open_business_callback:
            self.open_business_callback()

    def open_finance_system(self) -> None:
        if self.open_finance_callback:
            self.open_finance_callback()

    def open_outsource_system(self) -> None:
        callback = getattr(self, "open_outsource_callback", None)
        if callback:
            callback()

    def show_outsource_placeholder(self) -> None:
        QMessageBox.information(self, "暂未开放", "外发登记系统入口已预留，功能暂未实现。")


class AppController:
    def __init__(self) -> None:
        self.db = Database(DB_PATH)
        self.db.initialize()
        self.login_dialog: LoginDialog | None = None
        self.launcher_window: SystemLauncherWindow | None = None
        self.active_window: QMainWindow | None = None
        self.current_system_scope: str | None = None

    def start(self) -> None:
        self.show_login()

    def show_login(self) -> None:
        if self.active_window:
            self.active_window.close()
            self.active_window = None
        if self.launcher_window:
            self.launcher_window.close()
            self.launcher_window = None

        self.login_dialog = LoginDialog()
        if self.login_dialog.exec() != QDialog.Accepted:
            QApplication.instance().quit()
            return
        self.current_system_scope = self.login_dialog.authenticated_system
        self.route_after_login()

    def route_after_login(self) -> None:
        if self.login_dialog:
            self.login_dialog.close()
            self.login_dialog = None
        if self.current_system_scope == "business":
            self.open_business_system()
            return
        if self.current_system_scope == "finance":
            self.open_finance_system()
            return
        if self.current_system_scope == "outsource":
            self.open_outsource_system()
            return
        self.show_launcher()

    def show_launcher(self) -> None:
        if self.login_dialog:
            self.login_dialog.close()
            self.login_dialog = None
        self.launcher_window = SystemLauncherWindow(
            self.db,
            open_business_callback=self.open_business_system,
            open_finance_callback=self.open_finance_system,
        )
        self.launcher_window.open_outsource_callback = self.open_outsource_system
        self.launcher_window.show()

    def open_business_system(self) -> None:
        self._open_system_window(MainWindow(db=self.db, logout_callback=self.logout_to_login))

    def open_finance_system(self) -> None:
        self._open_system_window(
            FinanceMainWindow(self.db, logout_callback=self.logout_to_login)
        )

    def open_outsource_system(self) -> None:
        self._open_system_window(
            OutsourceMainWindow(self.db, logout_callback=self.logout_to_login)
        )

    def _open_system_window(self, window: QMainWindow) -> None:
        if self.launcher_window:
            self.launcher_window.close()
            self.launcher_window = None
        self.active_window = window
        window.show()
        window.activateWindow()
        window.raise_()

    def logout_to_login(self, window: QMainWindow) -> None:
        if self.active_window is window:
            self.active_window = None
        self.current_system_scope = None
        window.close()
        self.show_login()


def run() -> None:
    app = QApplication(sys.argv)
    controller = AppController()
    controller.start()
    sys.exit(app.exec())


