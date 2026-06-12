"""
Regression test for deterministic text parsing in tools/_order_parser.py.
"""
import os
import sys


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from tools import _order_parser as order_parser


ORDER_TEXT = """订单编号: DH-O-20260423-294092
公司名称: 任丘三中店
联系人: 任建华
联系电话: 18154355555
收货地址: 河北省沧州市任丘市会站北道任丘市第三中学对面制茶青年
1 P9456694174 椰果果粒 规格：2kg*10袋 3 件
2 P2763858458 蓝莓果肉果酱 1 件
3 P8365640612 原味晶球 件：1kg*20袋 2 件
"""


def main() -> None:
    original_call_llm = order_parser._call_llm
    order_parser._call_llm = lambda *_args, **_kwargs: {"success": False, "error": "forced"}
    try:
        result = order_parser.parse(ORDER_TEXT, order_type="text")
    finally:
        order_parser._call_llm = original_call_llm

    assert result["success"], result
    assert result["_parse_method"] == "regex_fallback", result
    assert "任丘三中店" in result["stores"], result

    store = result["stores"]["任丘三中店"]
    assert store["order_no"] == "DH-O-20260423-294092"
    assert store["contact_person"] == "任建华"
    assert store["phone"] == "18154355555"
    assert len(store["items"]) == 3
    assert sum(item["quantity"] for item in store["items"]) == 6
    assert store["items"][0]["product_code"] == "P9456694174"
    assert store["items"][0]["product_name"] == "椰果果粒"
    assert store["items"][0]["quantity"] == 3
    print("PASSED text fallback regression")


if __name__ == "__main__":
    main()
