#!/usr/bin/env python3
"""
映射准确率回归测试 (CI 集成)

目的:
  覆盖门店匹配、货主识别、单位映射 3 个环节的准确率
  防止后续代码修改导致匹配质量退化

测试分组:
  A) 门店匹配准确率 — match_store() 多层匹配
  B) 货主识别准确率 — 门店匹配后 owner_code 正确性
  C) 单位映射准确率 — order_unit → unit_type 正确性

环境要求:
  - DB 连接 (通过 .env 或环境变量)
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

# 🆕 分组统计 (v5.15.2): 每个测试组的 pass/fail 独立统计,用于末尾准确率汇总
GROUP_STATS = {}  # {group_name: {"pass": int, "fail": int}}
CURRENT_GROUP = ""


def _set_group(name: str):
    """设置当前测试组名 (在每组测试开头调用)"""
    global CURRENT_GROUP
    CURRENT_GROUP = name
    if name not in GROUP_STATS:
        GROUP_STATS[name] = {"pass": 0, "fail": 0}


def _record(ok, name, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  ✅ {name}")
    else:
        FAIL_COUNT += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name} -- {detail}")
    # 🆕 分组统计
    if CURRENT_GROUP and CURRENT_GROUP in GROUP_STATS:
        if ok:
            GROUP_STATS[CURRENT_GROUP]["pass"] += 1
        else:
            GROUP_STATS[CURRENT_GROUP]["fail"] += 1


def _get_db_config():
    """获取数据库配置"""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(SKILL_DIR, "..", "..", ".env"))
    except ImportError:
        pass

    host = os.environ.get("DB_HOST", "")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("DB_PORT", "5432")),
        "database": os.environ.get("DB_NAME", "neo"),
        "user": os.environ.get("DB_USER", "agenthub"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


# ===================== A: 门店匹配准确率 =====================

def test_store_matching(db_config):
    """门店匹配准确率测试"""
    _set_group("门店匹配")
    print("\n[A] 门店匹配准确率")
    print("-" * 60)

    from tools._store_matcher import match_store

    # 测试用例: (输入门店名, 期望 owner_code, 说明)
    # 从真实 store_list 中取样, 覆盖不同匹配层
    test_cases = [
        # Layer 2: 精确匹配 (门店名完全一致)
        {
            "store_name": "制茶青年-保定小朱庄店",
            "expected_owner": "HZ2023061500002",
            "desc": "精确匹配-制茶青年",
        },
        {
            "store_name": "口口椰-K南京莱迪店",
            "expected_owner": "HZ2023101200002",
            "desc": "精确匹配-口口椰",
        },
        # Layer 1: 客户公司匹配 (owner_name)
        {
            "store_name": "随便什么店名",
            "customer_company": "郑州市必德供应链管理有限公司",
            "expected_owner": "HZ2024091100001",
            "desc": "客户公司匹配-必德",
        },
        {
            "store_name": "test",
            "customer_company": "河南上黎供应链管理有限公司",
            "expected_owner": "HZ2023061500002",
            "desc": "客户公司匹配-上黎",
        },
    ]

    for tc in test_cases:
        try:
            result = match_store(
                store_name=tc["store_name"],
                customer_company=tc.get("customer_company"),
                db_config=db_config,
            )
            if result is None:
                _record(False, tc["desc"], "match_store 返回 None")
                continue

            actual_owner = result.get("owner_code", "")
            matched = actual_owner == tc["expected_owner"]
            _record(matched, tc["desc"],
                    f"期望 owner={tc['expected_owner']}, 实际={actual_owner}")
        except Exception as e:
            _record(False, tc["desc"], f"异常: {e}")


# ===================== B: 货主识别准确率 =====================

def test_owner_identification(db_config):
    """货主识别准确率测试 — 通过门店间接验证 owner_code"""
    _set_group("货主识别")
    print("\n[B] 货主识别准确率 (门店→owner_code)")
    print("-" * 60)

    from tools._store_matcher import match_store

    # 从 DB 取真实门店样本, 每个货主取 2 个门店
    import psycopg2
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # 取每个货主的门店样本 (排除 0 门店的货主)
    cur.execute("""
        SELECT DISTINCT ON (owner_code) store_name, owner_code
        FROM store_list
        WHERE owner_code IS NOT NULL AND owner_code != ''
        ORDER BY owner_code, store_name
    """)
    samples = cur.fetchall()
    conn.close()

    if not samples:
        _record(False, "货主识别", "store_list 无数据")
        return

    for store_name, expected_owner in samples:
        try:
            result = match_store(
                store_name=store_name,
                db_config=db_config,
            )
            if result is None:
                _record(False, f"{store_name[:25]}", "match_store 返回 None")
                continue

            actual_owner = result.get("owner_code", "")
            matched = actual_owner == expected_owner
            _record(matched, f"{store_name[:25]} → {expected_owner}",
                    f"实际 owner={actual_owner}")
        except Exception as e:
            _record(False, f"{store_name[:25]}", f"异常: {e}")


# ===================== C: 单位映射准确率 =====================

def test_unit_mapping(db_config):
    """单位映射准确率测试 — order_unit → unit_type + unit"""
    _set_group("单位映射")
    print("\n[C] 单位映射准确率")
    print("-" * 60)

    from tools._sku_mapper import map_sku_batch

    # 测试用例: (货主ID, 商品名, order_unit, 期望 unit_type, 期望 sku_unit, 说明)
    test_cases = [
        # 制茶青年 (HZ2023061500002)
        {
            "shipper_id": "HZ2023061500002",
            "product_name": "果糖/新",
            "unit": "桶",
            "expected_unit_type": "小单位",
            "expected_unit": "桶",
            "desc": "果糖+桶 → 小单位/桶",
        },
        {
            "shipper_id": "HZ2023061500002",
            "product_name": "果糖/新",
            "unit": "箱",
            "expected_unit_type": "大单位",
            "expected_unit": "箱",
            "desc": "果糖+箱 → 大单位/箱",
        },
        # 安徽洪通通 (HZ2023101200002)
        {
            "shipper_id": "HZ2023101200002",
            "product_name": "椰子水950ml",
            "unit": "件",
            "expected_unit_type": "大单位",
            "expected_unit": "件",
            "desc": "椰子水950ml+件 → 大单位/件",
        },
    ]

    for tc in test_cases:
        try:
            items = [{
                "seq": 1,
                "product_name": tc["product_name"],
                "spec": "",
                "quantity": 1,
                "unit": tc["unit"],
            }]
            results, unmatched = map_sku_batch(tc["shipper_id"], items, db_config)

            if not results:
                _record(False, tc["desc"], "map_sku_batch 无结果")
                continue

            r = results[0]
            actual_unit_type = r.get("unit_type", "")
            actual_unit = r.get("unit", "")

            # 验证 unit_type
            type_ok = actual_unit_type == tc["expected_unit_type"]
            _record(type_ok, f"{tc['desc']} (unit_type)",
                    f"期望={tc['expected_unit_type']}, 实际={actual_unit_type}")

            # 验证 unit
            unit_ok = actual_unit == tc["expected_unit"]
            _record(unit_ok, f"{tc['desc']} (unit)",
                    f"期望={tc['expected_unit']}, 实际={actual_unit}")

        except Exception as e:
            _record(False, tc["desc"], f"异常: {e}")


# ===================== D: 仓库映射准确率 =====================

def test_warehouse_mapping(db_config):
    """仓库映射准确率测试 — warehouse_name → warehouse_code"""
    _set_group("仓库映射")
    print("\n[D] 仓库映射准确率")
    print("-" * 60)

    from tools._template_generator import get_warehouse_code
    import psycopg2

    # Part 1: 精确匹配测试 — 从 warehouse_code_mapping 表取样
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # 取 10 个有代表性的仓库 (覆盖高频使用的仓库)
    cur.execute("""
        SELECT wm.warehouse_name, wm.warehouse_code,
               COUNT(sl.store_code) as store_count
        FROM warehouse_code_mapping wm
        LEFT JOIN store_list sl ON sl.warehouse = wm.warehouse_name
        GROUP BY wm.warehouse_name, wm.warehouse_code
        ORDER BY store_count DESC
        LIMIT 10
    """)
    samples = cur.fetchall()
    conn.close()

    if not samples:
        _record(False, "仓库映射", "warehouse_code_mapping 无数据")
        return

    for wh_name, expected_code, store_count in samples:
        try:
            actual_code = get_warehouse_code(wh_name, db_config)
            matched = actual_code == expected_code
            _record(matched,
                    f"{wh_name} (关联{store_count}店) → {expected_code}",
                    f"实际 code={actual_code}")
        except Exception as e:
            _record(False, f"{wh_name}", f"异常: {e}")

    # Part 2: 门店关联仓库测试 — 门店匹配后 warehouse_code 是否正确
    print()
    print("  [D2] 门店→仓库 关联测试")
    print("  " + "-" * 56)

    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # 取每个货主各 1 个有仓库的门店
    cur.execute("""
        SELECT DISTINCT ON (sl.owner_code)
               sl.store_name, sl.owner_code, sl.warehouse,
               wm.warehouse_code as expected_wh_code
        FROM store_list sl
        JOIN warehouse_code_mapping wm ON wm.warehouse_name = sl.warehouse
        WHERE sl.warehouse IS NOT NULL AND sl.warehouse != ''
          AND sl.owner_code IS NOT NULL AND sl.owner_code != ''
        ORDER BY sl.owner_code, sl.store_name
    """)
    store_wh_samples = cur.fetchall()
    conn.close()

    if not store_wh_samples:
        _record(False, "门店→仓库关联", "无有仓库的门店数据")
        return

    from tools._store_matcher import match_store

    for store_name, owner_code, wh_name, expected_wh_code in store_wh_samples:
        try:
            result = match_store(
                store_name=store_name,
                db_config=db_config,
            )
            if result is None:
                _record(False, f"{store_name[:20]} → 仓库", "match_store 返回 None")
                continue

            actual_wh_code = result.get("warehouse_code", "")
            matched = actual_wh_code == expected_wh_code
            _record(matched,
                    f"{store_name[:20]} → {wh_name} ({expected_wh_code})",
                    f"实际 wh_code={actual_wh_code}")
        except Exception as e:
            _record(False, f"{store_name[:20]} → 仓库", f"异常: {e}")


# ===================== 主函数 =====================

def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("映射准确率回归测试")
    print("=" * 60)

    db_config = _get_db_config()
    if not db_config:
        print("\n⚠️  DB 未配置,跳过所有测试")
        print("   设置 DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD")
        print("   或确保 .env 文件存在")
        sys.exit(2)

    # 验证 DB 连接
    try:
        import psycopg2
        conn = psycopg2.connect(**db_config)
        conn.close()
        print(f"\n✅ DB 连接成功: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    except Exception as e:
        print(f"\n❌ DB 连接失败: {e}")
        sys.exit(2)

    # 执行测试
    try:
        test_store_matching(db_config)
        test_owner_identification(db_config)
        test_unit_mapping(db_config)
    except Exception as e:
        print(f"\n❌ 测试执行异常: {e}")
        traceback.print_exc()
        sys.exit(1)

    # D: 仓库映射准确率
    try:
        test_warehouse_mapping(db_config)
    except Exception as e:
        print(f"\n❌ 仓库映射测试异常: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1

    # 🆕 汇总 + 分组准确率
    total = PASS_COUNT + FAIL_COUNT
    print("\n" + "=" * 60)
    print(f"总计: {total} 个测试, {PASS_COUNT} ✅ 通过, {FAIL_COUNT} ❌ 失败")
    print("=" * 60)

    # 🆕 分组准确率汇总
    print("\n📊 准确率指标汇总:")
    print("-" * 60)
    for group_name, stats in GROUP_STATS.items():
        g_total = stats["pass"] + stats["fail"]
        g_pct = stats["pass"] / g_total * 100 if g_total > 0 else 0
        status = "✅" if stats["fail"] == 0 else "⚠️" if g_pct >= 80 else "❌"
        print(f"  {status} {group_name:12s}: {stats['pass']}/{g_total} ({g_pct:.0f}%)")
    print("-" * 60)

    if FAILURES:
        print("\n失败列表:")
        for name, detail in FAILURES:
            print(f"  ❌ {name} -- {detail}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
