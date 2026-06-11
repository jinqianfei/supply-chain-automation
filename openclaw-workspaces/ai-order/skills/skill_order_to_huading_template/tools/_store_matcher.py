"""
门店匹配工具 - 将统一JSON中的门店名匹配到数据库中的门店，获取货主ID

支持多层匹配策略：
- Layer 0: 手机号/收货人/地址辅助匹配（基于订单主行信息）
- Layer 1: 客户公司匹配（优先）
- Layer 2: 精确匹配
- Layer 3: 模糊匹配（相似度计算）
"""
from typing import Optional, Dict, Any, List, Tuple
from difflib import SequenceMatcher
import re


def _strip_brand_prefix(store_name: str) -> str:
    """去除品牌前缀，提取门店具体名称部分"""
    # 常见品牌前缀（从实际数据中提取）
    prefixes = [
        "制茶青年-", "制茶青年",
        "廖朵朵-", "廖朵朵蛋糕-", "廖朵朵",
        "口口椰-K", "口口椰-", "口口椰",
        "创宇-", "创宇",
        "阿朴社长-", "阿朴社长济南-", "阿朴社长",
        "V甜-", "V甜",
        "哎渔村", "哎渔村-",
    ]
    for prefix in prefixes:
        if store_name.startswith(prefix):
            remainder = store_name[len(prefix):]
            return remainder.lstrip("-").strip()
    return store_name



def _keyword_cross_match(store_name: str, db_config: Optional[dict]) -> Optional[dict]:
    """
    关键词交叉匹配 - Layer 3.5（模糊匹配失败后的兜底）
    
    当 store_name 包含品牌+地址但顺序颠倒（如"沛县廖朵朵" -> "廖朵朵-徐州沛县"）
    时，通过提取关键词并搜索包含这些关键词的门店来做匹配。
    
    Args:
        store_name: 门店名称（从订单中提取）
        db_config: 数据库配置
    
    Returns:
        匹配结果 dict 或 None
    """
    import re
    from difflib import SequenceMatcher
    
    # 移除常见品牌前缀，提取剩余的地址/位置关键词
    clean_name = store_name
    for prefix in ['廖朵朵', '创宇', 'V甜', '口口椰', '阿朴', '口口']:
        clean_name = clean_name.replace(prefix, '')
    
    # 提取2-char以上的有意义的词
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}', clean_name)
    meaningful = [w for w in words if len(w) >= 2 and w not in ['徐州市', '江苏省']]
    
    if not meaningful:
        return None
    
    conn = _get_connection(db_config)
    cur = conn.cursor()
    
    # 用关键词搜索数据库门店
    all_codes = set()
    for kw in meaningful[:3]:
        cur.execute("""
            SELECT store_code FROM store_list WHERE store_name LIKE %s
        """, (f'%{kw}%',))
        for row in cur.fetchall():
            all_codes.add(row[0])
    
    if not all_codes:
        conn.close()
        return None
    
    store_codes = list(all_codes)
    placeholders = ','.join(['%s'] * len(store_codes))
    cur.execute(f"""
        SELECT store_code, store_name, owner_name, owner_code, phone, address, warehouse
        FROM store_list WHERE store_code IN ({placeholders})
    """, store_codes)
    candidates = [dict(zip(
        ['store_code', 'store_name', 'owner_name', 'owner_code', 'phone', 'address', 'warehouse_name'],
        row
    )) for row in cur.fetchall()]
    conn.close()
    
    # 计算 2-char n-gram 覆盖率
    def get_2char_combos(name):
        chars = [c for c in name if '一' <= c <= '龥']
        return set(''.join(chars[i:i+2]) for i in range(len(chars)-1))
    
    input_combos = get_2char_combos(store_name)
    scored = []
    for store in candidates:
        db_combos = get_2char_combos(store["store_name"])
        common = input_combos & db_combos
        coverage = len(common) / len(input_combos) if input_combos else 0
        seq = SequenceMatcher(None, store_name, store["store_name"]).ratio()
        score = 0.5 * coverage + 0.5 * seq
        scored.append((score, coverage, store))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    
    if scored and scored[0][0] >= 0.35:
        best = scored[0][2]
        coverage = scored[0][1]
        return {
            "store_code": best["store_code"],
            "store_name": best["store_name"],
            "owner_code": best["owner_code"],
            "owner_name": best.get("owner_name", ""),
            "warehouse_name": best.get("warehouse_name", ""),
            "address": best.get("address", ""),
            "phone": best.get("phone", ""),
            "contact_person": "",
            "match_type": "keyword_cross",
            "match_method": f"关键词交叉匹配（覆盖率{coverage:.0%}）",
        }
    
    return None


def match_store(store_name: str, customer_company: str = None,
                db_config: Optional[dict] = None,
                phone: str = None, address: str = None,
                contact_person: str = None) -> Optional[dict]:
    """
    门店匹配 - 多层级匹配策略

    新增 Layer 0: 手机号/收货人/地址辅助匹配
    - 当 store_name 是无效值（如"店铺1"、"订单号"）时使用
    - 优先用手机号精确匹配
    - 其次用收货人姓名/地址模糊匹配

    Args:
        store_name: 门店名称（从订单中提取）
        customer_company: 客户公司名称（可选，用于优先匹配货主）
        phone: 手机号（从订单主行提取，可选）
        address: 收货地址（从订单主行提取，可选）
        contact_person: 收货人姓名（从订单主行提取，可选）

    Returns:
        精确匹配：门店信息 dict
        模糊匹配候选：{"need_confirm": True, "candidates": [...], "store_name_submitted": ...}
        未匹配但有货主提示：{"need_customer_hint": True, "possible_customers": [...]}
        完全未匹配：None
    """
    # ========== 判断是否需要使用辅助匹配（Layer 0）==========
    # 条件：store_name 无效（店铺/门店/SN开头/太短） OR 有手机号（最高优先级）
    # 注意：即使 store_name 看起来正常，只要有手机号就应该优先尝试精确匹配
    _is_invalid_name = (not store_name or
                        store_name.startswith("店铺") or
                        store_name.startswith("门店") or
                        store_name.startswith("SN") or
                        store_name.startswith("PN") or
                        len(store_name) < 3)

    # 【v5.15.0】有手机号时匹配，增加门店名校验
    # v5.15.1 fix: 手机号命中但门店名差异大时，保留候选以便合并到最终结果
    _phone_candidate = None
    if phone:
        phone_result = _find_by_phone(phone, db_config)
        if phone_result:
            if isinstance(phone_result, dict) and phone_result.get("_multi"):
                # 多门店共用手机号 → 按门店名相似度排序
                stores = phone_result["stores"]
                scored = []
                for s in stores:
                    # 先完整名称相似度
                    sim = SequenceMatcher(None, store_name, s["store_name"]).ratio()
                    if sim < 0.6:
                        # 不够则去品牌前缀再算
                        sim2 = SequenceMatcher(
                            None,
                            _strip_brand_prefix(store_name),
                            _strip_brand_prefix(s["store_name"])
                        ).ratio()
                        sim = max(sim, sim2)
                    scored.append((sim, s))
                scored.sort(key=lambda x: x[0], reverse=True)
                best_sim, best_store = scored[0]

                if best_sim >= 0.8:
                    return _build_store_result(best_store, "phone_exact_high_conf",
                                               f"手机号+门店名双重匹配（{phone}，{best_sim:.0%}）", db_config)
                elif best_sim >= 0.6:
                    result = _build_store_result(best_store, "phone_exact_multi",
                                                 f"手机号匹配+门店名待确认（{phone}，{best_sim:.0%}）", db_config)
                    result["need_confirm"] = True
                    result["candidates"] = [_build_store_result(s, "phone_exact_multi",
                                                 f"{phone}，{sim:.0%}", db_config)
                                            for sim, s in scored if sim >= 0.5]
                    return result
                # else: 全部 < 0.6，不信任手机号，保留候选供后续合并
                _phone_candidate = _build_store_result(best_store, "phone_exact_low_conf",
                    f"手机号匹配但门店名差异大（{phone}，{best_sim:.0%}）", db_config)
                _phone_candidate["candidate_source"] = "phone_exact"
            else:
                # 唯一命中 → 也要做门店名校验
                sim = SequenceMatcher(None, store_name, phone_result["store_name"]).ratio()
                if sim < 0.6:
                    sim2 = SequenceMatcher(
                        None,
                        _strip_brand_prefix(store_name),
                        _strip_brand_prefix(phone_result["store_name"])
                    ).ratio()
                    sim = max(sim, sim2)

                if sim >= 0.8:
                    return _build_store_result(phone_result, "phone_exact_high_conf",
                                               f"手机号+门店名双重匹配（{phone}，{sim:.0%}）", db_config)
                elif sim >= 0.6:
                    result = _build_store_result(phone_result, "phone_exact",
                                                 f"手机号匹配+门店名待确认（{phone}，{sim:.0%}）", db_config)
                    result["need_confirm"] = True
                    return result
                # else: < 0.6，不信任手机号，保留候选供后续合并
                _phone_candidate = _build_store_result(phone_result, "phone_exact_low_conf",
                    f"手机号匹配但门店名差异大（{phone}，{sim:.0%}）", db_config)
                _phone_candidate["candidate_source"] = "phone_exact"

        # 手机号没匹配到或门店名差异太大，且store_name也无效时，尝试地址关键词
        if _is_invalid_name and address:
            addr_result = _match_by_address_keyword(address, db_config)
            if addr_result:
                return addr_result

    # 无效名称且有收货人/地址时，尝试辅助匹配
    if _is_invalid_name and (address or contact_person):
        result = _match_by_order_info(phone, address, contact_person, db_config)
        if result:
            return result

    # ========== Layer 1: 客户公司匹配（优先）==========
    if customer_company:
        result = _match_by_company(customer_company, db_config)
        if result:
            return result

    # ========== Layer 2: 精确匹配 ==========
    stores = _find_store(store_name, db_config)
    exact_matches = [s for s in stores if s["store_name"] == store_name]

    if len(exact_matches) == 1:
        store = exact_matches[0]
        return _build_store_result(store, "exact", f"精确匹配（'{store_name}'）", db_config)

    if len(exact_matches) > 1:
        return {
            "need_confirm": True,
            "store_name_submitted": store_name,
            "candidates": [_build_store_result(s, "exact", "", db_config) for s in exact_matches],
            "message": f"门店「{store_name}」找到 {len(exact_matches)} 个精确匹配"
        }

    # 精确匹配无结果时，检查地址是否包含沛县/伊春等关键词作为辅助判断
    if address:
        addr_kw = _extract_address_keywords(address)
        for kw in addr_kw:
            addr_stores = _find_store(kw, db_config)
            liaoduo_stores = [s for s in addr_stores if "廖朵朵" in s["store_name"]]
            if liaoduo_stores:
                # 找到了地址关键词匹配+廖朵朵的门店
                # 验证store_name是否与廖朵朵相关（包含"廖朵朵"或"沛县"或"徐州"等）
                if "廖朵朵" in store_name:
                    return _build_store_result(liaoduo_stores[0], "fuzzy_contains",
                                               f"门店+地址综合匹配（'{store_name}', addr='{kw}'）", db_config)

    # ========== Layer 3: 模糊匹配 ==========
    fuzzy_matches = [s for s in stores if s["store_name"] != store_name]

    # 如果有包含关系（输入名是店名的一部分）
    for store in stores:
        if store_name in store["store_name"] or store["store_name"] in store_name:
            return _build_store_result(store, "fuzzy_contains",
                                       f"包含匹配（'{store_name}'→'{store['store_name']}'）", db_config)

    # 计算相似度
    scored = []
    for store in fuzzy_matches:
        ratio = SequenceMatcher(None, store_name, store["store_name"]).ratio()
        if ratio >= 0.5:
            scored.append((ratio, store))

    scored.sort(key=lambda x: x[0], reverse=True)

    if scored and scored[0][0] >= 0.75:
        best = scored[0][1]
        return _build_store_result(best, "fuzzy_similar",
                                   f"模糊匹配（相似度{scored[0][0]:.0%}）: '{store_name}'→'{best['store_name']}'", db_config)

    if scored:
        candidates = [_build_store_result(s, "fuzzy", f"相似度{r:.0%}", db_config)
                      for r, s in scored[:5]]
        return {
            "need_confirm": True,
            "store_name_submitted": store_name,
            "candidates": candidates,
            "message": f"门店「{store_name}」找到 {len(candidates)} 个相近匹配"
        }


    # ========== Layer 3.5: 关键词交叉匹配（兜底）==========
    # 当所有前述匹配都失败时，用关键词分词+覆盖率方式做最后兜底
    cross_result = _keyword_cross_match(store_name, db_config)
    if cross_result:
        return _build_store_result(cross_result, "keyword_cross",
                                   cross_result.get("match_method", "关键词交叉匹配"), db_config)

    # ========== Layer 3.6: 联系人姓名兜底（contact_person 作为门店名输入时）==========
    # 当 contact_person 是有效人名（如"梁女士"）而非门店名时，
    # 用 contact_person + 原始地址/手机号信息重新匹配
    if contact_person and contact_person != store_name and len(contact_person) >= 2:
        # 尝试用 contact_person 重新搜索门店（忽略 Layer 0/1/2，直接 Layer 3）
        # 如果手机号存在，优先用手机号
        if phone:
            by_phone = _find_by_phone(phone, db_config)
            if by_phone:
                return _build_store_result(by_phone, "phone_exact",
                                            f"手机号精确匹配（{phone}，contact_person兜底）", db_config)
        # 尝试用地址关键词匹配
        if address:
            addr_result = _match_by_address_keyword(address, db_config)
            if addr_result:
                return addr_result

    # ========== 未匹配到：尝试货主提示 ==========
    possible_customers = _search_by_name(store_name, db_config)
    if possible_customers:
        return {
            "need_customer_hint": True,
            "store_name_submitted": store_name,
            "possible_customers": possible_customers,
            "message": f"门店「{store_name}」未找到，但以下货主名称相似："
        }

    return None


def _extract_address_keywords(address: str) -> list:
    """从地址中提取有意义的区县/市/省关键词（由小到大）"""
    import re
    # 先提取省/市/区/县（用更精确的正则，避免将"沛县九龙"合在一起）
    # 匹配省/市/区/县 - 2-4字符
    pattern = r'[\u4e00-\u9fa5]{2,4}'
    all_words = re.findall(pattern, address)
    # 优先返回县/区级关键词
    for w in all_words:
        if any(x in w for x in ['县', '区']) and len(w) <= 4:
            return [w]
    # 如果没有县/区，返回市名
    for w in all_words:
        if '市' in w and len(w) <= 4:
            return [w]
    # 再返回省
    for w in all_words:
        if '省' in w and len(w) <= 4:
            return [w]
    return all_words[:2] if all_words else []


def _match_by_address_keyword(address: str, db_config: Optional[dict]) -> Optional[dict]:
    """通过地址关键词匹配门店（phone无结果时fallback）"""
    if not address:
        return None
    import re
    keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', address)
    keywords.sort(key=len, reverse=True)
    for kw in keywords:
        stores = _find_store(kw, db_config)
        if stores:
            liaoduo = [s for s in stores if "廖朵朵" in s["store_name"]]
            if liaoduo:
                return _build_store_result(liaoduo[0], "address_keyword",
                                           f"地址关键词匹配（'{kw}'）", db_config)
            scored = [(SequenceMatcher(None, address, s["address"]).ratio(), s)
                      for s in stores]
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0][1] if scored else stores[0]
            return _build_store_result(best, "address_keyword",
                                       f"地址关键词匹配（'{kw}'）", db_config)
    return None


def _match_by_order_info(phone: str, address: str, contact_person: str,
                         db_config: Optional[dict]) -> Optional[dict]:
    """
    Layer 0 (续): 通过收货人/地址匹配门店（phone已在主流程优先处理）

    优先级：
    1. 收货人姓名匹配（高相似度）
    2. 地址关键词匹配
    """
    if not address and not contact_person:
        return None

    # 第1优先级：收货人姓名匹配（手机号已在上层处理）
    if contact_person:
        stores = _find_store(contact_person, db_config)
        if stores:
            # 取相似度最高的
            scored = [(SequenceMatcher(None, contact_person, s["store_name"]).ratio(), s)
                      for s in stores]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored and scored[0][0] >= 0.6:
                return _build_store_result(scored[0][1], "contact_person",
                                           f"收货人姓名匹配（'{contact_person}'→'{scored[0][1]['store_name']}'）", db_config)

    # 第3优先级：地址关键词匹配
    if address:
        # 提取所有中文字符串（2+字符）
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', address)
        # 按长度降序排列（优先匹配更具体的地名，如"沛县"而非"江苏"）
        keywords.sort(key=len, reverse=True)
        for kw in keywords:
            stores = _find_store(kw, db_config)
            if stores:
                # 优先选廖朵朵相关门店
                liaoduo = [s for s in stores if "廖朵朵" in s["store_name"]]
                if liaoduo:
                    best = liaoduo[0]
                else:
                    # 选相似度最高的
                    scored = [(SequenceMatcher(None, address, s["address"]).ratio(), s)
                              for s in stores]
                    scored.sort(key=lambda x: x[0], reverse=True)
                    best = scored[0][1] if scored else stores[0]
                return _build_store_result(best, "address_keyword",
                                           f"地址关键词匹配（'{kw}'）", db_config)

    return None


def _match_by_company(customer_company: str, db_config: Optional[dict]) -> Optional[dict]:
    """通过客户公司名匹配货主"""
    customers = _search_by_name(customer_company, db_config)
    if not customers:
        return None

    owner_code = customers[0]["customer_id"]
    stores = _get_by_owner(owner_code, db_config)

    if stores:
        return _build_store_result(stores[0], "customer_company",
                                   f"客户公司匹配（'{customer_company}'）", db_config)

    return None


def _build_store_result(store: dict, match_type: str, match_method: str, db_config: Optional[dict] = None) -> dict:
    """构建统一的门店信息返回格式"""
    warehouse_name = store.get("warehouse", "") or store.get("warehouse_name", "")
    warehouse_code = ""
    warehouse_code_error = None
    if warehouse_name:
        try:
            import psycopg2
            conn = psycopg2.connect(**db_config)
            cur = conn.cursor()
            cur.execute("""
                SELECT warehouse_code FROM warehouse_code_mapping
                WHERE warehouse_name = %s
            """, (warehouse_name,))
            row = cur.fetchone()
            if row:
                warehouse_code = row[0] or ""
            cur.close()
            conn.close()
        except Exception as e:
            warehouse_code_error = str(e)

    result = {
        "store_code": store.get("store_code", ""),
        "store_name": store.get("store_name", ""),
        "owner_code": store.get("owner_code", ""),
        "owner_name": store.get("owner_name", ""),
        "warehouse_name": store.get("warehouse", ""),
        "warehouse_code": warehouse_code,
        "address": store.get("address", ""),
        "contact_person": store.get("contact_person", ""),
        "phone": store.get("phone", ""),
        "match_type": match_type,
        "match_method": match_method,
    }
    if warehouse_code_error:
        result["warehouse_code_error"] = warehouse_code_error
    return result


# ========== 数据库操作（内联，避免相对导入问题）==========
def _get_connection(db_config):
    import psycopg2
    return psycopg2.connect(**db_config)


def _find_store(name: str, db_config: Optional[dict] = None) -> List[dict]:
    """按名称模糊匹配门店"""
    if not db_config:
        return []
    conn = _get_connection(db_config)
    cur = conn.cursor()

    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE store_name LIKE %s
    """, (f"%{name}%",))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "store_code": r[0] or "",
            "store_name": r[1] or "",
            "owner_code": r[2] or "",
            "owner_name": r[3] or "",
            "province": r[4] or "",
            "city": r[5] or "",
            "district": r[6] or "",
            "address": r[7] or "",
            "phone": r[8] or "",
            "contact_person": r[9] or "",
            "warehouse": r[10] or "",
        }
        for r in rows
    ]


def _get_by_owner(owner_code: str, db_config: Optional[dict] = None) -> List[dict]:
    """按货主ID查询所有门店"""
    if not db_config:
        return []
    conn = _get_connection(db_config)
    cur = conn.cursor()

    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE owner_code = %s
        LIMIT 20
    """, (owner_code,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "store_code": r[0] or "",
            "store_name": r[1] or "",
            "owner_code": r[2] or "",
            "owner_name": r[3] or "",
            "province": r[4] or "",
            "city": r[5] or "",
            "district": r[6] or "",
            "address": r[7] or "",
            "phone": r[8] or "",
            "contact_person": r[9] or "",
            "warehouse": r[10] or "",
        }
        for r in rows
    ]


def _find_by_phone(phone: str, db_config: Optional[dict] = None) -> Optional[dict]:
    """按手机号查询门店（支持多门店复用场景）"""
    if not phone or not db_config:
        return None
    conn = _get_connection(db_config)
    cur = conn.cursor()

    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE phone = %s
    """, (phone,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return None

    def _row_to_dict(r):
        return {
            "store_code": r[0] or "", "store_name": r[1] or "",
            "owner_code": r[2] or "", "owner_name": r[3] or "",
            "province": r[4] or "", "city": r[5] or "",
            "district": r[6] or "", "address": r[7] or "",
            "phone": r[8] or "", "contact_person": r[9] or "",
            "warehouse": r[10] or "",
        }

    if len(rows) == 1:
        return _row_to_dict(rows[0])

    # 多门店共用手机号
    return {"_multi": True, "stores": [_row_to_dict(r) for r in rows]}


def _search_by_name(name: str, db_config: Optional[dict] = None) -> List[dict]:
    """按名称模糊搜索货主"""
    if not db_config:
        return []
    conn = _get_connection(db_config)
    cur = conn.cursor()

    cur.execute("""
        SELECT customer_id, customer_name, customer_type, contact_person,
               contact_phone, address, warehouse_name, status
        FROM customer
        WHERE status = 'ACTIVE' AND customer_name LIKE %s
        ORDER BY customer_name
        LIMIT 10
    """, (f"%{name}%",))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "customer_id": r[0],
            "customer_name": r[1],
            "customer_type": r[2],
            "contact_person": r[3],
            "contact_phone": r[4],
            "address": r[5],
            "warehouse_name": r[6],
            "status": r[7],
        }
        for r in rows
    ]