ORDER_TYPES = ["\u65b0\u8ba2\u5355", "\u6837\u54c1\u5355", "\u91cd\u505a\u5355", "\u6253\u6837\u4e0b\u5355", "\u590d\u8ba2\u5355", "\u8d60\u505a\u5355"]
QUANTITY_UNITS = ["\u4e2a", "\u5957"]
BASE_MATERIALS = ["\u9752\u94dc\u54ac\u677f", "\u94dc", "\u94c1\u8d28", "\u950c\u5408\u91d1", "\u4f4e\u6e29\u950c\u5408\u91d1", "\u94dd", "\u4e0d\u9508\u94a2"]
SURFACE_CRAFTS = ["\u70e4\u6f06", "\u73d0\u7405", "UV", "\u5e73\u5370", "\u956d\u96d5"]
MATERIALS = BASE_MATERIALS + [
    f"{material}  {craft}"
    for material in BASE_MATERIALS
    for craft in SURFACE_CRAFTS
]
PLATING = ["\u5982\u6837", "\u91d1", "\u94f6", "\u954d", "\u53e4\u94f6", "\u9ed1\u954d", "\u96fe\u954d", "\u53e4\u954d", "\u7ea2\u94dc", "\u9752\u94dc", "\u53e4\u7ea2\u94dc", "\u53e4\u91d1", "\u53e4\u9752\u94dc", "\u96fe\u91d1", "\u5237\u7ebf\u5c01\u6cb9", "\u4eff\u91d1", "\u67d3\u9ed1", "\u771f\u91d1", "\u91d1+\u954d"]
ACCESSORIES = ["10mm \u523a\u9a6c\u9488", "8mm \u523a\u9a6c\u9488", "\u5b89\u5168\u522b\u9488", "\u94f6\u9521", "\u710a\u9521", "\u710a\u80f6", "\u7b80\u9488", "\u78c1\u94c1", "\u5b9d\u77f3", "\u67f3\u9488"]
POLISHING = ["\u6b63\u9762", "\u4fa7\u9762", "\u80cc\u9762", "\u4e09\u9762", "\u55b7\u7802"]
COLORING_OPTIONS = ["\u5f69\u56fe", "\u6837\u54c1", "\u8bf4\u660e"]
RESIN_OPTIONS = ["\u4e00\u822c", "\u539a", "\u8584", "\u53cc\u9762", "\u5355\u9762"]
PACKAGING = ["\u7a7a\u767d\u888b", "\u5939\u94fe\u888b", "OPP\u888b", "MIC\u888b", "PVC\u888b", "\u6c14\u6ce1\u888b", "\u9ed1\u80f6\u5e3d", "\u9ec4\u80f6\u5e3d", "\u8774\u8776\u5e3d", "\u88c5\u8ba2", "\u767d\u7eb8\u5377"]
BACK_MODES = ["\u5982\u6837", "\u5149\u5e73", "\u5e03\u7eb9", "\u7802\u9762", "\u56e2\u6a21", "\u53cc\u9762\u6a21"]


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
