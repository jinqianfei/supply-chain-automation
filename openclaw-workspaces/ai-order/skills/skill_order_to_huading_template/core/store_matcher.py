"""
core/store_matcher.py — 门店匹配核心模块

职责：
1. 调用 tools/_store_matcher.py 的 match_store 进行门店匹配
2. 管理多门店确认状态（confirmed_stores 字典）
3. 构建门店确认响应
4. 保留旧版内联匹配逻辑（向后兼容）

提取来源：
- __init__.py: _call_match_store, _is_auto_confirmed_store_match,
  _merge_confirmed_store, _confirmed_store_for, _store_confirm_response,
  _match_store (旧版内联)
"""
import copy
import importlib
from typing import Dict, Any, Optional, List


# ---------------------------------------------------------------------------
# 动态导入 tools 层
# ---------------------------------------------------------------------------

def _import_skill_attr(module_path: str, attr_name: str):
    """Import from installed skill package, with direct-directory fallback."""
    absolute_name = f"skills.skill_order_to_huading_template.{module_path}"
    try:
        module = importlib.import_module(absolute_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing != "skills" and not missing.startswith("skills.skill_order_to_huading_template"):
            raise
        module = importlib.import_module(module_path)
    return getattr(module, attr_name)


# ---------------------------------------------------------------------------
# 门店匹配调用
# ---------------------------------------------------------------------------

def call_match_store(store_name: str, customer_company: str = None,
                     db_config: dict = None,
                     phone: str = None, address: str = None,
                     contact_person: str = None) -> Optional[dict]:
    """动态导入并调用 tools.store_matcher.match_store"""
    match_store = _import_skill_attr("tools._store_matcher", "match_store")
    return match_store(
        store_name=store_name,
        customer_company=customer_company,
        db_config=db_config,
        phone=phone,
        address=address,
        contact_person=contact_person,
    )


def is_auto_confirmed_store_match(store_info: Optional[dict]) -> bool:
    """
    只有「门店名精确匹配且唯一」可以跳过人工确认。

    手机号、地址、联系人、包含/模糊匹配都需要用户确认。
    """
    if not store_info:
        return False
    if store_info.get("need_confirm") or store_info.get("candidates"):
        return False
    return store_info.get("match_type") == "exact"


# ---------------------------------------------------------------------------
# 确认状态管理
# ---------------------------------------------------------------------------

def merge_confirmed_store(confirmed_stores: Dict[str, Dict[str, Any]],
                          confirmed_store: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Merge a single or batched store confirmation into the confirmation map."""
    merged = dict(confirmed_stores or {})
    if not confirmed_store or not isinstance(confirmed_store, dict):
        return merged

    batched = confirmed_store.get("confirmed_stores")
    if isinstance(batched, dict):
        for key, store in batched.items():
            if isinstance(store, dict):
                merged[str(key)] = dict(store)

    if confirmed_store.get("store_code") or confirmed_store.get("store_name"):
        key = (
            confirmed_store.get("_store_key")
            or confirmed_store.get("store_key")
            or confirmed_store.get("store_name_submitted")
            or confirmed_store.get("store_name")
        )
        if key:
            store_copy = dict(confirmed_store)
            store_copy.pop("confirmed_stores", None)
            merged[str(key)] = store_copy

    return merged


def confirmed_store_for(confirmed_stores: Dict[str, Dict[str, Any]],
                        store_key: str, store_name: str) -> Optional[Dict[str, Any]]:
    """Find a prior confirmation by stable store key or submitted/display name.

    v5.15.3 fix: Removed overly-broad fallback that matched _store_key against
    the current store_key, which caused single-store confirmations to leak into
    ALL stores in multi-store orders (P1 bug from 2026-06-10).
    Now only exact key/name matches are used.
    """
    if not confirmed_stores:
        return None
    candidates = [store_key, store_name]
    for key in candidates:
        if key and key in confirmed_stores:
            return confirmed_stores[key]
    for store in confirmed_stores.values():
        if not isinstance(store, dict):
            continue
        submitted = store.get("store_name_submitted")
        if submitted and submitted in candidates:
            return store
    return None


def order_cache_with_confirmations(order_data: Dict[str, Any],
                                   confirmed_stores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Return a portable order cache carrying prior store confirmations."""
    try:
        cached = copy.deepcopy(order_data)
    except Exception:
        cached = dict(order_data or {})
    cached["_confirmed_stores"] = copy.deepcopy(confirmed_stores or {})
    return cached


def store_confirm_response(store_name_submitted: str, store_info: dict,
                           store_key: str = None,
                           order_data_cache: Dict[str, Any] = None,
                           confirmed_stores: Dict[str, Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建统一的门店确认响应。"""
    candidates = store_info.get("candidates") or []
    top_c = candidates[0] if candidates else store_info
    top_sim = top_c.get("similarity", store_info.get("similarity", 1.0))
    matched_store = {
        "store_code": store_info.get("store_code", top_c.get("store_code", "")),
        "store_name": store_info.get("store_name", top_c.get("store_name", "")),
        "owner_code": store_info.get("owner_code", top_c.get("owner_code", "")),
        "owner_name": store_info.get("owner_name", top_c.get("owner_name", "")),
        "warehouse_name": store_info.get("warehouse_name", top_c.get("warehouse_name", "")),
        "warehouse_code": store_info.get("warehouse_code", top_c.get("warehouse_code", "")),
        "address": store_info.get("address", top_c.get("address", "")),
        "contact_person": store_info.get("contact_person", top_c.get("contact_person", "")),
        "phone": store_info.get("phone", top_c.get("phone", "")),
        "similarity": top_sim,
        "match_type": store_info.get("match_type", top_c.get("match_type", "")),
        "match_method": store_info.get("match_method", top_c.get("match_method", "")),
        "store_name_submitted": store_name_submitted,
    }
    if store_key:
        matched_store["_store_key"] = store_key
        for c in candidates:
            if isinstance(c, dict):
                c.setdefault("_store_key", store_key)
                c.setdefault("store_name_submitted", store_name_submitted)
    return {
        "success": False,
        "need_store_confirm": True,
        "pending_store_key": store_key or store_name_submitted,
        "store_name_submitted": store_name_submitted,
        "candidates": candidates or [matched_store],
        "matched_store": matched_store,
        "confirmed_stores": confirmed_stores or {},
        "order_data_cache": order_data_cache,
        "message": f"门店「{store_name_submitted}」→ {matched_store.get('store_name', '')}，请确认"
    }


# ---------------------------------------------------------------------------
# StoreMatcher 类 — 封装完整的门店匹配 + 确认管理
# ---------------------------------------------------------------------------

class StoreMatcher:
    """
    门店匹配器

    用法：
        matcher = StoreMatcher(db_config)
        result = matcher.match("廖朵朵郑州仓", customer_company="郑州市必德...")
        confirmed_stores = matcher.process_confirmations(user_response)
    """

    def __init__(self, db_config: dict):
        self.db_config = db_config

    def match(self, store_name: str, customer_company: str = None,
              phone: str = None, address: str = None,
              contact_person: str = None) -> Optional[dict]:
        """调用 tools 层进行门店匹配"""
        return call_match_store(
            store_name=store_name,
            customer_company=customer_company,
            db_config=self.db_config,
            phone=phone,
            address=address,
            contact_person=contact_person,
        )

    def is_auto_confirmed(self, store_info: Optional[dict]) -> bool:
        """判断匹配结果是否可以自动确认"""
        return is_auto_confirmed_store_match(store_info)

    def merge_confirmation(self, confirmed_stores: Dict, confirmed_store: Optional[Dict]) -> Dict:
        """合并用户确认结果"""
        return merge_confirmed_store(confirmed_stores, confirmed_store)

    def find_confirmation(self, confirmed_stores: Dict, store_key: str, store_name: str) -> Optional[Dict]:
        """查找已确认的门店"""
        return confirmed_store_for(confirmed_stores, store_key, store_name)

    def build_confirm_response(self, store_name_submitted: str, store_info: dict,
                               store_key: str = None,
                               order_data_cache: Dict = None,
                               confirmed_stores: Dict = None) -> Dict:
        """构建门店确认响应"""
        return store_confirm_response(
            store_name_submitted, store_info,
            store_key=store_key,
            order_data_cache=order_data_cache,
            confirmed_stores=confirmed_stores,
        )

    def cache_order(self, order_data: Dict, confirmed_stores: Dict) -> Dict:
        """创建带确认状态的订单缓存"""
        return order_cache_with_confirmations(order_data, confirmed_stores)

    # ------------------------------------------------------------------
    # 高级编排方法 — Phase A + Phase B（供 execute() 调用）
    # ------------------------------------------------------------------

    def process_all_stores(self, order_data: Dict, confirmed_stores: Dict,
                           sku_matcher=None, session_id: str = "",
                           emit_event=None) -> Dict[str, Any]:
        """
        处理所有门店匹配 + SKU 匹配（多门店/单门店统一入口）

        Args:
            order_data: 解析后的订单数据
            confirmed_stores: 已确认门店字典
            sku_matcher: SKUMatcher 实例（用于 Phase B SKU 匹配）
            session_id: 会话 ID（事件 emit 用）
            emit_event: 事件发射函数 emit_event(event_name, data)

        Returns:
            处理结果字典，包含：
            - need_store_confirm: 是否需要用户确认门店
            - all_store_results: 所有门店的匹配+SKU结果
            - confirmed_stores: 更新后的确认字典
            - 或 error 信息
        """
        import time as _time

        is_multi = bool(order_data.get("_multi_store") and order_data.get("stores"))
        stores_dict = order_data.get("stores", {})

        if is_multi and stores_dict:
            return self._process_multi_store(
                order_data, stores_dict, confirmed_stores,
                sku_matcher, session_id, emit_event)
        else:
            return self._process_single_store(
                order_data, confirmed_stores,
                sku_matcher, session_id, emit_event)

    def _process_multi_store(self, order_data, stores_dict, confirmed_stores,
                             sku_matcher, session_id, emit_event):
        """多门店模式处理"""
        import time as _time
        all_store_matches = []
        pending_stores = []
        failed_stores = []
        store_items_map = {}

        for store_key, store_data in stores_dict.items():
            store_items = [it for it in order_data["items"]
                          if it.get("_store_name") == store_key
                          or it.get("_store_name") == store_data.get("store_name", store_key)]
            if not store_items:
                store_items = store_data.get("items", [])
                store_items = [{"seq": i+1, "product_code": str(it.get("product_code","")).strip(),
                               "product_name": str(it.get("product_name","")).strip(),
                               "spec": str(it.get("spec","")).strip(),
                               "quantity": int(it.get("quantity",0)),
                               "unit": str(it.get("unit","件")).strip(),
                               "remark": str(it.get("remark","")).strip()}
                              for i, it in enumerate(store_items)]
            store_items_map[store_key] = store_items
            store_name_for_match = store_data.get("store_name", store_key)
            confirmed_for_store = self.find_confirmation(confirmed_stores, store_key, store_name_for_match)

            if confirmed_for_store:
                si = confirmed_for_store
                si.setdefault("_store_key", store_key)
                si.setdefault("store_name_submitted", store_name_for_match)
                confirmed_stores[store_key] = si
                _system_match = None
                try:
                    _system_match = self.match(store_name_for_match,
                        customer_company=store_data.get("shipper_name",""),
                        phone=store_data.get("phone") or store_data.get("store_phone"),
                        address=store_data.get("address") or store_data.get("store_address"),
                        contact_person=store_data.get("contact_person"))
                except Exception:
                    pass
                _sys_code = (_system_match or {}).get("store_code","") if isinstance(_system_match, dict) else ""
                _user_code = si.get("store_code","")
                _is_correction = bool(_sys_code and _user_code and _sys_code != _user_code)
                if emit_event:
                    emit_event("store_confirmed", {"session_id": session_id, "timestamp": _time.time(),
                        "store_name_submitted": store_name_for_match, "selected_store": si,
                        "from_candidates": bool(si.get("store_code")),
                        "top_similarity": float(si.get("similarity",1.0) or 1.0),
                        "match_type": si.get("match_type","unknown"),
                        "user_response_text": "user_provided_confirmed_store"})
                    if _is_correction:
                        try:
                            emit_event("store_corrected", {"session_id": session_id, "timestamp": _time.time(),
                                "store_name_submitted": store_name_for_match,
                                "original_match": {"store_code": _sys_code, "store_name": (_system_match or {}).get("store_name","")},
                                "user_corrected_to": {"store_code": si.get("store_code",""), "store_name": si.get("store_name",""), "owner_code": si.get("owner_code","")},
                                "match_type": si.get("match_type","unknown"), "match_score": float(si.get("similarity",1.0) or 1.0)})
                        except Exception:
                            pass
            else:
                si = self.match(store_name_for_match,
                    customer_company=store_data.get("shipper_name",""),
                    phone=store_data.get("phone") or store_data.get("store_phone"),
                    address=store_data.get("address") or store_data.get("store_address"),
                    contact_person=store_data.get("contact_person"))

            is_confirmed = bool(confirmed_for_store)
            is_auto = False
            match_status = "pending"
            if not si:
                failed_stores.append({"store_key": store_key, "store_name_submitted": store_name_for_match, "error": "门店未找到匹配"})
                match_status = "failed"
            elif si.get("need_customer_hint"):
                failed_stores.append({"store_key": store_key, "store_name_submitted": store_name_for_match,
                    "error": "需要货主提示", "possible_customers": si.get("possible_customers",[])})
                match_status = "need_hint"
            elif confirmed_for_store:
                is_confirmed = True; is_auto = True; match_status = "confirmed"
            elif self.is_auto_confirmed(si):
                si.setdefault("_store_key", store_key)
                si.setdefault("store_name_submitted", store_name_for_match)
                confirmed_stores[store_key] = si
                is_confirmed = True; is_auto = True; match_status = "auto_confirmed"
            else:
                pending_stores.append(store_key)
                match_status = "pending"

            store_match_info = {"store_key": store_key, "store_name_submitted": store_name_for_match,
                "items_count": len(store_items), "items": store_items,
                "status": match_status, "is_confirmed": is_confirmed, "is_auto_confirmed": is_auto}
            if si:
                store_match_info["matched_store"] = {"store_code": si.get("store_code",""),
                    "store_name": si.get("store_name",""), "owner_code": si.get("owner_code",""),
                    "owner_name": si.get("owner_name",""), "warehouse_name": si.get("warehouse_name",""),
                    "warehouse_code": si.get("warehouse_code",""), "address": si.get("address",""),
                    "contact_person": si.get("contact_person",""), "phone": si.get("phone",""),
                    "similarity": si.get("similarity",0), "match_type": si.get("match_type",""),
                    "match_method": si.get("match_method",""), "_store_key": store_key,
                    "store_name_submitted": store_name_for_match}
                store_match_info["candidates"] = si.get("candidates",[])
            all_store_matches.append(store_match_info)

        if pending_stores or failed_stores:
            confirmed_count = sum(1 for m in all_store_matches if m["is_confirmed"])
            pending_count = len(pending_stores)
            failed_count = len(failed_stores)
            if emit_event:
                for pm in all_store_matches:
                    if pm["status"] == "pending" and pm.get("matched_store"):
                        emit_event("store_confirm_needed", {"session_id": session_id, "timestamp": _time.time(),
                            "store_name_submitted": pm["store_name_submitted"], "matched_store": pm["matched_store"],
                            "candidates": pm.get("candidates",[]), "top_similarity": pm["matched_store"].get("similarity",0),
                            "match_type": pm["matched_store"].get("match_type","unknown"),
                            "match_layer": pm["matched_store"].get("match_type","unknown"),
                            "need_customer_hint": False, "batch_mode": True,
                            "batch_total": len(all_store_matches), "batch_pending": pending_count})
            first_pending = next((m for m in all_store_matches if m["status"] == "pending"), None)
            compat = {}
            if first_pending:
                compat["store_name_submitted"] = first_pending.get("store_name_submitted","")
                compat["matched_store"] = first_pending.get("matched_store",{})
                compat["candidates"] = first_pending.get("candidates",[])
            return {"success": False, "need_store_confirm": True, "batch_mode": True,
                "all_store_matches": all_store_matches, "pending_store_keys": pending_stores,
                "pending_count": pending_count, "confirmed_count": confirmed_count,
                "failed_count": failed_count, "failed_stores": failed_stores,
                "confirmed_stores": confirmed_stores,
                "order_data_cache": self.cache_order(order_data, confirmed_stores),
                "message": f"共 {len(all_store_matches)} 个门店：{confirmed_count} 已确认，{pending_count} 待确认，{failed_count} 失败。请确认所有门店后继续",
                **compat}

        # Phase B: 全部确认 → SKU 匹配
        all_store_results = []
        for store_key, store_data in stores_dict.items():
            store_items = store_items_map.get(store_key, [])
            store_name_for_match = store_data.get("store_name", store_key)
            si = confirmed_stores.get(store_key)
            if not si:
                si = self.find_confirmation(confirmed_stores, store_key, store_name_for_match)
            if not si:
                continue
            owner_code = si.get("owner_code", "")
            sku_results, unmatched_items = sku_matcher.match_batch(store_items, owner_code) if sku_matcher else ([], [])
            all_store_results.append({"store_info": si, "store_name": store_name_for_match,
                "sku_results": sku_results, "unmatched_items": unmatched_items, "items": store_items})
        return {"success": True, "all_store_results": all_store_results, "confirmed_stores": confirmed_stores}

    def _process_single_store(self, order_data, confirmed_stores,
                              sku_matcher, session_id, emit_event):
        """单门店模式处理"""
        import time as _time
        stores_dict = order_data.get("stores", {})
        if stores_dict:
            store_key = list(stores_dict.keys())[0]
            store_data = stores_dict[store_key]
            store_name_val = store_data.get("store_name", store_key)
            phone_val = store_data.get("phone") or store_data.get("store_phone")
            address_val = store_data.get("address") or store_data.get("store_address")
            contact_val = store_data.get("contact_person")
            shipper_name_val = store_data.get("shipper_name", "")
        else:
            store_name_val = order_data.get("store_name", "")
            phone_val = order_data.get("phone")
            address_val = order_data.get("address")
            contact_val = order_data.get("contact_person")
            shipper_name_val = order_data.get("customer_company", "")
            store_key = store_name_val

        confirmed_for_store = self.find_confirmation(confirmed_stores, store_key, store_name_val)

        if confirmed_for_store:
            store_info = confirmed_for_store
            store_info.setdefault("_store_key", store_key)
            store_info.setdefault("store_name_submitted", store_name_val)
            confirmed_stores[store_key] = store_info
            _sys_match = None
            try:
                _sys_match = self.match(store_name_val, customer_company=shipper_name_val,
                    phone=phone_val, address=address_val, contact_person=contact_val)
            except Exception:
                pass
            _sys_code = (_sys_match or {}).get("store_code","") if isinstance(_sys_match, dict) else ""
            _user_code = store_info.get("store_code","")
            _is_corr = bool(_sys_code and _user_code and _sys_code != _user_code)
            if emit_event:
                emit_event("store_confirmed", {"session_id": session_id, "timestamp": _time.time(),
                    "store_name_submitted": store_name_val or order_data.get("store_name",""),
                    "selected_store": store_info, "from_candidates": bool(store_info.get("store_code")),
                    "top_similarity": float(store_info.get("similarity",1.0) or 1.0),
                    "match_type": store_info.get("match_type","unknown"),
                    "user_response_text": "user_provided_confirmed_store"})
                if _is_corr:
                    try:
                        emit_event("store_corrected", {"session_id": session_id, "timestamp": _time.time(),
                            "store_name_submitted": store_name_val,
                            "original_match": {"store_code": _sys_code, "store_name": (_sys_match or {}).get("store_name","")},
                            "user_corrected_to": {"store_code": store_info.get("store_code",""), "store_name": store_info.get("store_name",""), "owner_code": store_info.get("owner_code","")},
                            "match_type": store_info.get("match_type","unknown"), "match_score": float(store_info.get("similarity",1.0) or 1.0)})
                    except Exception:
                        pass
        else:
            store_info = self.match(store_name_val, customer_company=shipper_name_val,
                phone=phone_val, address=address_val, contact_person=contact_val)
            if not store_info:
                return {"success": False, "need_store_match": True,
                    "store_name_submitted": order_data.get("store_name",""),
                    "message": f"门店「{order_data.get('store_name','未知')}」未找到匹配门店"}
            if store_info.get("need_customer_hint"):
                return {"success": False, "need_customer_hint": True,
                    "store_name_submitted": store_info.get("store_name_submitted",""),
                    "possible_customers": store_info.get("possible_customers",[]),
                    "message": f"门店「{store_info.get('store_name_submitted','未知')}」未找到匹配，但可能属于以下货主"}
            if not self.is_auto_confirmed(store_info):
                submitted = store_info.get("store_name_submitted", store_name_val or order_data.get("store_name",""))
                response = self.build_confirm_response(submitted, store_info, store_key=store_key,
                    order_data_cache=self.cache_order(order_data, confirmed_stores),
                    confirmed_stores=confirmed_stores)
                if emit_event:
                    emit_event("store_confirm_needed", {"session_id": session_id, "timestamp": _time.time(),
                        "store_name_submitted": submitted, "matched_store": response["matched_store"],
                        "candidates": response.get("candidates",[]),
                        "top_similarity": response["matched_store"].get("similarity",0),
                        "match_type": response["matched_store"].get("match_type","unknown"),
                        "match_layer": response["matched_store"].get("match_type","unknown"),
                        "need_customer_hint": False})
                return response
            store_info.setdefault("_store_key", store_key)
            store_info.setdefault("store_name_submitted", store_name_val)
            confirmed_stores[store_key] = store_info

        owner_code = store_info.get("owner_code", "") if store_info else ""
        sku_results, unmatched_items = sku_matcher.match_batch(order_data["items"], owner_code) if sku_matcher else ([], [])
        all_store_results = [{"store_info": store_info,
            "store_name": store_info.get("store_name","") if store_info else "",
            "sku_results": sku_results, "unmatched_items": unmatched_items,
            "items": order_data["items"]}]
        return {"success": True, "all_store_results": all_store_results, "confirmed_stores": confirmed_stores}
