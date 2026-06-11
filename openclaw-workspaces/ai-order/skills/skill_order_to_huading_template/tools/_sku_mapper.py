"""
SKU映射工具 - 按货主ID过滤,匹配商品名,判断单位类型

2026-06-03 优化:
1. map_sku_batch() 批量模式 - 一次 DB 查询处理所有商品(几十到上百ms)
2. SKUCache 类 - 预加载单个货主的 SKU 到内存,Layer 2.5/Layer 3 直接内存匹配
3. 保留了原有的 map_sku() 单次查询接口(兼容备用)
4. 原来的 5 层逻辑不变,只是把 N 次查询变成 1 次

单次调用(保留):
    result = map_sku(owner_code, product_name, unit, db_config)
批量调用(推荐):
    results = map_sku_batch(owner_code, items, db_config)
"""
from typing import Optional, Dict, Any, List, Tuple
from difflib import SequenceMatcher
import re
import psycopg2
import sys
import os

# 允许独立运行(不依赖主入口):将 skill 根目录加入 sys.path
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from db.connection import get_connection, get_default_db_config
from db.table_names import SKU_TABLE, WAREHOUSE_TABLE, ALIAS_TABLE, STORE_TABLE, ACTIVE_STATUS, SKU_CACHE_LIMIT, SKU_MATCH_LIMIT


def _clean_product_name(name: str) -> str:
    """
    清洗订单商品名称:去除括号内容,保留核心商品名

    规则:
    1. 只去除括号及其内容(括号通常是规格/别名描述)
    2. **中间**的连接符(-、-、_)全部保留,因为它们可能是商品名的一部分
    3. 🆕 **开头/末尾**的孤立分隔符会被去除(如 "果糖-", "果糖_", "-果糖")
    4. 例如:
       - 辣白菜D-X-H → 辣白菜D-X-H (中间连接符保留)
       - 鱼你幸福青花椒酱料(新款) → 鱼你幸福青花椒酱料 (去括号)
       - 冻品-鱼你幸福猪肉片(1KG*12包/箱) → 冻品-鱼你幸福猪肉片 (去括号)
       - 果糖- → 果糖 (去末尾孤立-,v5.13.3 修复)
       - 辣白菜D-X-H- → 辣白菜D-X-H (只去末尾-,中间保留)

    修复记录:
    - 2026-06-09: 原逻辑错误去掉了 - 和连接符,导致 Layer 1 精确匹配失败
      例如 辣白菜D-X-H 被洗成 辣白菜DXH,与数据库不匹配
    - 2026-06-11: v5.13.3 金姐反馈 "果糖-" 匹配不到(沧州行别营店),
      根本原因: 清洗函数没考虑 "孤立分隔符" 场景,末尾的 "-" 被原样保留
      修复: 正则用 ^ 和 $ 锚点,只去除开头/末尾的孤立分隔符,中间连接符不动
    """
    # 去除所有括号及其内容（含中文括号（））
    cleaned = re.sub(r'[\uff08(][^)\uff09]*[\uff09)]', '', name)
    # 去除多余空格,但保留连接符(-、-、_)
    cleaned = re.sub(r'\s+', '', cleaned)
    cleaned = cleaned.strip()
    # 🆕 修复 (v5.13.3): 去除末尾的孤立分隔符
    # 原因: 订单中常出现"果糖-"这种带尾部孤立符号的商品名,导致 Layer 1/1b 精确匹配失败
    # 例如 "果糖-" 清洗后应是 "果糖",才能匹配 DB 中的 "果糖/新"
    # 正则 ^ 和 $ 是锚点,只匹配开头/末尾,中间的连接符(如"辣白菜D-X-H")不受影响
    cleaned = re.sub(r'[-_./\\,;:]+$', '', cleaned)
    cleaned = re.sub(r'^[-_./\\,;:]+', '', cleaned)
    return cleaned.strip()


def _extract_spec_from_name(name: str) -> str:
    """
    从订单商品名中提取规格描述

    规则:只提取明确是规格的格式,如"14包*1KG"、"1KG*12包/箱"等
    对于"新款"、"A"等不明确的,不作为规格(规格匹配分数=0.5,不扣分)
    """
    # 匹配明确是规格的格式
    patterns = [
        r'\d+KG\s*[*×]\s*\d+[包袋箱件个条]',  # 如 1KG*12包, 14包*1KG
        r'\d+[包袋箱件个条]\s*[*×]\s*\d+KG',  # 如 14包*1KG
        r'\d+[包袋箱件个条]/\d+[包袋箱件个条]',  # 如 10包/袋, 14包/箱
        r'\d+[包袋箱件个条]\s*[*×]\s*\d+[包袋箱件个条]',  # 如 14包*1
    ]
    for p in patterns:
        m = re.search(p, name, re.IGNORECASE)
        if m:
            return m.group(0)

    # 检查括号内容是否像规格(包含数字和单位) - 支持中英文括号
    match = re.search(r'[\uff08(]([^\uff09)]+)[\uff09)]', name)
    if match:
        content = match.group(1)
        if re.search(r'\d', content) and re.search(r'[包袋箱件个条]', content):
            return content
    return ""


def _spec_match_score(order_spec: str, db_spec: str) -> float:
    """
    计算订单规格与数据库规格的匹配分数

    Returns:
        1.0 - 完全匹配
        0.5-0.9 - 部分匹配(如"14包/箱" vs "箱")
        0.0 - 不匹配
    """
    if not order_spec and not db_spec:
        return 1.0  # 都没规格,当作匹配
    if not order_spec or not db_spec:
        return 0.5  # 一个有规格一个没有

    order_spec_lower = order_spec.lower().strip()
    db_spec_lower = db_spec.lower().strip()

    # 完全匹配
    if order_spec_lower == db_spec_lower:
        return 1.0

    # 提取数字进行比较
    order_nums = re.findall(r'\d+', order_spec_lower)
    db_nums = re.findall(r'\d+', db_spec_lower)

    # 检查单位是否一致
    order_units = re.findall(r'[包袋箱件个条]', order_spec_lower)
    db_units = re.findall(r'[包袋箱件个条]', db_spec_lower)

    # 如果单位不一致,分数降低
    if order_units and db_units and order_units[0] != db_units[0]:
        return 0.3

    # 如果数字匹配度高,分数提高
    if order_nums and db_nums:
        # 14包/箱 vs 14包/箱 → 1.0(完全匹配,精准)
        if order_nums == db_nums and order_units == db_units:
            return 1.0
        # 数字部分相同
        if set(order_nums) == set(db_nums):
            return 0.8

    # 使用字符串相似度
    return SequenceMatcher(None, order_spec_lower, db_spec_lower).ratio()


def _keyword_boost(clean_name: str, sku_name: str) -> float:
    """
    关键词命中时计算置信度加成

    当数据库sku_name包含清洗后的订单商品名时,说明匹配非常精确
    - 清洗后的订单商品名 是 数据库sku_name的子串 → 加成0.25(强匹配)
    - 数据库sku_name 是 清洗后的订单商品名的子串 → 加成0.10
    """
    if clean_name in sku_name:
        return 0.25  # 订单商品名被数据库名称包含,强匹配
    if sku_name in clean_name:
        return 0.10  # 数据库名称是订单商品名的子串
    return 0.0


def _has_core_word_match(clean_name: str, sku_name: str) -> bool:
    """
    核心词校验:判断订单名称和SKU名称是否包含相同的核心词或产品类型

    产品类型:鸡排、片、肠、翅、腿、排等物理形态产品
    调料类型:酱料、酱、粉、膏等风味产品

    规则:
    1. 包含关系:清洗后的订单商品名 与 SKU名称 存在包含关系 → 通过
    2. 核心词关系:去除前缀后的核心词必须互相包含 → 通过
    3. 物理产品类型:两者都包含相同的物理产品类型词(如"鸡排"、"鱼片")→ 通过
    4. 调料类型:如果核心词包含调料类型词,则必须完全相同才能匹配
    """
    import re

    if clean_name in sku_name or sku_name in clean_name:
        return True

    def extract_core(name):
        name = re.sub(r'^[0-9]+[a-zA-Z]*', '', name)
        return name.strip()

    order_core = extract_core(clean_name)
    sku_core = extract_core(sku_name)

    if not order_core or not sku_core:
        return True

    if order_core in sku_core or sku_core in order_core:
        return True

    # 产品类型词:物理形态,不会因口味不同而改变
    product_types = ['鸡排', '片', '肠', '翅', '腿', '排', '羊排', '牛排', '蟹', '虾', '鱼', '肉', '丸子']

    flavor_types = ['酱料', '粉', '膏']

    # 如果核心词包含调料类型词,只比较核心词是否完全相同
    order_is_flavor = any(t in order_core for t in flavor_types)
    sku_is_flavor = any(t in sku_core for t in flavor_types)

    if order_is_flavor or sku_is_flavor:
        return order_core == sku_core

    # 产品类型词匹配
    order_types = [t for t in product_types if t in order_core]
    sku_types = [t for t in product_types if t in sku_core]

    if order_types and sku_types:
        if any(t in sku_types for t in order_types):
            return True

    return False


# ===================== v5.14.0 新增: 选 SKU 时的统一打分 + 唯一性判断 =====================


def _compute_match_score(name_score: float, spec_score: float, keyword_boost: float,
                          order_unit: str, sku_unit: str,
                          order_spec: str, db_spec: str,
                          layer: str) -> float:
    """
    v5.14.0 新增: 统一计算 SKU 匹配分数

    加成:
      - order_unit == sku_unit → +0.20 (单位精确命中)
      - order_spec == db_spec → +0.10 (规格精确命中)

    Args:
        name_score: 名称相似度 (0-1)
        spec_score: 规格匹配分 (0-1)
        keyword_boost: 关键词加成 (0-0.25)
        order_unit: 订单单位（如"桶""件""瓶"）
        sku_unit: DB SKU 的 unit 字段
        order_spec: 订单中的规格描述
        db_spec: DB SKU 的 product_spec 字段
        layer: 哪一层 ("L2" / "L25" / "L3")

    Returns:
        float: 综合分数, cap 在 1.0
    """
    # 基础权重 (按 layer 调)
    weights = {
        "L2":  {"name": 0.50, "spec": 0.20, "kb": 0.00},
        "L25": {"name": 0.45, "spec": 0.20, "kb": 0.10},
        "L3":  {"name": 0.45, "spec": 0.20, "kb": 0.10},
    }
    w = weights.get(layer, weights["L3"])
    ts = (name_score * w["name"]
          + spec_score * w["spec"]
          + keyword_boost * w["kb"])

    # 🆕 单位命中加成 (所有层通用, v5.14.0)
    if order_unit and sku_unit and order_unit == sku_unit:
        ts += 0.20

    # 🆕 规格精确命中加成
    if order_spec and db_spec and order_spec == db_spec:
        ts += 0.10

    return min(1.0, ts)


def _select_unique_best(scored: list, threshold: float = 0.001) -> tuple:
    """
    v5.14.0 新增: 从打分结果中选唯一最高分候选

    Args:
        scored: list of (total_score, name_score, spec_score, kb, row) 元组
        threshold: 判定"并列"的分数差阈值

    Returns:
        (best_row, need_confirm, candidates)
        - best_row: 唯一最高分的 row
        - need_confirm: True 表示有并列或多个候选
        - candidates: 多个候选时返回所有 row
    """
    if not scored:
        return (None, False, [])

    sorted_scored = sorted(scored, key=lambda x: x[0], reverse=True)
    best_score = sorted_scored[0][0]

    # 找所有"近似最高分"的候选 (差<threshold)
    tied = [s for s in sorted_scored if abs(s[0] - best_score) < threshold]

    if len(tied) == 1:
        # 唯一最高分
        return (tied[0][-1], False, [])
    else:
        # 多个并列最高
        return (tied[0][-1], True, [t[-1] for t in tied])


def _build_with_candidates(rows: list, confidence: float,
                            original_product_name: str = "",
                            match_method: str = "") -> dict:
    """
    v5.14.0 新增: 构造多个候选结果 (复用 v5.13.2 的 candidates 机制)
    """
    if not rows:
        return {
            "matched": False, "confidence": 0.0, "sku_code": "",
            "sku_name": "", "unit": "", "unit_type": "",
            "conversion_ratio": 1.0, "product_spec": "",
            "match_method": match_method or "未匹配",
        }
    r = rows[0]
    result = _build_result(r, confidence=confidence, original_product_name=original_product_name)
    result["match_method"] = match_method
    if len(rows) > 1:
        # 把所有 rows 都放进 candidates (rows[0] 也包进去, 跟 v5.13.2 一致)
        result["candidates"] = [_build_result(rr, confidence=confidence) for rr in rows]
        result["need_confirm"] = True
    return result


def _resolve_unit_type(rows: list, order_quantity: float = 1, order_unit: str = "") -> tuple:
    """
    根据订单单位精确匹配选择出库单位(v5.13.0)

    规则:
    1. 订单单位与 SKU.unit 精确匹配 → 选中该 SKU
    2. 匹配不上 → 直接用第一个 SKU(它自带 unit_type)
    3. 多个同 unit 候选 → need_confirm

    Args:
        rows: 同名商品的 SKU 记录列表 (sku_code, sku_name, unit, unit_type, conversion_ratio, ...)
        order_quantity: 订单数量(保留参数兼容,不再使用)
        order_unit: 订单单位(如"件""包""袋""瓶")

    Returns:
        (selected_row, need_confirm, all_candidates)
    """
    if not rows:
        return (None, False, [])
    if len(rows) == 1:
        return (rows[0], False, rows)

    # 订单单位精确匹配
    if order_unit:
        unit_matches = [r for r in rows if r[2] == order_unit]
        if len(unit_matches) == 1:
            return (unit_matches[0], False, rows)
        elif len(unit_matches) > 1:
            return (unit_matches[0], True, rows)

    # 匹配不上 → 直接用第一个 SKU(自带 unit_type)
    return (rows[0], False, rows)


def map_sku(owner_code: str, product_name: str, unit: str = "",
            order_quantity: float = 1,
            db_config: Optional[dict] = None) -> dict:
    """
    SKU映射 - 委托给 map_sku_batch 保持逻辑一致(v5.13.0)

    Args:
        owner_code: 货主ID
        product_name: 商品名称
        unit: 订单单位
        order_quantity: 订单数量
        db_config: 数据库配置
    """
    items = [{
        "product_name": product_name,
        "spec": "",
        "unit": unit or "件",
        "quantity": order_quantity,
        "seq": 1,
    }]
    results, unmatched = map_sku_batch(owner_code, items, db_config)
    if results:
        return results[0]
    return {
        "matched": False, "confidence": 0.0, "sku_code": "",
        "sku_name": product_name, "unit_type": "", "conversion_ratio": 1.0,
        "product_spec": "", "unit": unit or "件", "match_method": "未匹配",
    }


def _map_sku_legacy(owner_code: str, product_name: str, unit: str = "",
                    order_quantity: float = 1,
                    db_config: Optional[dict] = None) -> dict:
    """[已废弃] 原始 map_sku 实现 - 保留供参考,不再调用"""
    if db_config is None:
        db_config = get_default_db_config()

    # 预处理:去除各种空白字符
    import re
    def clean_name_text(name):
        if not name:
            return ""
        name = str(name)
        name = name.strip()
        name = re.sub(r'[\t\u00a0\u3000\u200b\u200f\ufeff]+', '', name)  # 保留连接符 -
        name = name.replace(' ', '')
        return name

    product_name = clean_name_text(product_name)
    unit = clean_name_text(unit) if unit else ""

    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # 提取并保存原始规格
    order_spec = _extract_spec_from_name(product_name)

    # 清洗商品名(去除规格描述)
    clean_name = _clean_product_name(product_name)

    # ========== Layer 0: 别名表查表 ==========
    cur.execute(f"""
        SELECT p.sku_code, p.sku_name, p.unit, p.unit_type, p.conversion_ratio, p.product_spec, p.customer_code
        FROM {ALIAS_TABLE} a
        JOIN {SKU_TABLE} p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
        WHERE a.shipper_id = %s AND a.order_product_name = %s
    """, (owner_code, product_name))
    alias_rows = cur.fetchall()
    if alias_rows:
        r = alias_rows[0]  # 临时取第一个,单位选择后置
        conn.close()
        result = _build_result(r, confidence=0.98, original_product_name=product_name)
        result["match_method"] = "Layer 0 别名表精确匹配"
        return result

    # ========== Layer 1: 精确匹配(原始名称) ==========
    cur.execute(f"""
        SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
        FROM {SKU_TABLE}
        WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
          AND (sku_name = %s OR customer_code = %s)
    """, (owner_code, product_name, product_name))
    rows = cur.fetchall()
    if rows:
        r = rows[0]  # 临时取第一个,单位选择后置
        conn.close()
        result = _build_result(r, confidence=0.95, original_product_name=product_name)
        result["match_method"] = "Layer 1 精确匹配"
        return result

    # ========== Layer 1b: 精确匹配(清洗后名称) ==========
    if clean_name != product_name:
        cur.execute(f"""
            SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
            FROM {SKU_TABLE}
            WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
              AND (sku_name = %s OR customer_code = %s)
        """, (owner_code, clean_name, clean_name))
        rows = cur.fetchall()
        if rows:
            # 如果有规格,先按规格筛选缩小范围
            if order_spec and len(rows) > 1:
                spec_candidates = []
                for row in rows:
                    spec_score = _spec_match_score(order_spec, row[5] or "")
                    if spec_score >= 0.5:
                        spec_candidates.append(row)
                if spec_candidates:
                    rows = spec_candidates  # 规格匹配的子集
            r = rows[0]  # 临时取第一个,单位选择后置
            conn.close()
            result = _build_result(r, confidence=0.93, original_product_name=product_name)
            result["match_method"] = "Layer 1b 精确匹配(去除规格后)"
            return result

    # ========== Layer 2: 模糊匹配(清洗后名称) ==========
    if clean_name != product_name:
        cur.execute(f"""
            SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
            FROM {SKU_TABLE}
            WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
              AND sku_name LIKE %s
        """, (owner_code, f"%{clean_name}%"))
        rows = cur.fetchall()
        if rows:
            scored = []
            for r in rows:
                name_score = SequenceMatcher(None, clean_name, r[1]).ratio()
                spec_score = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
                # 综合分数 = 名称相似度 * 0.6 + 规格匹配 * 0.4
                total_score = name_score * 0.6 + spec_score * 0.4
                scored.append((total_score, name_score, spec_score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            total_score, name_score, spec_score, best = scored[0]
            if total_score >= 0.8:
                conn.close()
                result = _build_result(best, confidence=round(total_score, 2), original_product_name=product_name)
                result["match_method"] = f"Layer 2 模糊匹配+规格校验(名称{int(name_score*100)}%+规格{int(spec_score*100)}%)"
                result["need_confirm"] = False
                return result
            elif total_score >= 0.6:
                conn.close()
                result = _build_result(best, confidence=round(total_score, 2), original_product_name=product_name)
                result["match_method"] = f"Layer 2 模糊匹配+规格校验(置信度低,需确认)名称{int(name_score*100)}%+规格{int(spec_score*100)}%)"
                result["need_confirm"] = True
                return result

    # ========== Layer 2.5: 全量相似度匹配(始终执行,当Layer 2无结果时兜底) ==========
    cur.execute(f"SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code FROM {SKU_TABLE} WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}' LIMIT {SKU_CACHE_LIMIT}", (owner_code,))
    all_skus = cur.fetchall()
    if all_skus:
        scored = []
        for r in all_skus:
            sku_name = r[1]
            name_score = SequenceMatcher(None, clean_name, sku_name).ratio()

            # 新增:核心词校验 - 订单清洗后名称和SKU名称必须互相包含核心词
            # 例如:"鱼你幸福金汤酱料" 必须包含 "金汤",SKU "鱼你幸福番茄酱料" 必须包含 "金汤"
            if not _has_core_word_match(clean_name, sku_name):
                continue  # 核心词不匹配,跳过此候选

            # 规格匹配分数
            spec_score = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5

            # 高相似度时额外加权:当名称相似度>=0.7时,boost=0.25
            keyword_boost = _keyword_boost(clean_name, sku_name)
            if name_score >= 0.7:
                keyword_boost = max(keyword_boost, 0.25)

            # 综合分数 = 名称 * 0.5 + 规格 * 0.3 + 加成 * 0.2
            total_score = name_score * 0.5 + spec_score * 0.3 + keyword_boost * 0.2
            scored.append((total_score, name_score, spec_score, keyword_boost, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            total_score, name_score, spec_score, keyword_boost, best = scored[0]
            if total_score >= 0.7:
                conn.close()
                result = _build_result(best, confidence=min(0.85, round(total_score, 2)), original_product_name=product_name)
                result["match_method"] = f"Layer 2.5 相似度匹配(名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%)"
                result["need_confirm"] = total_score < 0.8
                return result

    # ========== Layer 3: 分词关键词匹配 ==========
    keywords = []
    for l in [5, 4, 3, 2]:
        if len(clean_name) >= l:
            keywords.append(clean_name[:l])
            if len(clean_name) > l:
                keywords.append(clean_name[-l:])

    all_matches = []
    for keyword in keywords:
        cur.execute(f"SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code FROM {SKU_TABLE} WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}' AND sku_name LIKE %s LIMIT {SKU_MATCH_LIMIT}", (owner_code, f"%{keyword}%"))
        rows = cur.fetchall()
        for r in rows:
            # 核心词校验 - 排除不同口味调料的错误匹配
            if not _has_core_word_match(clean_name, r[1]):
                continue
            name_score = SequenceMatcher(None, clean_name, r[1]).ratio()
            spec_score = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
            keyword_boost = _keyword_boost(clean_name, r[1])
            total_score = name_score * 0.5 + spec_score * 0.4 + keyword_boost
            all_matches.append((total_score, name_score, spec_score, keyword_boost, r))

    if all_matches:
        all_matches.sort(key=lambda x: x[0], reverse=True)
        total_score, name_score, spec_score, keyword_boost, best = all_matches[0]

        # Fallback:当分数略低(0.55-0.6)但名称相似度>=0.7时,加boost后允许通过
        if 0.55 <= total_score < 0.6 and name_score >= 0.7:
            keyword_boost = max(keyword_boost, 0.2)
            total_score = min(0.79, total_score + keyword_boost)

        if total_score >= 0.8:
            conn.close()
            result = _build_result(best, confidence=min(0.88, round(total_score, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配(名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%)"
            result["need_confirm"] = False
            return result
        elif total_score >= 0.6:
            conn.close()
            result = _build_result(best, confidence=min(0.88, round(total_score, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配(置信度低,需确认)名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%)"
            result["need_confirm"] = True
            return result
        elif 0.55 <= total_score < 0.6 and name_score >= 0.7:
            # Fallback:分数在0.55-0.6之间,名称相似度>=0.7时,加boost后允许通过
            conn.close()
            result = _build_result(best, confidence=min(0.79, round(total_score + 0.2, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配(Fallback加成)名称{int(name_score*100)}%+加成20%)"
            result["need_confirm"] = True
            return result

    conn.close()
    return {
        "matched": False,
        "confidence": 0.0,
        "sku_code": "",
        "sku_name": product_name,
        "unit_type": "",
        "conversion_ratio": 1.0,
        "product_spec": "",
        "unit": unit or "件",
        "match_method": "未匹配",
    }


def _build_result(row: tuple, confidence: float, original_product_name: str = "") -> dict:
    """构建SKU映射结果(通用)"""
    return {
        "matched": True,
        "confidence": confidence,
        "sku_code": row[0],
        "sku_name": row[1],
        "unit": row[2],
        "unit_type": row[3],
        "conversion_ratio": float(row[4]),
        "product_spec": row[5] or "",
        "unit_original": row[2],
        "original_product_name": original_product_name,
        "product_name": original_product_name,
    }


# ============================ 批量优化(2026-06-03)============================


class SKUCache:
    """
    单个货主的 SKU 缓存,批量处理时使用

    在 map_sku_batch() 调用前预加载,一次 DB 查询获取该货主所有活跃 SKU,
    后续 Layer 2.5 / Layer 3 都在内存做相似度匹配,不再查 DB。
    """

    def __init__(self, owner_code: str, db_config: dict):
        self.owner_code = owner_code
        self.db_config = db_config
        self._loaded = False
        self._rows = []  # list of (sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code)

    def load(self) -> "SKUCache":
        """一次 DB 查询加载所有 SKU"""
        if self._loaded:
            return self
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute(f"""
            SELECT sku_code, sku_name, unit, unit_type,
                   conversion_ratio, product_spec, customer_code
            FROM {SKU_TABLE}
            WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
        """, (self.owner_code,))
        self._rows = cur.fetchall()
        conn.close()
        self._loaded = True
        return self

    def rows(self) -> List[Tuple]:
        return self._rows

    def find_by_name(self, name: str) -> List[Tuple]:
        """按 sku_name 模糊查询(用于 Layer 2/3 LIKE 查询)"""
        return [r for r in self._rows if name in r[1]]

    def find_by_keyword(self, keyword: str) -> List[Tuple]:
        """按关键词 LIKE 查询(用于 Layer 3)"""
        return [r for r in self._rows if keyword in r[1]]


def map_sku_batch(owner_code: str, items: List[Dict],
                 db_config: Optional[dict] = None) -> Tuple[List[Dict], List[Dict]]:
    """
    SKU批量映射 - 推荐使用,大幅提升多商品订单的处理速度

    策略:
    1. 一次 DB 查询获取该货主所有活跃 SKU(Layer 2.5 / Layer 3 在内存做)
    2. Layer 0(别名表)仍然查 DB,但只有一次
    3. Layer 1 / 1b 在内存做(精确匹配)
    4. Layer 2 / 2.5 / 3 在内存做(模糊匹配)

    Args:
        owner_code: 货主ID
        items: list of {product_name, spec, unit, seq}
        db_config: 数据库配置

    Returns:
        (results, unmatched_items) - 与 map_sku() 返回格式兼容
    """
    if db_config is None:
        db_config = get_default_db_config()

    # 预处理
    def clean_name_text(name):
        if not name:
            return ""
        name = str(name).strip()
        name = re.sub(r'[\t\u00a0\u3000\u200b\u200f\ufeff]+', '', name)  # 保留连接符 -
        name = name.replace(' ', '')
        return name

    # 预加载 SKU 缓存(一次 DB 查询)
    cache = SKUCache(owner_code, db_config).load()
    all_skus = cache.rows()

    # 加载别名表(一次 DB 查询)- v5.12.0 改为支持同名多SKU
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT a.order_product_name, p.sku_code, p.sku_name, p.unit, p.unit_type,
               p.conversion_ratio, p.product_spec, p.customer_code
        FROM {ALIAS_TABLE} a
        JOIN {SKU_TABLE} p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
        WHERE a.shipper_id = %s
    """, (owner_code,))
    alias_groups = {}  # order_product_name -> list of (sku_code, sku_name, ...)
    for r in cur.fetchall():
        alias_groups.setdefault(r[0], []).append(r[1:])
    conn.close()

    results = []
    unmatched_items = []

    for item in items:
        product_name = item.get("product_name", "")
        spec = item.get("spec", "")
        unit = item.get("unit", "件")
        seq = item.get("seq", 0)
        quantity = item.get("quantity", 0)

        result = _map_single_in_batch(
            owner_code, clean_name_text(product_name),
            spec, unit, quantity, db_config, cache, alias_groups, all_skus,
            clean_name_text, _extract_spec_from_name, _clean_product_name,
            _spec_match_score, _keyword_boost, _has_core_word_match
        )

        if result["matched"]:
            # 透传订单原始信息（v5.13.2：多候选已在 result["candidates"] 中，用户选 SKU 即选单位）
            result["quantity"] = quantity
            result["order_unit"] = unit  # 订单原始单位
            result["spec"] = spec
            result["seq"] = seq
            results.append(result)
        else:
            unmatched_items.append({
                "seq": seq, "product_name": product_name,
                "spec": spec, "quantity": quantity, "unit": unit})

    return results, unmatched_items


def _map_single_in_batch(owner_code, product_name, spec, unit, quantity,
                         db_config, cache, alias_groups, all_skus,
                         clean_name_text, _extract_spec_from_name,
                         _clean_product_name, _spec_match_score,
                         _keyword_boost, _has_core_word_match) -> dict:
    """单商品在批量模式下的匹配逻辑(内存计算)"""

    order_spec = _extract_spec_from_name(product_name)
    clean_name = _clean_product_name(product_name)

    # Layer 0: 别名表（v5.13.2：多候选时返回 candidates 让用户选）
    if product_name in alias_groups:
        candidate_rows = alias_groups[product_name]
        r = candidate_rows[0]
        result = _build_result(r, confidence=0.98, original_product_name=product_name)
        result["match_method"] = "Layer 0 别名表精确匹配"
        if len(candidate_rows) > 1:
            result["candidates"] = [_build_result(cr, confidence=0.98) for cr in candidate_rows]
            result["need_confirm"] = True
        return result

    # Layer 1: 精确匹配（v5.14.0：多候选时按 order_unit 选, 唯一命中不返 candidates）
    exact_matches = [r for r in all_skus if r[1] == product_name or r[6] == product_name]
    if exact_matches:
        # 1. 单候选 → 直接返回
        if len(exact_matches) == 1:
            r = exact_matches[0]
            result = _build_result(r, confidence=0.95, original_product_name=product_name)
            result["match_method"] = "Layer 1 精确匹配"
            return result
        # 2. 多候选 → 按 order_unit 选
        if unit:
            unit_matches = [m for m in exact_matches if m[2] == unit]
            if len(unit_matches) == 1:
                r = unit_matches[0]
                result = _build_result(r, confidence=0.95, original_product_name=product_name)
                result["match_method"] = f"Layer 1 精确匹配 (单位命中: {unit})"
                return result
            elif len(unit_matches) > 1:
                # 多候选同 unit, 返回 candidates
                return _build_with_candidates(
                    unit_matches, confidence=0.95,
                    original_product_name=product_name,
                    match_method=f"Layer 1 精确匹配 (多 SKU 同单位: {unit})")
            # else: order_unit 没匹配到任何 SKU, fallthrough 到 "无 order_unit" 逻辑
        # 3. 无 order_unit 或 unit 没匹配 → 返回 candidates
        return _build_with_candidates(
            exact_matches, confidence=0.95,
            original_product_name=product_name,
            match_method="Layer 1 精确匹配 (多候选待选)")

    # Layer 1b: 清洗后精确匹配（v5.14.0：多候选时按 order_unit 选, 唯一命中不返 candidates）
    if clean_name != product_name:
        clean_matches = [r for r in all_skus if r[1] == clean_name or r[6] == clean_name]
        if clean_matches:
            if order_spec and len(clean_matches) > 1:
                spec_candidates = [r for r in clean_matches if _spec_match_score(order_spec, r[5] or "") >= 0.5]
                if spec_candidates:
                    clean_matches = spec_candidates
            # 1. 单候选 → 直接返回
            if len(clean_matches) == 1:
                r = clean_matches[0]
                result = _build_result(r, confidence=0.93, original_product_name=product_name)
                result["match_method"] = "Layer 1b 精确匹配（去除规格后）"
                return result
            # 2. 多候选 → 按 order_unit 选
            if unit:
                unit_matches = [m for m in clean_matches if m[2] == unit]
                if len(unit_matches) == 1:
                    r = unit_matches[0]
                    result = _build_result(r, confidence=0.93, original_product_name=product_name)
                    result["match_method"] = f"Layer 1b 精确匹配 (单位命中: {unit})"
                    return result
                elif len(unit_matches) > 1:
                    return _build_with_candidates(
                        unit_matches, confidence=0.93,
                        original_product_name=product_name,
                        match_method=f"Layer 1b 精确匹配 (多 SKU 同单位: {unit})")
            # 3. 无 order_unit 或 unit 没匹配 → 返回 candidates
            return _build_with_candidates(
                clean_matches, confidence=0.93,
                original_product_name=product_name,
                match_method="Layer 1b 精确匹配 (多候选待选)")

    # Layer 2: 模糊匹配（v5.14.0：用 _compute_match_score + _select_unique_best）
    # 取消 `if clean_name != product_name` 限制 (v5.14.0 修复)
    # 原限制导致 clean_name=果糖,product_name=果糖时 Layer 2 跳过,但 DB 里 SKU 叫"果糖/新"
    # 这种 "名字部分包含" 场景必须走 Layer 2 才能匹配
    candidates = cache.find_by_name(clean_name)
    if candidates:
        scored = []
        for r in candidates:
            ns = SequenceMatcher(None, clean_name, r[1]).ratio()
            ss = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
            kb = 0.0  # Layer 2 不算 keyword_boost
            ts = _compute_match_score(ns, ss, kb,
                                       order_unit=unit, sku_unit=r[2],
                                       order_spec=order_spec, db_spec=r[5] or "",
                                       layer="L2")
            scored.append((ts, ns, ss, kb, r))
        # 排序后取 best (v5.14.0: 排序后用 sorted[0] 拿 ts, 不是 scored[0])
        scored.sort(key=lambda x: x[0], reverse=True)
        best_row, need_confirm, tied_rows = _select_unique_best(scored)
        if best_row is not None:
            ts, ns, ss, kb, _ = scored[0]  # sorted 后的第一个 = 最高分
            if need_confirm:
                if ts >= 0.6 or ns >= 0.7:
                    return _build_with_candidates(
                        tied_rows, confidence=round(ts, 2),
                        original_product_name=product_name,
                        match_method=f"Layer 2 模糊匹配 (多候选并列,名称{int(ns*100)}%+规格{int(ss*100)}%)")
                # 阈值不够，继续找下一层
            else:
                # 唯一命中,按阈值判定
                if ts >= 0.8:
                    result = _build_result(best_row, confidence=round(ts, 2), original_product_name=product_name)
                    result["match_method"] = f"Layer 2 模糊匹配(名称{int(ns*100)}%+规格{int(ss*100)}%+单位加成)"
                    return result
                elif ts >= 0.6:
                    result = _build_result(best_row, confidence=round(ts, 2), original_product_name=product_name)
                    result["match_method"] = f"Layer 2 模糊匹配(需确认)名称{int(ns*100)}%+规格{int(ss*100)}%+单位加成)"
                    result["need_confirm"] = True
                    return result

    # Layer 2.5: 全量相似度匹配(内存)（v5.14.0：用新公式）
    scored = []
    for r in all_skus:
        sku_name = r[1]
        ns = SequenceMatcher(None, clean_name, sku_name).ratio()
        if ns < 0.5:
            continue
        if not _has_core_word_match(clean_name, sku_name):
            continue
        ss = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
        kb = _keyword_boost(clean_name, sku_name)
        if ns >= 0.7:
            kb = max(kb, 0.25)
        ts = _compute_match_score(ns, ss, kb,
                                   order_unit=unit, sku_unit=r[2],
                                   order_spec=order_spec, db_spec=r[5] or "",
                                   layer="L25")
        scored.append((ts, ns, ss, kb, r))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_row, need_confirm, tied_rows = _select_unique_best(scored)
        if best_row is not None:
            ts, ns, ss, kb, _ = scored[0]
            if need_confirm:
                if ts >= 0.7 or ns >= 0.7:
                    return _build_with_candidates(
                        tied_rows, confidence=min(0.85, round(ts, 2)),
                        original_product_name=product_name,
                        match_method=f"Layer 2.5 相似度匹配 (多候选并列)")
                # 阈值不够，继续找下一层
            elif ts >= 0.7:
                result = _build_result(best_row, confidence=min(0.85, round(ts, 2)), original_product_name=product_name)
                result["match_method"] = f"Layer 2.5 相似度匹配(名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%+单位加成)"
                result["need_confirm"] = ts < 0.8
                return result

    # Layer 3: 分词关键词匹配(内存)（v5.14.0：用新公式）
    keywords = []
    for l in [5, 4, 3, 2]:
        if len(clean_name) >= l:
            keywords.append(clean_name[:l])
            if len(clean_name) > l:
                keywords.append(clean_name[-l:])

    all_matches = []
    seen = set()
    for kw in keywords:
        for r in cache.find_by_keyword(kw):
            if r[0] in seen:
                continue
            seen.add(r[0])
            if not _has_core_word_match(clean_name, r[1]):
                continue
            ns = SequenceMatcher(None, clean_name, r[1]).ratio()
            ss = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
            kb = _keyword_boost(clean_name, r[1])
            ts = _compute_match_score(ns, ss, kb,
                                       order_unit=unit, sku_unit=r[2],
                                       order_spec=order_spec, db_spec=r[5] or "",
                                       layer="L3")
            all_matches.append((ts, ns, ss, kb, r))

    if all_matches:
        all_matches.sort(key=lambda x: x[0], reverse=True)
        best_row, need_confirm, tied_rows = _select_unique_best(all_matches)
        if best_row is not None:
            ts, ns, ss, kb, _ = all_matches[0]
            # Layer 3 Fallback: 0.55-0.6 + name>=0.7 → +0.2 boost
            if 0.55 <= ts < 0.6 and ns >= 0.7:
                kb = max(kb, 0.2)
                ts = min(0.79, ts + kb * 0.0)  # 公式已含 kb, 这里只补一点
            if need_confirm:
                if ts >= 0.6 or ns >= 0.7:
                    return _build_with_candidates(
                        tied_rows, confidence=min(0.88, round(ts, 2)),
                        original_product_name=product_name,
                        match_method=f"Layer 3 分词匹配 (多候选并列)")
                # 阈值不够，继续找下一层
            elif ts >= 0.8:
                result = _build_result(best_row, confidence=min(0.88, round(ts, 2)), original_product_name=product_name)
                result["match_method"] = f"Layer 3 分词匹配(名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%+单位加成)"
                return result
            elif ts >= 0.6:
                result = _build_result(best_row, confidence=min(0.88, round(ts, 2)), original_product_name=product_name)
                result["match_method"] = f"Layer 3 分词匹配(需确认)名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%+单位加成)"
                result["need_confirm"] = True
                return result
            elif 0.55 <= ts < 0.6 and ns >= 0.7:
                result = _build_result(best_row, confidence=min(0.79, round(ts + 0.2, 2)), original_product_name=product_name)
                result["match_method"] = f"Layer 3 分词匹配(Fallback加成)名称{int(ns*100)}%+加成20%)"
                result["need_confirm"] = True
                return result

    return {
        "matched": False, "confidence": 0.0, "sku_code": "",
        "sku_name": product_name, "unit_type": "", "conversion_ratio": 1.0,
        "product_spec": "", "unit": unit or "件", "match_method": "未匹配",
    }


# ============================ 以下为原有的单次查询接口 ==================================


    """构建SKU映射结果"""
    return {
        "matched": True,
        "confidence": confidence,
        "sku_code": row[0],
        "sku_name": row[1],
        "unit": row[2],
        "unit_type": row[3],
        "conversion_ratio": float(row[4]) if row[4] else 1.0,
        "product_spec": row[5] or "",
        "customer_code": row[6] or "",
        "match_method": "",
    }
