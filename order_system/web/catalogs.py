ORDER_TYPES = ["新订单", "样品单", "重做单", "打样下单", "复订单", "赔做单"]
QUANTITY_UNITS = ["个", "套"]
BASE_MATERIALS = ["青铜咬板", "铜", "铁质", "锌合金", "低温锌合金", "铝", "不锈钢"]
SURFACE_CRAFTS = ["烤漆", "珐琅", "UV", "镭雕"]
MATERIALS = BASE_MATERIALS + [
    f"{material}  {craft}"
    for material in BASE_MATERIALS
    for craft in SURFACE_CRAFTS
]
PLATING = ["如样", "银", "镍", "古银", "黑镍", "雾镍", "古镍", "红铜", "青铜", "古红铜", "古金", "古青铜", "雾金", "刷线封油", "仿金", "染黑", "真金", "金+镍"]
ACCESSORIES = ["10mm 刺马针", "8mm 刺马针", "安全别针", "银锡", "焊锡", "焊胶", "简针", "磁铁", "宝石", "柳针"]
POLISHING = ["正面", "侧面", "背面", "三面", "喷砂"]
COLORING_OPTIONS = ["彩图", "样品", "说明"]
RESIN_OPTIONS = ["一般", "厚", "薄", "双面", "单面"]
PACKAGING = ["空白袋", "夹链袋", "蝴蝶帽", "MIC袋", "OPP袋", "气泡袋", "PVC袋", "装订"]
BACK_MODES = ["光平", "布纹", "砂面", "团模", "双面模"]


def import_catalogs() -> dict[str, list[str]]:
    return {
        "order_type": ORDER_TYPES,
        "quantity_unit": QUANTITY_UNITS,
        "materials": MATERIALS,
        "base_materials": BASE_MATERIALS,
        "surface_crafts": SURFACE_CRAFTS,
        "plating": PLATING,
        "accessories": ACCESSORIES,
        "polishing": POLISHING,
        "coloring": COLORING_OPTIONS,
        "resin": RESIN_OPTIONS,
        "packaging": PACKAGING,
        "back_mode": BACK_MODES,
    }

