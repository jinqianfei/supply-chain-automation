"""
模糊匹配算法模块（门店/SKU 共用）

提供：
- calculate_similarity(s1, s2) → float — 综合相似度（SequenceMatcher + 包含 + 关键词）
- extract_keywords(name, top_n) → list — 提取中文关键词
- best_match(candidates, target, key) → dict — 从候选列表中找最佳匹配
- filter_by_threshold(candidates, target, threshold, key) → list — 按阈值过滤
- calculate_name_score(s1, s2) → float — 纯名称相似度（SequenceMatcher）
- has_core_word_match(s1, s2) → bool — 核心词校验（SKU 匹配用）
- keyword_boost(s1, s2) → float — 关键词加成系数

依赖：difflib（标准库）、re（标准库）
可选依赖：jieba（分词，降级到正则提取）
"""

import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Callable, Any, Tuple


# ---------------------------------------------------------------------------
# 品牌前缀（清理用）
# ---------------------------------------------------------------------------

BRAND_PREFIXES = [
    '制茶青年-', '制茶青年',
    '天津仓-', '天津仓',
    '廖朵朵-', '廖朵朵',
]

# 地名关键词正则（省/市/区/县/镇/乡/村/街/路/店/仓/口）
LOCATION_PATTERN = re.compile(r'[\u4e00-\u9fa5]{2,6}(?:省|市|区|县|镇|乡|村|街|路|店|仓|口)')

# 中文连续字符正则
CHINESE_SEGMENT_PATTERN = re.compile(r'[\u4e00-\u9fa5]{2,4}')


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

def calculate_name_score(s1: str, s2: str) -> float:
    """
    纯名称相似度（SequenceMatcher ratio）

    Args:
        s1: 字符串1
        s2: 字符串2

    Returns:
        0.0 ~ 1.0
    """
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def _clean_brand_prefix(s: str) -> str:
    """清理品牌前缀"""
    for prefix in BRAND_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def calculate_similarity(s1: str, s2: str) -> float:
    """
    综合相似度（门店匹配专用）

    策略：
    1. 清理品牌前缀
    2. 基础相似度（SequenceMatcher）
    3. 包含匹配加分（短串是长串的前缀/包含）
    4. 地名关键词匹配加分

    Args:
        s1: 输入名称（如订单门店名）
        s2: 数据库名称（如 store_name）

    Returns:
        0.0 ~ 1.0+（可能超过 1.0 因为有 bonus）
    """
    if not s1 or not s2:
        return 0.0

    # 清理品牌前缀
    s1_cleaned = _clean_brand_prefix(s1)
    s2_cleaned = _clean_brand_prefix(s2)

    # 1. 基础相似度
    base_sim = SequenceMatcher(None, s1_cleaned, s2_cleaned).ratio()

    # 2. 包含匹配加分
    shorter = s1_cleaned if len(s1_cleaned) <= len(s2_cleaned) else s2_cleaned
    longer = s2_cleaned if len(s1_cleaned) <= len(s2_cleaned) else s1_cleaned

    contain_bonus = 0.0
    if shorter and shorter in longer:
        contain_bonus = len(shorter) / len(longer) + 0.3

    # 3. 地名关键词匹配
    loc1 = set(LOCATION_PATTERN.findall(s1_cleaned))
    loc2 = set(LOCATION_PATTERN.findall(s2_cleaned))

    keyword_bonus = 0.0
    if loc1 and loc2:
        common = loc1 & loc2
        if common:
            keyword_bonus = min(len(common) * 0.2, 0.6)

    return max(base_sim, contain_bonus, base_sim + keyword_bonus)


def extract_keywords(name: str, top_n: int = 5) -> List[str]:
    """
    提取中文关键词（2-4 字连续中文段）

    用于门店名/SKU 名分词后做关键词搜索。
    优先使用 jieba（如已安装），降级到正则提取。

    Args:
        name: 输入名称
        top_n: 最多返回几个关键词

    Returns:
        list of str（关键词列表）
    """
    if not name:
        return []

    # 尝试 jieba 分词
    try:
        import jieba
        words = list(jieba.cut(name))
        # 过滤：只保留 2+ 字符的中文词
        keywords = [w for w in words if len(w) >= 2 and re.match(r'^[\u4e00-\u9fa5]+$', w)]
        # 按长度降序（长词更精确）
        keywords.sort(key=len, reverse=True)
        return keywords[:top_n]
    except ImportError:
        pass

    # 降级：正则提取 2-4 字连续中文
    segments = CHINESE_SEGMENT_PATTERN.findall(name)
    # 去重保序
    seen = set()
    keywords = []
    for seg in segments:
        if seg not in seen:
            seen.add(seg)
            keywords.append(seg)
    return keywords[:top_n]


def best_match(
    candidates: List[Any],
    target: str,
    key: Optional[Callable] = None,
    similarity_func: Optional[Callable] = None,
) -> Optional[Dict]:
    """
    从候选列表中找最佳匹配

    Args:
        candidates: 候选列表（可以是 dict/tuple/str）
        target: 目标字符串
        key: 从候选中提取比较字符串的函数（默认：如果是 str 直接用，dict 取 'name' 或 'store_name'）
        similarity_func: 自定义相似度函数（默认 calculate_similarity）

    Returns:
        {
            "item": 最佳匹配项,
            "score": 相似度分数,
            "index": 在 candidates 中的索引
        }
        或 None（candidates 为空）
    """
    if not candidates:
        return None

    sim_func = similarity_func or calculate_similarity

    # 默认 key 函数
    if key is None:
        def _default_key(item):
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                return item.get("name") or item.get("store_name") or item.get("sku_name") or ""
            if isinstance(item, (tuple, list)):
                # 通常第二个元素是名称
                return str(item[1]) if len(item) > 1 else str(item[0])
            return str(item)
        key = _default_key

    best_score = -1.0
    best_item = None
    best_idx = -1

    for idx, candidate in enumerate(candidates):
        candidate_str = key(candidate)
        score = sim_func(target, candidate_str)
        if score > best_score:
            best_score = score
            best_item = candidate
            best_idx = idx

    return {
        "item": best_item,
        "score": best_score,
        "index": best_idx,
    }


def filter_by_threshold(
    candidates: List[Any],
    target: str,
    threshold: float = 0.7,
    key: Optional[Callable] = None,
    similarity_func: Optional[Callable] = None,
) -> List[Dict]:
    """
    按阈值过滤候选列表

    Args:
        candidates: 候选列表
        target: 目标字符串
        threshold: 最低相似度阈值
        key: 提取比较字符串的函数
        similarity_func: 自定义相似度函数

    Returns:
        list of {"item": ..., "score": ..., "index": ...}
        按 score 降序排列
    """
    if not candidates:
        return []

    sim_func = similarity_func or calculate_similarity

    # 默认 key 函数（同 best_match）
    if key is None:
        def _default_key(item):
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                return item.get("name") or item.get("store_name") or item.get("sku_name") or ""
            if isinstance(item, (tuple, list)):
                return str(item[1]) if len(item) > 1 else str(item[0])
            return str(item)
        key = _default_key

    results = []
    for idx, candidate in enumerate(candidates):
        candidate_str = key(candidate)
        score = sim_func(target, candidate_str)
        if score >= threshold:
            results.append({
                "item": candidate,
                "score": score,
                "index": idx,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# SKU 匹配专用辅助函数
# ---------------------------------------------------------------------------

def has_core_word_match(order_name: str, sku_name: str) -> bool:
    """
    核心词校验（SKU 匹配用）

    判断订单清洗后名称和 SKU 名称是否共享核心词（排除不同口味调料的错误匹配）。

    策略：
    - 提取 2-4 字中文片段作为核心词候选
    - 检查是否有交集

    Args:
        order_name: 订单商品名（清洗后）
        sku_name: SKU 名称

    Returns:
        True 表示核心词匹配通过
    """
    if not order_name or not sku_name:
        return False

    # 提取 2-3 字中文片段（核心词）
    def get_core_words(name, min_len=2, max_len=3):
        words = set()
        for length in range(min_len, max_len + 1):
            for i in range(len(name) - length + 1):
                seg = name[i:i + length]
                if re.match(r'^[\u4e00-\u9fa5]+$', seg):
                    words.add(seg)
        return words

    order_cores = get_core_words(order_name)
    sku_cores = get_core_words(sku_name)

    if not order_cores or not sku_cores:
        # 如果太短无法提取核心词，默认通过
        return True

    # 有交集即通过
    return bool(order_cores & sku_cores)


def keyword_boost(s1: str, s2: str) -> float:
    """
    关键词加成系数（SKU 匹配用）

    当两个字符串共享关键片段时，给予额外加成。

    Args:
        s1: 订单商品名（清洗后）
        s2: SKU 名称

    Returns:
        0.0 ~ 0.3 的加成系数
    """
    if not s1 or not s2:
        return 0.0

    # 提取 2-3 字核心词
    def get_core_words(name):
        words = set()
        for length in [2, 3]:
            for i in range(len(name) - length + 1):
                seg = name[i:i + length]
                if re.match(r'^[\u4e00-\u9fa5]+$', seg):
                    words.add(seg)
        return words

    cores1 = get_core_words(s1)
    cores2 = get_core_words(s2)

    if not cores1 or not cores2:
        return 0.0

    common = cores1 & cores2
    if not common:
        return 0.0

    # 共同核心词越多，加成越高
    # 1个 → 0.1, 2个 → 0.2, 3+个 → 0.3
    return min(len(common) * 0.1, 0.3)


# ---------------------------------------------------------------------------
# 2-char n-gram 覆盖率（门店匹配辅助）
# ---------------------------------------------------------------------------

def get_2char_combos(name: str) -> set:
    """
    提取 2 字符中文组合（n-gram 覆盖率计算用）

    Args:
        name: 输入名称

    Returns:
        set of 2-char strings
    """
    chars = [c for c in name if '\u4e00' <= c <= '\u9fff']
    return set(''.join(chars[i:i + 2]) for i in range(len(chars) - 1))
