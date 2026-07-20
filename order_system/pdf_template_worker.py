import json
import os
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


PAGE_WIDTH = 540
PAGE_HEIGHT = 780
QR_CODE_RIGHT = 518
QR_CODE_TOP = 17
QR_CODE_SIZE = 34
REMARK_LEFT = 36
REMARK_TOP = 550
REMARK_WIDTH = 146
REMARK_HEIGHT = 182
IMAGE_AREA_LEFT = 193
IMAGE_AREA_TOP = 536
IMAGE_AREA_WIDTH = 315
IMAGE_AREA_HEIGHT = 200
FONT_NAME = "MicrosoftYaHei"
BLACK = (0, 0, 0)
RED = (0.8, 0.12, 0.12)
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
]


for font_path in FONT_CANDIDATES:
    if not font_path.exists():
        continue
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))
        break
    except Exception:  # Some Linux CJK TTC files use unsupported CFF outlines.
        continue
else:
    FONT_NAME = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python -m order_system.pdf_template_worker record.json template.pdf output.pdf")

    record_path = Path(sys.argv[1])
    template_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    record = json.loads(record_path.read_text(encoding="utf-8"))
    overlay_pdf = _build_overlay(record)
    _merge_overlay(template_path, overlay_pdf, output_path)
    return 0


def _build_overlay(record: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setTitle(f"订单预览 {record.get('order_no', '')}")

    _draw_header(pdf, record)
    _draw_process_table(pdf, record)
    _draw_images(pdf, record)
    _draw_footer(pdf, record)

    pdf.save()
    return buffer.getvalue()


def _merge_overlay(template_path: Path, overlay_pdf: bytes, output_path: Path) -> None:
    template_reader = PdfReader(str(template_path))
    overlay_reader = PdfReader(BytesIO(overlay_pdf))
    template_page = template_reader.pages[0]
    template_page.merge_page(overlay_reader.pages[0])

    writer = PdfWriter()
    writer.add_page(template_page)
    with output_path.open("wb") as file_obj:
        writer.write(file_obj)


def _draw_header(pdf: canvas.Canvas, record: dict) -> None:
    _draw_order_qr_code(pdf, record.get("order_no") or "")

    pdf.setFont(FONT_NAME, 12)
    order_type = record.get("order_type") or ""
    order_type_color = RED if str(order_type).startswith("补数单") else BLACK
    _draw_box_text(pdf, order_type, 108, 66, 76, 20, color=order_type_color)
    _draw_box_text(pdf, record.get("salesman") or "", 271, 66, 76, 20)
    _draw_box_text(pdf, record.get("product_name") or "", 434, 66, 77, 20)

    _draw_box_text(pdf, _format_quantity(record), 108, 107, 76, 20)
    _draw_box_text(pdf, record.get("width_mm") or "", 271, 107, 76, 20, top_offset=4)
    _draw_box_text(pdf, record.get("height_mm") or "", 353, 107, 76, 20, top_offset=4)
    thickness = record.get("thickness_mm") or ""
    if record.get("size_as_sample"):
        thickness = (thickness + " 如样").strip()
    _draw_box_text(pdf, thickness, 436, 107, 74, 20, top_offset=4)

    pdf.setFont(FONT_NAME, 12)
    _draw_order_no(pdf, record.get("order_no") or "", 108, 146, 76, 20)
    _draw_box_text(pdf, record.get("order_date") or "", 271, 146, 76, 20, top_offset=8)
    _draw_box_text(pdf, record.get("delivery_date") or "", 434, 146, 77, 20, top_offset=8)


def _draw_order_qr_code(pdf: canvas.Canvas, order_no: str) -> None:
    value = str(order_no or "").strip()
    if not value:
        return

    qr_code = createBarcodeDrawing(
        "QR",
        value=value,
        width=QR_CODE_SIZE,
        height=QR_CODE_SIZE,
    )
    draw_x = QR_CODE_RIGHT - QR_CODE_SIZE
    draw_y = PAGE_HEIGHT - QR_CODE_TOP - QR_CODE_SIZE
    qr_code.drawOn(pdf, draw_x, draw_y)

def _draw_process_table(pdf: canvas.Canvas, record: dict) -> None:
    process_rows = [
        ("材料", _join_selected(record.get("materials_json")), record.get("material_note") or "", 214, 43, True, _note_color(record, "material_note_red")),
        ("电镀", _join_selected(record.get("plating_json")), record.get("plating_note") or "", 257, 39, False, _note_color(record, "plating_note_red")),
        ("配件", _join_selected(record.get("accessories_json")), record.get("accessories_note") or "", 296, 40, False, _note_color(record, "accessories_note_red")),
        ("抛光", _join_selected(record.get("polishing_json")), record.get("polishing_note") or "", 336, 40, False, _note_color(record, "polishing_note_red")),
        ("上色", _coloring_content(record), record.get("coloring_note") or "", 376, 39, False, _note_color(record, "coloring_note_red")),
        ("树脂", _join_selected(record.get("resin_json")), record.get("resin_note") or "", 415, 40, False, _note_color(record, "resin_note_red")),
        ("包装", _packaging_content(record), record.get("packaging_note") or "", 455, 40, False, _note_color(record, "packaging_note_red")),
        ("背模", record.get("back_mode") or "", record.get("back_mode_note") or "", 495, 40, False, _note_color(record, "back_mode_note_red")),
    ]

    for _title, content, note, top, height, wide, note_color in process_rows:
        if wide:
            _draw_multiline_text(pdf, content, 89, top - 9, 415, 17, 13.5, 15, color=BLACK)
            if note.strip():
                _draw_multiline_text(
                    pdf,
                    f"备注：{note.strip()}",
                    89,
                    top + 8,
                    415,
                    height - 17,
                    13.5,
                    15,
                    color=note_color,
                )
            continue

        _draw_multiline_text(pdf, content, 89, top - 10, 93, height - 6, 13.5, 15, color=BLACK)
        _draw_multiline_text(pdf, note, 193, top - 10, 315, height - 6, 13.5, 15, color=note_color)

    _draw_multiline_text(
        pdf,
        record.get("global_note") or "",
        REMARK_LEFT,
        REMARK_TOP,
        REMARK_WIDTH,
        REMARK_HEIGHT,
        11.5,
        13,
        color=_note_color(record, "global_note_red"),
    )


def _draw_images(pdf: canvas.Canvas, record: dict) -> None:
    image_names = _loads_json(record.get("image_paths_json"))
    data_root = Path(os.environ.get("TWD_DATA_DIR", Path(__file__).resolve().parent.parent))
    image_paths = [
        data_root / "images" / Path(image_name).name
        for image_name in image_names
    ]
    image_paths = [path for path in image_paths if path.exists()]
    if not image_paths:
        return

    slots = _image_slots(len(image_paths))
    for image_path, slot in zip(image_paths[:3], slots):
        _draw_image_in_slot(pdf, image_path, *slot)


def _draw_footer(pdf: canvas.Canvas, record: dict) -> None:
    pdf.setFont(FONT_NAME, 13)
    _draw_single_line(pdf, f"{record.get('bi_no') or ''}", 105, 762)
    _draw_single_line(pdf, f"{record.get('production_no') or ''}", 322, 762)


def _format_quantity(record: dict) -> str:
    quantity = record.get("quantity")
    if quantity in (None, ""):
        return ""
    spare_quantity = record.get("spare_quantity")
    quantity_text = str(quantity)
    if spare_quantity not in (None, "", 0, "0"):
        quantity_text = f"{quantity_text}+{spare_quantity}"
    unit = record.get("quantity_unit") or "\u4e2a"
    return f"{quantity_text}{unit}"


def _draw_box_text(
    pdf: canvas.Canvas,
    text: str,
    left: float,
    top: float,
    width: float,
    height: float,
    top_offset: float | None = None,
    color: tuple[float, float, float] = BLACK,
) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    pdf.setFont(FONT_NAME, 12)
    pdf.setFillColorRGB(*color)
    if top_offset is None:
        y = PAGE_HEIGHT - top - (height / 2) - 4
    else:
        y = PAGE_HEIGHT - top - top_offset
    pdf.drawString(left + 4, y, clean)


def _draw_single_line(pdf: canvas.Canvas, text: str, left: float, top: float) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    y = PAGE_HEIGHT - top - 4
    pdf.setFillColorRGB(*BLACK)
    pdf.drawString(left, y, clean)


def _draw_order_no(
    pdf: canvas.Canvas,
    order_no: str,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    clean = str(order_no or "").strip()
    if not clean:
        return
    if "-" in clean:
        prefix, suffix = clean.split("-", 1)
        formatted_suffix = f"{suffix[:2]} {suffix[2:6]} {suffix[6:]}" if len(suffix) == 9 and suffix.isdigit() else suffix
        content = f"{prefix}-\n{formatted_suffix}"
        _draw_multiline_text(pdf, content, left + 4, top - 9, width - 8, height + 22, 11.5, 11.5, color=BLACK)
        return
    _draw_box_text(pdf, clean, left, top, width, height)


def _draw_multiline_text(
    pdf: canvas.Canvas,
    text: str,
    left: float,
    top: float,
    width: float,
    height: float,
    font_size: float,
    leading: float,
    color: tuple[float, float, float] = BLACK,
) -> None:
    clean = (text or "").strip()
    if not clean:
        return

    lines = _wrap_text(clean, width, font_size)
    max_lines = max(1, int(height // leading))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1]:
            lines[-1] = lines[-1].rstrip(".") + "..."

    pdf.setFont(FONT_NAME, font_size)
    pdf.setFillColorRGB(*color)
    text_object = pdf.beginText()
    text_object.setTextOrigin(left, PAGE_HEIGHT - top - font_size)
    text_object.setLeading(leading)
    for line in lines:
        text_object.textLine(line)
    pdf.drawText(text_object)


def _wrap_text(text: str, width: float, font_size: float) -> list[str]:
    wrapped_lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            wrapped_lines.append("")
            continue

        current = ""
        for char in paragraph:
            candidate = current + char
            if pdfmetrics.stringWidth(candidate, FONT_NAME, font_size) <= width:
                current = candidate
                continue
            if current:
                wrapped_lines.append(current)
            current = char
        if current:
            wrapped_lines.append(current)
    return wrapped_lines


def _image_slots(image_count: int) -> list[tuple[float, float, float, float]]:
    if image_count <= 1:
        return [(IMAGE_AREA_LEFT, IMAGE_AREA_TOP, IMAGE_AREA_WIDTH, IMAGE_AREA_HEIGHT)]
    if image_count == 2:
        slot_width = (IMAGE_AREA_WIDTH - 12) / 2
        return [
            (IMAGE_AREA_LEFT, IMAGE_AREA_TOP, slot_width, IMAGE_AREA_HEIGHT),
            (IMAGE_AREA_LEFT + slot_width + 12, IMAGE_AREA_TOP, slot_width, IMAGE_AREA_HEIGHT),
        ]
    slot_width = (IMAGE_AREA_WIDTH - 20) / 3
    return [
        (IMAGE_AREA_LEFT, IMAGE_AREA_TOP, slot_width, IMAGE_AREA_HEIGHT),
        (IMAGE_AREA_LEFT + slot_width + 10, IMAGE_AREA_TOP, slot_width, IMAGE_AREA_HEIGHT),
        (IMAGE_AREA_LEFT + (slot_width + 10) * 2, IMAGE_AREA_TOP, slot_width, IMAGE_AREA_HEIGHT),
    ]


def _draw_image_in_slot(
    pdf: canvas.Canvas,
    image_path: Path,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    reader = ImageReader(str(image_path))
    image_width, image_height = reader.getSize()
    scale = min(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    x = left + (width - draw_width) / 2
    y = PAGE_HEIGHT - top - draw_height
    pdf.drawImage(reader, x, y, draw_width, draw_height, preserveAspectRatio=True, mask="auto")


def _combine_content_and_note(content: str, note: str) -> str:
    content = content.strip()
    note = note.strip()
    if content and note:
        return f"{content}\n备注：{note}"
    if note:
        return f"备注：{note}"
    return content


def _note_color(record: dict, key: str) -> tuple[float, float, float]:
    return RED if int(record.get(key) or 0) else BLACK


def _coloring_content(record: dict) -> str:
    return _join_selected(record.get("coloring_json"))

def _packaging_content(record: dict) -> str:
    selected = _join_selected(record.get("packaging_json"))
    rule = (record.get("packaging_rule") or "").strip()
    if selected and rule:
        return f"{selected}\n{rule}"
    return selected or rule


def _join_selected(value: str | None) -> str:
    return "、".join(_loads_json(value))


def _loads_json(value: str | None) -> list[str]:
    if not value:
        return []
    return json.loads(value)


if __name__ == "__main__":
    raise SystemExit(main())
