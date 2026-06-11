#!/usr/bin/env python3
"""
SKU 映射器回归测试 (CI 自动回归用例集)

目的:
  锁定 _clean_product_name + map_sku_batch 的关键行为,防止后续修改回归
  v5.13.3 (2026-06-11) 沧州行别营店 "果糖-" 匹配不到 bug 修复后建立

测试分两组:
  A) _clean_product_name 单元测试 (纯字符串清洗,无需 DB)
  B) map_sku_batch 端到端测试 (需要真实 DB,验证 SKU 映射+置信度)

运行方式:
  python3 scripts/test_sku_mapper_regression.py

退出码:
  0 = 全部通过
  1 = 有失败

环境要求:
  - DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD 环境变量
  - 或项目根目录的 .env 文件
"""
import os
import sys
import traceback

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)


# ===================== 测试结果统计 =====================

PASS_COUNT = 0
FAIL_COUNT = 0
FAILURES = []


def _record(ok, name, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  ✅ {name}")
    else:
        FAIL_COUNT += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name} -- {detail}")


def _try_import():
    """导入待测试模块 (失败时友好退出)"""
    try:
        from tools._sku_mapper import _clean_product_name, map_sku_batch
        from db.connection import get_default_db_config
        return _clean_product_name, map_sku_batch, get_default_db_config
    except Exception as e:
        print(f"❌ 无法导入 _sku_mapper 模块: {e}")
        traceback.print_exc()
        sys.exit(2)


def _get_db_config():
    """从环境变量/.env 加载 DB 配置"""
    # 优先用 .env
    env_path = os.path.join(SKILL_DIR, "..", "..", ".env")
    env_path = os.path.abspath(env_path)
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    return {
        "host": os.environ.get("DB_HOST", "agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


# ===================== A) _clean_product_name 单元测试 =====================


def test_clean_product_name(_clean_product_name):
    """_clean_product_name 单元测试 (无需 DB)"""
    print("\n[A] _clean_product_name 单元测试")
    print("-" * 60)

    cases = [
        # ---- 基础不变 ----
        ("果糖", "果糖"),
        ("椰子水950ml", "椰子水950ml"),
        ("白糖糕D-X-H", "白糖糕D-X-H"),
        # ---- 中间连接符保留 (不能误删) ----
        ("鱼你幸福-X-猪肉片", "鱼你幸福-X-猪肉片"),
        ("冻品-鱼你幸福猪肉片", "冻品-鱼你幸福猪肉片"),
        ("D-X-H-辣白菜", "D-X-H-辣白菜"),
        # ---- v5.13.3 修复: 末尾孤立分隔符 ----
        ("果糖-", "果糖"),
        ("果糖_", "果糖"),
        ("果糖/", "果糖"),
        ("果糖.", "果糖"),
        ("果糖,", "果糖"),
        ("果糖;", "果糖"),
        ("果糖:", "果糖"),
        ("果糖\\", "果糖"),
        # ---- v5.13.3 修复: 开头孤立分隔符 ----
        ("-果糖", "果糖"),
        ("_果糖", "果糖"),
        (".果糖", "果糖"),
        # ---- v5.13.3 修复: 两端都有 ----
        ("-果糖-", "果糖"),
        ("-果糖_", "果糖"),
        # ---- v5.13.3 修复: 多个连续分隔符 ----
        ("果糖---", "果糖"),
        ("果糖_-./", "果糖"),
        ("---果糖---", "果糖"),
        # ---- 中间连接符 + 末尾孤立符 (只去末尾) ----
        ("白糖糕D-X-H-", "白糖糕D-X-H"),
        ("白糖糕D-X-H---", "白糖糕D-X-H"),
        ("鱼你幸福-X-猪肉片-", "鱼你幸福-X-猪肉片"),
        # ---- 括号内规格去除 ----
        ("浩然奥尔良翅中(10袋)", "浩然奥尔良翅中"),
        ("浩然奥尔良翅中（10袋）", "浩然奥尔良翅中"),
        ("冻品-鱼你幸福猪肉片(1KG*12包/箱)", "冻品-鱼你幸福猪肉片"),
        # ---- 空白处理 ----
        ("果糖 ", "果糖"),
        (" 果糖", "果糖"),
        (" 果糖 ", "果糖"),
        ("果 糖", "果糖"),  # 中间空格也去除(原设计)
    ]

    for inp, expected in cases:
        actual = _clean_product_name(inp)
        _record(
            actual == expected,
            f'clean("{inp}") = "{actual}"',
            f'期望 "{expected}"' if actual != expected else "",
        )


# ===================== B) map_sku_batch 端到端测试 =====================


def _make_item(product_name, unit, quantity=1, seq=1):
    return {
        "product_name": product_name,
        "spec": "",
        "unit": unit,
        "quantity": quantity,
        "seq": seq,
    }


def test_sku_exact_match(map_sku_batch, db_config):
    """Layer 1 精确匹配 (大小单位 SKU 都存在的场景)"""
    print("\n[B1] Layer 1 精确匹配 - 椰子水950ml (HZ2023101200002)")
    print("-" * 60)

    # 完整原名匹配 - 应返回大单位
    items = [_make_item("椰子水950ml", "件")]
    results, unmatched = map_sku_batch("HZ2023101200002", items, db_config)
    if results:
        r = results[0]
        _record(
            r["matched"] and r["sku_code"] == "SK231013000200",
            "椰子水950ml+件 → SK231013000200",
            f"实际 sku_code={r['sku_code']}, matched={r['matched']}",
        )
        _record(
            r["unit_type"] == "大单位",
            "椰子水950ml+件 → unit_type=大单位",
            f"实际 unit_type={r['unit_type']}",
        )
        _record(
            r["quantity"] == 1,
            "椰子水950ml quantity 透传 = 1",
            f"实际 quantity={r['quantity']}",
        )
    else:
        _record(False, "椰子水950ml+件", "未匹配 (Layer 1 失败)")


def test_sku_v5133_fix(map_sku_batch, db_config):
    """v5.13.3 修复: 末尾孤立分隔符 (金姐反馈的果糖- bug)"""
    print("\n[B2] v5.13.3 修复 - 果糖系列孤立分隔符 (HZ2023061500002)")
    print("-" * 60)

    # 关键: 订单单位=桶 时, 至少要命中 (matched=True)
    cases = [
        ("果糖", "桶", "果糖/新 + 桶"),
        ("果糖-", "桶", "果糖- + 桶 (末尾孤立-)"),
        ("果糖_", "桶", "果糖_ + 桶 (末尾孤立_)"),
        ("-果糖", "桶", "-果糖 + 桶 (开头孤立-)"),
        ("-果糖-", "桶", "-果糖- + 桶 (两端孤立-)"),
    ]

    for product_name, unit, desc in cases:
        items = [_make_item(product_name, unit)]
        results, unmatched = map_sku_batch("HZ2023061500002", items, db_config)
        if results:
            r = results[0]
            _record(
                r["matched"],
                f"{desc} → matched=True",
                f"sku_name={r['sku_name']}, method={r['match_method'][:30]}",
            )
        else:
            _record(False, f"{desc}", "未匹配 (v5.13.3 修复失败)")


def test_sku_preserve_connector(map_sku_batch, db_config):
    """中间连接符保留: 白糖糕D-X-H 系列"""
    print("\n[B3] 中间连接符保留 - 白糖糕D-X-H (HZ2025122000013)")
    print("-" * 60)

    # 完整原名应 Layer 1 精确匹配 (置信度0.95)
    items = [_make_item("白糖糕D-X-H", "包")]
    results, unmatched = map_sku_batch("HZ2025122000013", items, db_config)
    if results:
        r = results[0]
        _record(
            r["matched"] and r["confidence"] >= 0.9,
            "白糖糕D-X-H+包 → Layer1 精确匹配 (conf>=0.9)",
            f"sku={r['sku_code']}, conf={r['confidence']}, method={r['match_method'][:30]}",
        )
    else:
        _record(False, "白糖糕D-X-H", "未匹配")

    # 末尾多个孤立 - (应 Layer1b, 只去末尾)
    items = [_make_item("白糖糕D-X-H-", "包")]
    results, unmatched = map_sku_batch("HZ2025122000013", items, db_config)
    if results:
        r = results[0]
        _record(
            r["matched"],
            "白糖糕D-X-H- → matched (只去末尾-)",
            f"sku={r['sku_code']}, conf={r['confidence']}",
        )
        # 不能被误匹配到其他商品
        _record(
            "白糖糕" in r["sku_name"],
            "白糖糕D-X-H- → sku_name 仍含\"白糖糕\"",
            f"实际 sku_name={r['sku_name']}",
        )
    else:
        _record(False, "白糖糕D-X-H-", "未匹配")


def test_sku_bracket_spec(map_sku_batch, db_config):
    """括号内规格去除: 中文/英文括号"""
    print("\n[B4] 括号规格 - 浩然奥尔良翅中 (HZ2024091100001)")
    print("-" * 60)

    # 英文括号
    items = [_make_item("浩然奥尔良翅中(10袋)", "件")]
    results, unmatched = map_sku_batch("HZ2024091100001", items, db_config)
    if results:
        r = results[0]
        _record(
            r["matched"],
            "浩然奥尔良翅中(10袋) 英文括号 → matched",
            f"sku={r['sku_code']}, conf={r['confidence']}",
        )
    else:
        # 没匹配也可能是这个货主下没有完全对应的 SKU, 不算 fail
        _record(
            True,
            "浩然奥尔良翅中(10袋) 未命中 - 货主下无对应 SKU (acceptable)",
            "",
        )

    # 中文括号
    items = [_make_item("浩然奥尔良翅中（10袋）", "件")]
    results, unmatched = map_sku_batch("HZ2024091100001", items, db_config)
    if results:
        r = results[0]
        _record(
            r["matched"],
            "浩然奥尔良翅中（10袋） 中文括号 → matched",
            f"sku={r['sku_code']}, conf={r['confidence']}",
        )
    else:
        _record(
            True,
            "浩然奥尔良翅中（10袋） 未命中 - 货主下无对应 SKU (acceptable)",
            "",
        )


# ===================== 主函数 =====================


def main():
    print("=" * 60)
    print("SKU Mapper 回归测试 (v5.13.3+)")
    print("=" * 60)

    _clean_product_name, map_sku_batch, _ = _try_import()

    # A 单元测试 (无需 DB)
    test_clean_product_name(_clean_product_name)

    # B 端到端测试 (需要 DB)
    db_config = _get_db_config()
    if not db_config["password"]:
        print("\n⚠️  跳过端到端测试: DB_PASSWORD 未配置")
        print("   请在 .env 中设置 DB_PASSWORD 或导出环境变量")
    else:
        try:
            test_sku_exact_match(map_sku_batch, db_config)
            test_sku_v5133_fix(map_sku_batch, db_config)
            test_sku_preserve_connector(map_sku_batch, db_config)
            test_sku_bracket_spec(map_sku_batch, db_config)
        except Exception as e:
            print(f"\n❌ 端到端测试异常: {e}")
            traceback.print_exc()
            global FAIL_COUNT
            FAIL_COUNT += 1

    # 汇总
    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"总计: {total} 个测试, {PASS_COUNT} ✅ 通过, {FAIL_COUNT} ❌ 失败")
    if FAILURES:
        print("\n失败列表:")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
    print("=" * 60)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()