"""
Regression test for Excel orders that have an order header block followed by
an item-detail table.

This intentionally forces the LLM path to fail so the deterministic Excel
fallback is exercised.
"""
import os
import sys
import tempfile

from openpyxl import Workbook


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from tools import _order_parser as order_parser


def _make_header_detail_order(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    rows = [
        ["订 货 单"],
        ["订单编号", "DH-O-20260423-294092", "下单日期", "2026-04-23 13:03", "预交货日期"],
        ["公司名称", "任丘三中店", None, None, "联系人", None, "任建华"],
        ["收货地址", "河北省沧州市任丘市会站北道任丘市第三中学对面制茶青年", None, None, "联系电话", None, "18154355555"],
        ["商 品 明 细"],
        ["序号", "商品编码", "商品名称", "商品规格", None, "数量", "计量单位", None, "备注"],
        [1, "P9456694174", "椰果果粒", "规格：2kg*10袋", None, 3, "件"],
        [2, "P2763858458", "蓝莓果肉果酱", None, None, 1, "件"],
        [3, "P8365640612", "原味晶球", "件：1kg*20袋", None, 2, "件"],
        [4, "P8757486782", "原味水晶冻粉", None, None, 1, "件"],
        [5, "P2969330615", "春香茉莉花茶（50袋*100g）", "件：100g×50袋", None, 1, "件"],
        [6, "P7869107138", "常温五合一芝士奶盖", None, None, 1, "件"],
        [7, "P7669860793", "奶冻粉蛋白固体饮料", None, None, 1, "件"],
        ["合计：", None, None, None, None, 10],
    ]
    for row in rows:
        ws.append(row)
    wb.save(path)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "header_detail_order.xlsx")
        _make_header_detail_order(path)

        original_call_llm = order_parser._call_llm
        order_parser._call_llm = lambda *_args, **_kwargs: {"success": False, "error": "forced"}
        try:
            result = order_parser.parse(path, order_type="excel")
        finally:
            order_parser._call_llm = original_call_llm

    assert result["success"], result
    assert result["_parse_method"] == "regex_fallback", result
    assert "任丘三中店" in result["stores"], result

    store = result["stores"]["任丘三中店"]
    assert store["store_name"] == "任丘三中店"
    assert store["order_no"] == "DH-O-20260423-294092"
    assert store["contact_person"] == "任建华"
    assert store["phone"] == "18154355555"
    assert "第三中学对面制茶青年" in store["address"]
    assert len(store["items"]) == 7
    assert sum(item["quantity"] for item in store["items"]) == 10
    assert store["items"][0] == {
        "seq": 1,
        "product_code": "P9456694174",
        "product_name": "椰果果粒",
        "spec": "规格：2kg*10袋",
        "quantity": 3,
        "unit": "件",
        "remark": "",
    }

    print("PASSED header-detail Excel fallback regression")


if __name__ == "__main__":
    main()
