"""
Regression test: public execute helpers must work when this skill directory is
used directly, without a top-level ``skills`` package on sys.path.
"""
import os
import sys


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from __init__ import OrderSkillError, OrderToHuadingTemplate


def main() -> None:
    skill = object.__new__(OrderToHuadingTemplate)

    text = """订单编号: DH-O-TEST-IMPORT
公司名称: 任丘三中店
联系人: 任建华
联系电话: 18154355555
1 P9456694174 椰果果粒 3 件
"""
    try:
        skill.tools_parse(text, order_type="text")
        raise AssertionError("tools_parse should not be directly accessible")
    except OrderSkillError as exc:
        assert exc.code == "E001", exc

    result = object.__getattribute__(skill, "tools_parse")(text, order_type="text")

    assert result["success"], result
    assert result["_parse_method"] in ("llm", "regex_fallback"), result
    assert result["stores"], result
    print("PASSED execute helper import fallback")


if __name__ == "__main__":
    main()
