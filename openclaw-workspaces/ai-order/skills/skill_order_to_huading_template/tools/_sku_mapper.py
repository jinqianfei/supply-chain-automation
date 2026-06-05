"""
SKU映射工具 - 按货主ID过滤，匹配商品名，判断单位类型

2026-06-03 优化：
1. map_sku_batch() 批量模式 — 一次 DB 查询处理所有商品（几十到上百ms）
2. SKUCache 类 — 预加载单个货主的 SKU 到内存，Layer 2.5/Layer 3 直接内存匹配
3. 保留了原有的 map_sku() 单次查询接口（兼容备用）
4. 原来的 5 层逻辑不变，只是把 N 次查询变成 1 次

单次调用（保留）：
    result = map_sku(owner_code, product_name, unit, db_config)
批量调用（推荐）：
    results = map_sku_batch(owner_code, items, db_config)
"""
from typing import Optional, Dict, Any, List, Tuple
from difflib import SequenceMatcher
import re
import psycopg2


def _clean_product_name(name: str) -> str:
    """
    清洗订单商品名称：去除规格描述，保留核心商品名
    
    规则：
    1. 如果"—"在括号内容之后，去除"—"后的别名后缀
       例如：鱼你幸福青花椒酱料（新款）—原椒麻酱料 → 鱼你幸福青花椒酱料
    2. 如果"—"在括号内容之前或没有括号，则保留（它是产品名的一部分）
       例如：冻品—鱼你幸福猪肉片（1KG*12包/箱） → 冻品鱼你幸福猪肉片
    3. 去除所有括号及其内容
    """
    original_name = name
    
    # 提取括号内容
    bracket_match = re.search(r'[（(]([^)）]+)[)）]', name)
    bracket_content = bracket_match.group(1) if bracket_match else ""
    
    # 找到括号内容的位置
    bracket_pos = -1
    if bracket_content:
        bracket_pos = name.find(f'（{bracket_content}）')
        if bracket_pos == -1:
            bracket_pos = name.find(f'({bracket_content})')
    
    # 如果有括号，且括号后有"—"，去除"—"及之后的内容
    if bracket_content and bracket_pos >= 0:
        after_bracket = name[bracket_pos + len(bracket_content) + 2:]
        if after_bracket and re.match(r'^[—–\-]', after_bracket):
            name = name[:bracket_pos + len(bracket_content) + 2]
    
    # 去除所有括号及其内容
    cleaned = re.sub(r'[（(][^)）]*[)）]', '', name)
    
    # 去除多余的空格和连接符
    cleaned = re.sub(r'[\s\-—–]+', '', cleaned)
    
    return cleaned.strip()


def _extract_spec_from_name(name: str) -> str:
    """
    从订单商品名中提取规格描述
    
    规则：只提取明确是规格的格式，如"14包*1KG"、"1KG*12包/箱"等
    对于"新款"、"A"等不明确的，不作为规格（规格匹配分数=0.5，不扣分）
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
    
    # 检查括号内容是否像规格（包含数字和单位）
    match = re.search(r'[（(]([^)）]+)[)）]', name)
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
        0.5-0.9 - 部分匹配（如"14包/箱" vs "箱"）
        0.0 - 不匹配
    """
    if not order_spec and not db_spec:
        return 1.0  # 都没规格，当作匹配
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
    
    # 如果单位不一致，分数降低
    if order_units and db_units and order_units[0] != db_units[0]:
        return 0.3
    
    # 如果数字匹配度高，分数提高
    if order_nums and db_nums:
        # 14包/箱 vs 14包/箱 → 1.0（完全匹配，精准）
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
    
    当数据库sku_name包含清洗后的订单商品名时，说明匹配非常精确
    - 清洗后的订单商品名 是 数据库sku_name的子串 → 加成0.25（强匹配）
    - 数据库sku_name 是 清洗后的订单商品名的子串 → 加成0.10
    """
    if clean_name in sku_name:
        return 0.25  # 订单商品名被数据库名称包含，强匹配
    if sku_name in clean_name:
        return 0.10  # 数据库名称是订单商品名的子串
    return 0.0


def _has_core_word_match(clean_name: str, sku_name: str) -> bool:
    """
    核心词校验：判断订单名称和SKU名称是否包含相同的核心词或产品类型
    
    产品类型：鸡排、片、肠、翅、腿、排等物理形态产品
    调料类型：酱料、酱、粉、膏等风味产品
    
    规则：
    1. 包含关系：清洗后的订单商品名 与 SKU名称 存在包含关系 → 通过
    2. 核心词关系：去除前缀后的核心词必须互相包含 → 通过
    3. 物理产品类型：两者都包含相同的物理产品类型词（如"鸡排"、"鱼片"）→ 通过
    4. 调料类型：如果核心词包含调料类型词，则必须完全相同才能匹配
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
    
    # 产品类型词：物理形态，不会因口味不同而改变
    product_types = ['鸡排', '片', '肠', '翅', '腿', '排', '羊排', '牛排', '蟹', '虾', '鱼', '肉', '丸子']
    
    flavor_types = ['酱料', '粉', '膏']
    
    # 如果核心词包含调料类型词，只比较核心词是否完全相同
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


def map_sku(owner_code: str, product_name: str, unit: str = "",
            db_config: Optional[dict] = None) -> dict:
    """
    SKU映射 - 5层匹配策略，查 product_sku 表，按 shipper_id 过滤
    
    Layer 0: 别名表查表（完整订单商品名精确匹配）
    Layer 1: 精确匹配（sku_name 或 customer_code 完全一致）
    Layer 2: 模糊匹配 + 规格校验（去除规格描述后匹配，再验证规格）
    Layer 3: 分词关键词匹配 + 规格校验 + 包含关系加成
    
    Args:
        owner_code: 货主ID
        product_name: 商品名称（可能包含规格描述）
        unit: 原始单位（可选，用于 unit_type 判断）
        db_config: 数据库配置
    
    Returns:
        {
            "matched": True/False,
            "confidence": float,
            "sku_code": str,
            "sku_name": str,
            "unit_type": "大单位"/"小单位",
            "conversion_ratio": float,
            "product_spec": str,
            "unit": str,
            "match_method": str,  # 新增：匹配方式说明
        }
    """
    if db_config is None:
        db_config = {"host": "localhost", "port": 5432, "database": "neo", "user": "jinqianfei"}
    
    # 预处理：去除各种空白字符
    import re
    def clean_name_text(name):
        if not name:
            return ""
        name = str(name)
        name = name.strip()
        name = re.sub(r'[\t\u00a0\u3000\u200b\-\u200f\ufeff]+', '', name)
        name = name.replace(' ', '')
        return name
    
    product_name = clean_name_text(product_name)
    unit = clean_name_text(unit) if unit else ""
    
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    
    # 提取并保存原始规格
    order_spec = _extract_spec_from_name(product_name)
    
    # 清洗商品名（去除规格描述）
    clean_name = _clean_product_name(product_name)
    
    # ========== Layer 0: 别名表查表 ==========
    cur.execute("""
        SELECT p.sku_code, p.sku_name, p.unit, p.unit_type, p.conversion_ratio, p.product_spec, p.customer_code
        FROM product_name_alias a
        JOIN product_sku p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
        WHERE a.shipper_id = %s AND a.order_product_name = %s
        ORDER BY p.unit_type DESC
        LIMIT 3
    """, (owner_code, product_name))
    alias_rows = cur.fetchall()
    if alias_rows:
        r = alias_rows[0]
        conn.close()
        result = _build_result(r, confidence=0.98, original_product_name=product_name)
        result["match_method"] = "Layer 0 别名表精确匹配"
        return result

    # ========== Layer 1: 精确匹配（原始名称） ==========
    cur.execute("""
        SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
        FROM product_sku
        WHERE shipper_id = %s AND status = 'ACTIVE'
          AND (sku_name = %s OR customer_code = %s)
        ORDER BY CASE WHEN unit_type = '大单位' THEN 0 ELSE 1 END
    """, (owner_code, product_name, product_name))
    rows = cur.fetchall()
    if rows:
        r = rows[0]
        conn.close()
        result = _build_result(r, confidence=0.95, original_product_name=product_name)
        result["match_method"] = "Layer 1 精确匹配"
        return result

    # ========== Layer 1b: 精确匹配（清洗后名称） ==========
    if clean_name != product_name:
        cur.execute("""
            SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
            FROM product_sku
            WHERE shipper_id = %s AND status = 'ACTIVE'
              AND (sku_name = %s OR customer_code = %s)
            ORDER BY CASE WHEN unit_type = '大单位' THEN 0 ELSE 1 END
        """, (owner_code, clean_name, clean_name))
        rows = cur.fetchall()
        if rows:
            # 如果有规格，进一步筛选
            if order_spec and len(rows) > 1:
                # 用规格筛选
                best_row = None
                best_score = 0
                for row in rows:
                    spec_score = _spec_match_score(order_spec, row[5] or "")
                    if spec_score > best_score:
                        best_score = spec_score
                        best_row = row
                if best_row and best_score >= 0.5:
                    r = best_row
                else:
                    r = rows[0]  # 没有合适的规格匹配，用第一个
            else:
                r = rows[0]
            conn.close()
            result = _build_result(r, confidence=0.93, original_product_name=product_name)
            result["match_method"] = "Layer 1b 精确匹配（去除规格后）"
            return result

    # ========== Layer 2: 模糊匹配（清洗后名称） ==========
    if clean_name != product_name:
        cur.execute("""
            SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
            FROM product_sku
            WHERE shipper_id = %s AND status = 'ACTIVE'
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
                result["match_method"] = f"Layer 2 模糊匹配+规格校验（名称{int(name_score*100)}%+规格{int(spec_score*100)}%）"
                result["need_confirm"] = False
                return result
            elif total_score >= 0.6:
                conn.close()
                result = _build_result(best, confidence=round(total_score, 2), original_product_name=product_name)
                result["match_method"] = f"Layer 2 模糊匹配+规格校验（置信度低，需确认）名称{int(name_score*100)}%+规格{int(spec_score*100)}%）"
                result["need_confirm"] = True
                return result
    
    # ========== Layer 2.5: 全量相似度匹配（始终执行，当Layer 2无结果时兜底） ==========
    cur.execute("SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code FROM product_sku WHERE shipper_id = %s AND status = 'ACTIVE' LIMIT 200", (owner_code,))
    all_skus = cur.fetchall()
    if all_skus:
        scored = []
        for r in all_skus:
            sku_name = r[1]
            name_score = SequenceMatcher(None, clean_name, sku_name).ratio()
            
            # 新增：核心词校验 - 订单清洗后名称和SKU名称必须互相包含核心词
            # 例如："鱼你幸福金汤酱料" 必须包含 "金汤"，SKU "鱼你幸福番茄酱料" 必须包含 "金汤"
            if not _has_core_word_match(clean_name, sku_name):
                continue  # 核心词不匹配，跳过此候选
            
            # 规格匹配分数
            spec_score = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
            
            # 高相似度时额外加权：当名称相似度>=0.7时，boost=0.25
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
                result["match_method"] = f"Layer 2.5 相似度匹配（名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%）"
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
        cur.execute("SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code FROM product_sku WHERE shipper_id = %s AND status = 'ACTIVE' AND sku_name LIKE %s LIMIT 20", (owner_code, f"%{keyword}%"))
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
        
        # Fallback：当分数略低(0.55-0.6)但名称相似度>=0.7时，加boost后允许通过
        if 0.55 <= total_score < 0.6 and name_score >= 0.7:
            keyword_boost = max(keyword_boost, 0.2)
            total_score = min(0.79, total_score + keyword_boost)
        
        if total_score >= 0.8:
            conn.close()
            result = _build_result(best, confidence=min(0.88, round(total_score, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%）"
            result["need_confirm"] = False
            return result
        elif total_score >= 0.6:
            conn.close()
            result = _build_result(best, confidence=min(0.88, round(total_score, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（置信度低，需确认）名称{int(name_score*100)}%+规格{int(spec_score*100)}%+加成{int(keyword_boost*100)}%）"
            result["need_confirm"] = True
            return result
        elif 0.55 <= total_score < 0.6 and name_score >= 0.7:
            # Fallback：分数在0.55-0.6之间，名称相似度>=0.7时，加boost后允许通过
            conn.close()
            result = _build_result(best, confidence=min(0.79, round(total_score + 0.2, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（Fallback加成）名称{int(name_score*100)}%+加成20%)"
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
    """构建SKU映射结果（通用）"""
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


# ============================ 批量优化（2026-06-03）============================


class SKUCache:
    """
    单个货主的 SKU 缓存，批量处理时使用

    在 map_sku_batch() 调用前预加载，一次 DB 查询获取该货主所有活跃 SKU，
    后续 Layer 2.5 / Layer 3 都在内存做相似度匹配，不再查 DB。
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
        cur.execute("""
            SELECT sku_code, sku_name, unit, unit_type,
                   conversion_ratio, product_spec, customer_code
            FROM product_sku
            WHERE shipper_id = %s AND status = 'ACTIVE'
        """, (self.owner_code,))
        self._rows = cur.fetchall()
        conn.close()
        self._loaded = True
        return self

    def rows(self) -> List[Tuple]:
        return self._rows

    def find_by_name(self, name: str) -> List[Tuple]:
        """按 sku_name 模糊查询（用于 Layer 2/3 LIKE 查询）"""
        return [r for r in self._rows if name in r[1]]

    def find_by_keyword(self, keyword: str) -> List[Tuple]:
        """按关键词 LIKE 查询（用于 Layer 3）"""
        return [r for r in self._rows if keyword in r[1]]


def map_sku_batch(owner_code: str, items: List[Dict],
                 db_config: Optional[dict] = None) -> Tuple[List[Dict], List[Dict]]:
    """
    SKU批量映射 — 推荐使用，大幅提升多商品订单的处理速度

    策略：
    1. 一次 DB 查询获取该货主所有活跃 SKU（Layer 2.5 / Layer 3 在内存做）
    2. Layer 0（别名表）仍然查 DB，但只有一次
    3. Layer 1 / 1b 在内存做（精确匹配）
    4. Layer 2 / 2.5 / 3 在内存做（模糊匹配）

    Args:
        owner_code: 货主ID
        items: list of {product_name, spec, unit, seq}
        db_config: 数据库配置

    Returns:
        (results, unmatched_items) — 与 map_sku() 返回格式兼容
    """
    if db_config is None:
        db_config = {"host": "localhost", "port": 5432, "database": "neo", "user": "jinqianfei"}

    # 预处理
    def clean_name_text(name):
        if not name:
            return ""
        name = str(name).strip()
        name = re.sub(r'[\t\u00a0\u3000\u200b\-\u200f\ufeff]+', '', name)
        name = name.replace(' ', '')
        return name

    # 预加载 SKU 缓存（一次 DB 查询）
    cache = SKUCache(owner_code, db_config).load()
    all_skus = cache.rows()

    # 加载别名表（一次 DB 查询）
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.order_product_name, p.sku_code, p.sku_name, p.unit, p.unit_type,
               p.conversion_ratio, p.product_spec, p.customer_code
        FROM product_name_alias a
        JOIN product_sku p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
        WHERE a.shipper_id = %s
    """, (owner_code,))
    alias_rows = {r[0]: r[1:] for r in cur.fetchall()}  # order_product_name -> (sku_code, sku_name, ...)
    conn.close()

    results = []
    unmatched_items = []

    for item in items:
        product_name = item.get("product_name", "")
        spec = item.get("spec", "")
        unit = item.get("unit", "件")
        seq = item.get("seq", 0)

        result = _map_single_in_batch(
            owner_code, clean_name_text(product_name),
            spec, unit, seq, db_config, cache, alias_rows, all_skus,
            clean_name_text, _extract_spec_from_name, _clean_product_name,
            _spec_match_score, _keyword_boost, _has_core_word_match
        )

        if result["matched"]:
            results.append(result)
        else:
            unmatched_items.append({
                "seq": seq, "product_name": product_name,
                "spec": spec, "quantity": item.get("quantity", 0), "unit": unit})

    return results, unmatched_items


def _map_single_in_batch(owner_code, product_name, spec, unit, seq,
                         db_config, cache, alias_rows, all_skus,
                         clean_name_text, _extract_spec_from_name,
                         _clean_product_name, _spec_match_score,
                         _keyword_boost, _has_core_word_match) -> dict:
    """单商品在批量模式下的匹配逻辑（内存计算）"""

    order_spec = _extract_spec_from_name(product_name)
    clean_name = _clean_product_name(product_name)

    # Layer 0: 别名表
    if product_name in alias_rows:
        r = alias_rows[product_name]
        result = _build_result(r, confidence=0.98, original_product_name=product_name)
        result["match_method"] = "Layer 0 别名表精确匹配"
        return result

    # Layer 1: 精确匹配
    for r in all_skus:
        if r[1] == product_name or r[6] == product_name:
            result = _build_result(r, confidence=0.95, original_product_name=product_name)
            result["match_method"] = "Layer 1 精确匹配"
            return result

    # Layer 1b: 清洗后精确匹配
    if clean_name != product_name:
        for r in all_skus:
            if r[1] == clean_name or r[6] == clean_name:
                result = _build_result(r, confidence=0.93, original_product_name=product_name)
                result["match_method"] = "Layer 1b 精确匹配（去除规格后）"
                return result

    # Layer 2: 模糊匹配
    if clean_name != product_name:
        candidates = cache.find_by_name(clean_name)
        if candidates:
            scored = []
            for r in candidates:
                ns = SequenceMatcher(None, clean_name, r[1]).ratio()
                ss = _spec_match_score(order_spec, r[5] or "") if order_spec else 0.5
                ts = ns * 0.6 + ss * 0.4
                scored.append((ts, ns, ss, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            ts, ns, ss, best = scored[0]
            if ts >= 0.8:
                result = _build_result(best, confidence=round(ts, 2), original_product_name=product_name)
                result["match_method"] = f"Layer 2 模糊匹配+规格校验（名称{int(ns*100)}%+规格{int(ss*100)}%）"
                result["need_confirm"] = False
                return result
            elif ts >= 0.6:
                result = _build_result(best, confidence=round(ts, 2), original_product_name=product_name)
                result["match_method"] = f"Layer 2 模糊匹配+规格校验（需确认）名称{int(ns*100)}%+规格{int(ss*100)}%）"
                result["need_confirm"] = True
                return result

    # Layer 2.5: 全量相似度匹配（内存）
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
        ts = ns * 0.5 + ss * 0.3 + kb * 0.2
        scored.append((ts, ns, ss, kb, r))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        ts, ns, ss, kb, best = scored[0]
        if ts >= 0.7:
            result = _build_result(best, confidence=min(0.85, round(ts, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 2.5 相似度匹配（名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%）"
            result["need_confirm"] = ts < 0.8
            return result

    # Layer 3: 分词关键词匹配（内存）
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
            ts = ns * 0.5 + ss * 0.4 + kb
            all_matches.append((ts, ns, ss, kb, r))

    if all_matches:
        all_matches.sort(key=lambda x: x[0], reverse=True)
        ts, ns, ss, kb, best = all_matches[0]
        if 0.55 <= ts < 0.6 and ns >= 0.7:
            kb = max(kb, 0.2)
            ts = min(0.79, ts + kb)
        if ts >= 0.8:
            result = _build_result(best, confidence=min(0.88, round(ts, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%）"
            result["need_confirm"] = False
            return result
        elif ts >= 0.6:
            result = _build_result(best, confidence=min(0.88, round(ts, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（需确认）名称{int(ns*100)}%+规格{int(ss*100)}%+加成{int(kb*100)}%）"
            result["need_confirm"] = True
            return result
        elif 0.55 <= ts < 0.6 and ns >= 0.7:
            result = _build_result(best, confidence=min(0.79, round(ts + 0.2, 2)), original_product_name=product_name)
            result["match_method"] = f"Layer 3 分词匹配（Fallback加成）名称{int(ns*100)}%+加成20%)"
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