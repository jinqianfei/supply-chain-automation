"""
skill-order-to-huading-template  v5.15.4-slim

将客户订单Excel转换为华鼎出库单模板（31字段）
支持Excel/图片/PDF/文字多种输入格式

重构 Phase 5：编排层精简（__init__.py 仅负责流程编排）
核心逻辑已提取到 core/ 模块：
- core.StoreMatcher   — 门店匹配
- core.SKUMatcher     — SKU 映射
- core.TemplateGenerator — 模板生成
- core.OrderParser    — 订单解析

自学习模块已解耦到工作区级 learning/，通过软加载启用。
事件总线已移至工作区级 events/。
"""

import os
import re
import datetime
import time
import uuid
import copy
import importlib
from typing import Dict, Any, Optional, Union, List, Tuple

# ── 统一 .env 加载器 ────────────────────────────────
from db.connection import _load_dotenv_to_environ
# ── 统一配置加载器 ──────────────────────────────────
from config import _get_huading_fields

# ── 事件总线 + 反馈采集器（懒加载，单例）────────────
try:
    from events.bus import EventBus
    from learn.collector import init_feedback_collector, get_feedback_collector
    _HAS_EVENT_BUS = True
except ImportError:
    _HAS_EVENT_BUS = False
    EventBus = None
    init_feedback_collector = None
    get_feedback_collector = None

# ── 自学习模块（软加载，不阻断主流程）───────────────
_LEARNING_ENABLED = False
try:
    import sys as _sys
    _ws = os.environ.get(
        "AI_ORDER_WORKSPACE",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if _ws not in _sys.path:
        _sys.path.insert(0, _ws)
    from learning import auto_init as _learning_auto_init
    from learning.feedback_parser import parse_user_feedback as _learning_parse_feedback
    from learning.modifier import apply_modifications as _learning_apply_modifications
    _LEARNING_ENABLED = True
except ImportError:
    _learning_auto_init = None
    _learning_parse_feedback = None
    _learning_apply_modifications = None

# ── core/ 模块导入 ──────────────────────────────────
from core.store_matcher import (
    StoreMatcher, call_match_store, is_auto_confirmed_store_match,
    merge_confirmed_store, confirmed_store_for, store_confirm_response,
    order_cache_with_confirmations,
)
from core.sku_matcher import SKUMatcher, clean_product_name
from core.generator import (
    TemplateGenerator, format_success_message, format_comparison_table_text,
    get_download_url, get_file_info, prepare_file_for_send,
    HUADING_FIELDS, DEFAULT_VALUES,
)
from core.parser import (
    OrderParser, FIELD_ALIAS_MAPPING, _parse_item_row, _is_sku_code,
    _normalize_ai_result_static,
)


# ── 代理环境变量清理 ────────────────────────────────
_PROXY_ENV_KEYS = (
    "SOCKS_PROXY", "socks_proxy", "ALL_PROXY", "all_proxy",
    "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
    "NO_PROXY", "no_proxy",
)


def _clear_proxy_env():
    """Remove proxy env vars that can break LLM/RDS network clients."""
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)


# ── 动态导入（向后兼容）────────────────────────────
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


# ── 异常与错误码 ────────────────────────────────────

class OrderSkillError(Exception):
    """订单映射Skill专用异常"""
    def __init__(self, code: str, message: str, detail: str = ""):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"[{code}] {message}")


ERROR_CODES = {
    "E001": {"title": "文件不存在", "message": "您上传的文件未找到，请检查后重新上传"},
    "E002": {"title": "文件格式错误", "message": "不支持的文件格式，请上传Excel、图片或PDF文件"},
    "E003": {"title": "文件读取失败", "message": "文件读取失败，可能是文件损坏，请重新上传"},
    "E101": {"title": "订单解析失败", "message": "无法识别订单格式，请检查订单内容或联系客服"},
    "E102": {"title": "缺少必填字段", "message": "订单中缺少必要的商品信息，请检查后重新上传"},
    "E103": {"title": "需要OCR识别", "message": "图片订单需要识别，请稍候..."},
    "E201": {"title": "门店未找到", "message": "未找到匹配门店，请确认门店名称是否正确"},
    "E202": {"title": "门店匹配需要确认", "message": "找到多个相似门店，请选择正确的门店"},
    "E301": {"title": "SKU映射失败", "message": "商品匹配失败，请检查商品名称或联系客服"},
    "E302": {"title": "商品不存在", "message": "该商品在系统中未找到，请确认商品名称"},
    "E401": {"title": "数据库连接失败", "message": "系统暂时无法处理订单，请稍后再试"},
    "E402": {"title": "数据库查询失败", "message": "查询数据时出错，请稍后再试"},
    "E999": {"title": "未知错误", "message": "系统繁忙，请稍后再试"},
}


def get_friendly_error(code: str, detail: str = "") -> Dict[str, Any]:
    """将错误码转换为用户友好的错误信息"""
    err_info = ERROR_CODES.get(code, ERROR_CODES["E999"])
    return {
        "success": False, "error_code": code,
        "error_title": err_info["title"], "error_message": err_info["message"],
        "_debug_detail": detail if os.getenv("DEBUG") else ""
    }


def wrap_error(e: Exception, code: str = "E999") -> Dict[str, Any]:
    """将异常包装为友好错误返回"""
    detail = str(e)
    if "psycopg2" in str(type(e)):
        return get_friendly_error("E401", detail)
    elif "ConnectionRefused" in str(e):
        return get_friendly_error("E401", detail)
    elif "FileNotFoundError" in str(type(e)):
        return get_friendly_error("E001", detail)
    elif "KeyError" in str(type(e)):
        return get_friendly_error("E102", detail)
    elif "IndexError" in str(type(e)):
        return get_friendly_error("E102", detail)
    elif "UnicodeDecodeError" in str(type(e)):
        return get_friendly_error("E003", detail)
    elif "PermissionError" in str(type(e)):
        return get_friendly_error("E003", detail)
    return get_friendly_error(code, detail)


def is_debug_mode() -> bool:
    return os.getenv("DEBUG", "").lower() in ["1", "true", "yes"]


# ════════════════════════════════════════════════════
# OrderToHuadingTemplate — 主类
# ════════════════════════════════════════════════════

class OrderToHuadingTemplate:
    """订单转华鼎出库单模板Skill"""

    VERSION = "5.15.4"

    # ========== AI调用约束 ==========
    __公开接口__ = ['execute']
    __内部工具__ = ['tools_parse', 'tools_transform']
    __内部初始化__ = [
        '_load_warehouse_mapping', '_load_field_mapping', '_check_db_connection', '_init_db_repos',
        '_store_matcher', '_sku_matcher', '_generator', '_parser',
        '_learning_enabled', '_current_session_id',
    ]

    REQUIRED_CONFIG = {
        "db_config": {
            "required": True,
            "description": "数据库连接配置",
            "fields": {
                "host": {"type": "string", "default": "your_db_host"},
                "port": {"type": "int", "default": "5432"},
                "database": {"type": "string", "default": "neo"},
                "user": {"type": "string", "default": "your_username"},
                "password": {"type": "string", "default": ""}
            }
        }
    }

    @classmethod
    def check_config(cls, db_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """检查Skill配置是否完整"""
        missing = []
        if not db_config:
            missing.append("db_config")
        elif not db_config.get("password"):
            missing.append("db_config.password")
        guide = "db_config 必填，需 host/port/database/user/password。支持环境变量或 .env 文件。"
        return {"ready": len(missing) == 0, "missing": missing, "setup_guide": guide}

    def __getattribute__(self, name: str):
        """拦截内部工具函数调用，防止AI跳过主入口"""
        if name.startswith('__'):
            return object.__getattribute__(self, name)
        try:
            内部工具 = object.__getattribute__(self, '__内部工具__')
        except AttributeError:
            内部工具 = []
        if name in 内部工具:
            raise OrderSkillError(code="E001",
                message=f"禁止直接调用内部函数 '{name}'，请通过 execute() 主入口调用",
                detail=f"'{name}' 是内部函数，AI 不得直接调用。正确方式：skill.execute(order_input=...)")
        if name.startswith('_'):
            try:
                公开接口 = object.__getattribute__(self, '__公开接口__')
            except AttributeError:
                公开接口 = []
            try:
                内部初始化 = object.__getattribute__(self, '__内部初始化__')
            except AttributeError:
                内部初始化 = []
            if name in 内部初始化:
                return object.__getattribute__(self, name)
            elif name not in 公开接口:
                raise OrderSkillError(code="E001",
                    message=f"禁止直接调用内部函数 '{name}'，请通过 execute() 主入口调用",
                    detail=f"'{name}' 是内部函数，AI 不得直接调用。正确方式：skill.execute(order_input=...)")
        return object.__getattribute__(self, name)

    def __init__(self, db_config: Dict[str, Any] = None, output_dir: Optional[str] = None):
        """初始化Skill配置"""
        if not db_config:
            _load_dotenv_to_environ()
            db_config = {
                "host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT", "0") or 5432),
                "database": os.getenv("DB_NAME"), "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD", "")
            }
            db_config = {
                "host": db_config.get("host") or "localhost",
                "port": int(db_config.get("port") or 5432),
                "database": db_config.get("database") or "neo",
                "user": db_config.get("user") or "your_username",
                "password": db_config.get("password", "")
            }

        config_status = self.check_config(db_config)
        if not config_status["ready"]:
            raise OrderSkillError(code="E401",
                message=f"Skill配置不完整，缺少：{', '.join(config_status['missing'])}",
                detail=config_status["setup_guide"])

        _load_dotenv_to_environ()
        _clear_proxy_env()

        self.shipper_id = None
        self.db_config = db_config
        self.output_dir = output_dir or "./output"

        # 加载仓库编码映射
        self.warehouse_code_map = object.__getattribute__(self, '_load_warehouse_mapping')()
        os.makedirs(self.output_dir, exist_ok=True)

        # ── 初始化 core/ 模块 ──
        self._store_matcher = StoreMatcher(db_config)
        self._sku_matcher = SKUMatcher(db_config)
        self._generator = TemplateGenerator(self.warehouse_code_map)
        self._parser = OrderParser()

        # ── 自学习模块软加载 ──
        self._learning_enabled = False
        if _LEARNING_ENABLED and _learning_auto_init:
            try:
                _learning_auto_init(self.db_config)
                self._learning_enabled = True
            except Exception as _e:
                print(f"[INFO] 自学习模块初始化失败（不影响主流程）: {_e}", flush=True)

    # ── 字段标准化相关（保留在类上供外部调用）──────

    FIELD_ALIAS_MAPPING = FIELD_ALIAS_MAPPING
    HUADING_FIELDS = list(HUADING_FIELDS)
    DEFAULT_VALUES = DEFAULT_VALUES

    @staticmethod
    def find_standard_field(input_name: str) -> Optional[str]:
        """将任意字段名映射到标准字段名"""
        if not input_name:
            return None
        input_name = str(input_name).strip().lower()
        for std_field, aliases in FIELD_ALIAS_MAPPING.items():
            if input_name == std_field.lower():
                return std_field
            for alias in aliases:
                if input_name == alias.lower():
                    return std_field
        return None

    def normalize_ai_result(self, raw_data: Dict) -> Tuple[Dict, List[str]]:
        return _normalize_ai_result_static(raw_data, FIELD_ALIAS_MAPPING)

    # ── 文件信息（委托给 core/generator）──────────

    get_file_info = staticmethod(get_file_info)
    prepare_file_for_send = staticmethod(prepare_file_for_send)

    # ── 仓库编码（委托给 core/generator）──────────

    def _load_warehouse_mapping(self) -> Dict[str, str]:
        """从数据库加载仓库编码映射"""
        try:
            import psycopg2
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            cur.execute("SELECT warehouse_name, warehouse_code FROM warehouse_code_mapping")
            rows = cur.fetchall()
            conn.close()
            return {name: code for name, code in rows}
        except Exception as e:
            print(f"加载仓库编码映射失败: {e}")
            return {}

    def _get_warehouse_code(self, warehouse_name: str) -> str:
        return self._generator.get_warehouse_code(warehouse_name)

    def _detect_input_type(self, order_input: str) -> str:
        if not order_input:
            return "text"
        if os.path.exists(order_input):
            ext = os.path.splitext(order_input)[1].lower()
            return {".xlsx": "excel", ".xls": "excel", ".pdf": "pdf"}.get(ext,
                   "image" if ext in [".jpg",".jpeg",".png",".bmp",".gif"] else "image")
        s = str(order_input).strip().lower()
        if s.endswith((".xlsx",".xls")): return "excel"
        if s.endswith((".jpg",".png",".jpeg")): return "image"
        if s.endswith(".pdf"): return "pdf"
        return "text" if "\n" in order_input or "门店" in order_input else "image"

    # ── 图片/PDF 处理 ──────────────────────────────

    def _parse_image(self, p):
        return {"__need_ocr__": True, "image_path": p} if p and os.path.exists(p) else None

    def _handle_ocr_result(self, r):
        return self._parser.normalize_extracted_data(r) if isinstance(r, dict) else None

    def _parse_pdf(self, p):
        return {"__need_pdf_ocr__": True, "pdf_path": p} if p and os.path.exists(p) else None

    def _handle_pdf_ocr_result(self, r):
        return self._parser.normalize_extracted_data(r) if isinstance(r, dict) else None

    def _normalize_extracted_data(self, e):
        return self._parser.normalize_extracted_data(e)

    # ── tools_parse / tools_transform（保持接口）─────

    def tools_parse(self, order_input: str, order_type: str = "auto") -> Dict[str, Any]:
        """Step 1: 调用 tools/order_parser.parse() 解析订单"""
        parse = _import_skill_attr("tools._order_parser", "parse")
        return parse(order_input, order_type=order_type)

    def tools_transform(self, order_data: Dict) -> Dict[str, Any]:
        """Step 2: 调用 tools/field_transformer.transform() 规则库标准化"""
        transform = _import_skill_attr("tools._field_transformer", "transform")
        return transform(order_data)

    # ── parse_with_llm（委托给 core/parser）─────────

    parse_with_llm = lambda self, c, t="text": self._parser.parse_with_llm(c, t)
    _excel_to_text = lambda self, df: self._parser.excel_to_text(df)
    _normalize_llm_result = lambda self, r: self._parser.normalize_llm_result(r)
    _parse_raw_text = lambda self, t: self._parser.parse_raw_text(t)
    _clean_product_name = staticmethod(clean_product_name)
    _match_sku = lambda self, items, oc: self._sku_matcher.match_batch(items, oc)
    _get_sku_unit_info = lambda self, sc, oc: self._sku_matcher.get_unit_info(sc, oc)
    _get_unit_type = lambda self, sc, oc: self._sku_matcher.get_unit_type(sc, oc)
    _generate_mapping_comparison = lambda self, *a: self._sku_matcher.generate_comparison(*a)
    _format_comparison_table_text = staticmethod(format_comparison_table_text)
    _generate_mapping_comparison_multi = lambda self, *a: self._sku_matcher.generate_comparison_multi(*a)
    _generate_template = lambda self, *a: self._generator.generate_single(*a)
    _generate_multi_store_template = lambda self, *a: self._generator.generate_multi(*a)
    _format_success_message = lambda self, *a, **kw: format_success_message(*a, **kw)

    # ── 用户反馈（委托给 learning/）─────────────────

    def _parse_user_feedback(self, user_message, mapping_result, current_order_data=None):
        if self._learning_enabled and _learning_parse_feedback:
            return _learning_parse_feedback(
                user_message, mapping_result, current_order_data,
                session_id=getattr(self, '_current_session_id', 'unknown'),
                emit_event=lambda evt, data: EventBus.emit(evt, data) if _HAS_EVENT_BUS else None,
            )
        # 内置 fallback（简化版）
        confirm_kw = ["没问题", "确认", "通过", "生成吧", "可以", "好的", "确认生成"]
        if any(kw in user_message for kw in confirm_kw):
            return {"action": "confirm", "modifications": [], "summary": "用户确认通过"}
        cancel_kw = ["取消", "算了", "不要了"]
        if any(kw in user_message for kw in cancel_kw):
            return {"action": "cancel", "modifications": [], "summary": "用户取消操作"}
        return {"action": "ask", "modifications": [], "summary": "无法理解用户反馈，请重述"}

    def _apply_modifications(self, mapping_result, modifications, sku_results=None, owner_code=""):
        if self._learning_enabled and _learning_apply_modifications:
            return _learning_apply_modifications(
                mapping_result, modifications,
                sku_results=sku_results, owner_code=owner_code,
                get_unit_info_fn=self._sku_matcher.get_unit_info,
            )
        # 内置 fallback（简化版）
        comparison_table = mapping_result["comparison_table"]
        for mod in modifications:
            row, field, new_value = mod["row"], mod["field"], mod["new_value"]
            for item in comparison_table:
                if (row == "all" or item["seq"] == row) and field in item:
                    item[field] = new_value
        return mapping_result

    # ── 旧版 Excel 解析（保留，委托给 tools）────────

    def _parse_order_excel(self, f):
        try:
            r = self.tools_parse(f, order_type="excel")
            return self.tools_transform(r) if r.get("success") else None
        except Exception:
            return None

    def _match_store(self, sn, cc=None):
        return self._store_matcher.match(sn, cc)

    # ══════════════════════════════════════════════════
    # execute() — 主编排方法（3次调用状态机）
    # ══════════════════════════════════════════════════

    def execute(self, order_input: str = None, output_file: str = None, order_type: str = "auto",
                ocr_result: Dict = None, confirmed_store: Dict = None,
                order_data_cache: Dict = None, confirmed_sku: Union[bool, Dict] = False,
                submitted_by: str = None) -> Dict[str, Any]:
        """
        执行订单转华鼎模板（支持多格式输入）

        3次调用状态机：
        1. 第1次：解析订单 → 返回 need_store_confirm（门店匹配需确认）
        2. 第2次：门店确认后 → 返回 need_sku_confirm（SKU映射需确认）
        3. 第3次：SKU确认后 → 生成模板 → 返回 success=True

        Args:
            order_input: 订单输入（文件路径/图片路径/文字内容）
            output_file: 输出文件路径
            order_type: 输入类型（"auto"/"excel"/"image"/"pdf"/"text"）
            ocr_result: 图片/PDF OCR识别结果
            confirmed_store: 用户确认的门店信息
            order_data_cache: 缓存的订单数据
            confirmed_sku: 用户确认SKU（True=确认, Dict=带修改）
            submitted_by: 提交人标识

        Returns:
            Dict: 包含 success, output_file, need_store_confirm, need_sku_confirm 等
        """
        # ── 会话 + 反馈采集器初始化 ──
        order_session_id = str(uuid.uuid4())
        self._current_session_id = order_session_id
        _started_ms = int(time.time() * 1000)
        if _HAS_EVENT_BUS and get_feedback_collector() is None:
            try:
                init_feedback_collector(self.db_config)
            except Exception as _e:
                print(f"[WARN] init_feedback_collector failed: {_e}", flush=True)

        try:
            # ── Step 1: 解析订单数据 ──
            if order_data_cache:
                order_data = order_data_cache
                extracted_from = order_data.get("_extracted_from", order_type if order_type != "auto" else "cache")
            elif order_type == "auto":
                order_type = object.__getattribute__(self, '_detect_input_type')(order_input)

            if order_data_cache:
                pass
            elif order_type == "image":
                if ocr_result:
                    order_data = object.__getattribute__(self, '_handle_ocr_result')(ocr_result)
                    extracted_from = "image"
                elif order_input:
                    parse_result = object.__getattribute__(self, '_parse_image')(order_input)
                    if parse_result and parse_result.get("__need_ocr__"):
                        return {"success": False, "need_ocr": True, "image_path": order_input,
                                "message": "图片需要OCR识别，请稍候"}
                    else:
                        order_data = parse_result
                        extracted_from = "image"
                else:
                    order_data = None
                    extracted_from = "image"
            elif order_type == "pdf":
                if ocr_result:
                    order_data = object.__getattribute__(self, '_handle_pdf_ocr_result')(ocr_result)
                    extracted_from = "pdf"
                elif order_input:
                    parse_result = object.__getattribute__(self, '_parse_pdf')(order_input)
                    if parse_result and parse_result.get("__need_pdf_ocr__"):
                        return {"success": False, "need_pdf_ocr": True, "pdf_path": order_input,
                                "message": "PDF需要OCR识别，请稍候"}
                    else:
                        order_data = parse_result
                        extracted_from = "pdf"
                else:
                    order_data = None
                    extracted_from = "pdf"
            elif order_type == "text":
                try:
                    parsed_result = object.__getattribute__(self, 'tools_parse')(order_input, order_type="text")
                    if parsed_result.get("success"):
                        order_data = parsed_result
                        order_data["_parse_method"] = "tools_parse"
                    else:
                        return {**get_friendly_error("E101", parsed_result.get("error", "订单解析失败")),
                                "extracted_from": "text"}
                except Exception as parse_err:
                    return {**get_friendly_error("E101", str(parse_err)), "extracted_from": "text"}
                try:
                    order_data = object.__getattribute__(self, 'tools_transform')(order_data)
                except Exception as transform_err:
                    order_data.setdefault("_warnings", []).append(f"规则库转换异常: {str(transform_err)}")
                extracted_from = "text"
            else:
                # excel
                if not os.path.exists(order_input):
                    return {**get_friendly_error("E001", f"文件不存在: {order_input}"),
                            "extracted_from": "excel"}
                try:
                    parsed_result = object.__getattribute__(self, 'tools_parse')(order_input, order_type="excel")
                    if parsed_result.get("success"):
                        order_data = parsed_result
                        order_data["_parse_method"] = "tools_parse"
                    else:
                        return {**get_friendly_error("E101", parsed_result.get("error", "订单解析失败")),
                                "extracted_from": "excel"}
                except Exception as parse_err:
                    return {**get_friendly_error("E101", str(parse_err)), "extracted_from": "excel"}
                try:
                    order_data = object.__getattribute__(self, 'tools_transform')(order_data)
                except Exception as transform_err:
                    order_data.setdefault("_warnings", []).append(f"规则库转换异常: {str(transform_err)}")
                extracted_from = "excel"

            if not order_data:
                return get_friendly_error("E101", f"订单解析失败（来源：{order_type}）")

            # ── Step 2: 门店匹配（委托给 core/StoreMatcher.process_all_stores）──
            confirmed_stores = merge_confirmed_store(
                order_data.get("_confirmed_stores", {}) if isinstance(order_data, dict) else {},
                confirmed_store,
            )

            def _emit(evt, data):
                if _HAS_EVENT_BUS:
                    EventBus.emit(evt, data)

            store_result = self._store_matcher.process_all_stores(
                order_data=order_data, confirmed_stores=confirmed_stores,
                sku_matcher=self._sku_matcher, session_id=order_session_id,
                emit_event=_emit)

            # 门店确认未完成 → 直接返回
            if not store_result.get("success"):
                return store_result

            all_store_results = store_result["all_store_results"]
            confirmed_stores = store_result["confirmed_stores"]

            # ── Step 3: 生成输出文件名 + 统计 ──
            if not output_file:
                raw_order_no = order_data.get("order_no", "")
                if raw_order_no and raw_order_no not in ("unknown", "", "nan", "往来单位名称", "单据日期"):
                    order_no_safe = raw_order_no.replace("/", "-").replace("\\", "-")
                else:
                    order_no_safe = f"DH-O-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
                output_file = os.path.join(self.output_dir, f"华鼎出库单_{order_no_safe}.xlsx")

            total_unmatched = sum(len(r["unmatched_items"]) for r in all_store_results)
            total_items = sum(len(r["sku_results"]) + len(r["unmatched_items"]) for r in all_store_results)
            all_unmatched = []
            for r in all_store_results:
                for it in r["unmatched_items"]:
                    it["_store"] = r["store_name"]
                    all_unmatched.append(it)

            review_data = self._sku_matcher.generate_comparison_multi(order_data, all_store_results)
            has_issues = total_unmatched > 0 or review_data["summary"]["alert_count"] > 0
            store_names = ", ".join(r["store_name"] for r in all_store_results)

            # ── SKU 确认检查 ──
            if not confirmed_sku or (total_unmatched > 0 and not isinstance(confirmed_sku, dict)):
                # 🔔 EventBus emit #7: sku_confirm_needed
                if _HAS_EVENT_BUS:
                    try:
                        _sku_items = []
                        for _sr in all_store_results:
                            for _sku in _sr.get("sku_results", []):
                                _sku_items.append({"seq": _sku.get("seq",0), "original_name": _sku.get("product_name",""),
                                    "match_layer": _sku.get("match_method",""),
                                    "match_score": float(_sku.get("confidence",0) or 0),
                                    "sku_code": _sku.get("sku_code",""), "sku_name": _sku.get("sku_name",""),
                                    "confidence": float(_sku.get("confidence",0) or 0)})
                        EventBus.emit("sku_confirm_needed", {"session_id": order_session_id, "timestamp": time.time(),
                            "items": _sku_items})
                    except Exception as _e:
                        print(f"[WARN] emit sku_confirm_needed failed: {_e}", flush=True)
                return {"success": False, "need_sku_confirm": True, "store_names": store_names,
                    "store_count": len(all_store_results), "item_count": total_items,
                    "matched_count": total_items - total_unmatched, "unmatched_count": total_unmatched,
                    "unmatched_items": all_unmatched, "review_data": review_data,
                    "all_store_results": all_store_results,
                    "order_data_cache": order_cache_with_confirmations(order_data, confirmed_stores),
                    "confirmed_stores": confirmed_stores, "proposed_output_file": output_file,
                    "message": "SKU映射结果需要确认，请检查映射对照表后继续生成模板"}

            # ── 应用用户 SKU 修正 ──
            if isinstance(confirmed_sku, dict) and "updates" in confirmed_sku:
                _applied_updates = []
                _failed_updates = []
                for update in confirmed_sku["updates"]:
                    store_key_u = update.get("store_key", "")
                    seq_u = update.get("seq", 0)
                    new_sku_code = update.get("sku_code", "")
                    if not store_key_u or not seq_u or not new_sku_code:
                        _failed_updates.append({"seq": seq_u, "store_key": store_key_u,
                            "reason": "missing_required_field",
                            "detail": f"store_key={store_key_u}, seq={seq_u}, sku_code={new_sku_code}"})
                        continue
                    _update_found = False
                    for sr in all_store_results:
                        if sr.get("store_name") != store_key_u and sr.get("store_info",{}).get("_store_key") != store_key_u:
                            continue
                        for ui_idx, ui in enumerate(sr.get("unmatched_items", [])):
                            if ui.get("seq") == seq_u:
                                sr["unmatched_items"].pop(ui_idx)
                                sr["sku_results"].append({"sku_code": new_sku_code,
                                    "sku_name": update.get("sku_name",""), "unit": update.get("unit","件"),
                                    "unit_type": update.get("unit_type",""), "quantity": ui.get("quantity",1),
                                    "product_name": ui.get("product_name",""), "match_method": "用户手动选择",
                                    "confidence": 1.0, "seq": ui.get("seq", seq_u),
                                    "spec": ui.get("spec",""), "product_spec": ui.get("spec",""),
                                    "remark": ui.get("remark",""), "original_product_name": ui.get("product_name","")})
                                sr["sku_results"].sort(key=lambda x: x.get("seq",0))
                                _applied_updates.append({"seq": seq_u, "sku_code": new_sku_code, "action": "fill_unmatched"})
                                _update_found = True
                                break
                        if _update_found:
                            break
                        for sku in sr.get("sku_results", []):
                            if sku.get("seq") == seq_u:
                                if new_sku_code: sku["sku_code"] = new_sku_code
                                if update.get("unit_type"): sku["unit_type"] = update["unit_type"]
                                if update.get("unit"): sku["unit"] = update["unit"]
                                if update.get("quantity") is not None: sku["quantity"] = update["quantity"]
                                sku["match_method"] = "用户手动修正"
                                _applied_updates.append({"seq": seq_u, "sku_code": new_sku_code, "action": "update_existing"})
                                _update_found = True
                                break
                    if not _update_found:
                        _failed_updates.append({"seq": seq_u, "store_key": store_key_u,
                            "reason": "store_key_or_seq_not_found",
                            "detail": f"store_key={store_key_u}, seq={seq_u} 未找到匹配商品"})

                if _failed_updates:
                    return {"success": False, "need_sku_confirm": True, "failed_updates": _failed_updates,
                        "applied_updates": _applied_updates,
                        "message": f"有 {len(_failed_updates)} 条修正未生效",
                        "all_store_results": all_store_results, "review_data": review_data}

                all_unmatched = []
                total_unmatched = 0
                for sr in all_store_results:
                    all_unmatched.extend(sr.get("unmatched_items", []))
                    total_unmatched += len(sr.get("unmatched_items", []))
                if total_unmatched > 0:
                    return {"success": False, "need_sku_confirm": True,
                        "message": f"仍有 {total_unmatched} 个未匹配SKU，请补齐后再继续生成模板",
                        "unmatched_count": total_unmatched, "unmatched_items": all_unmatched,
                        "all_store_results": all_store_results, "review_data": review_data}

                review_data = self._sku_matcher.generate_comparison_multi(order_data, all_store_results)
                total_items = sum(len(r["sku_results"]) + len(r["unmatched_items"]) for r in all_store_results)
                total_unmatched = sum(len(r["unmatched_items"]) for r in all_store_results)
                has_issues = total_unmatched > 0 or review_data["summary"]["alert_count"] > 0
                # 🔔 EventBus emit #8: sku_corrected
                if _HAS_EVENT_BUS:
                    try:
                        _corrected_items = [{"seq": u.get("seq",0), "original_name": u.get("product_name",""),
                            "user_corrected_to": {"sku_code": u.get("sku_code",""), "sku_name": u.get("sku_name","")},
                            "match_layer": "user_manual", "match_score": 1.0}
                            for u in confirmed_sku.get("updates", [])]
                        EventBus.emit("sku_corrected", {"session_id": order_session_id, "timestamp": time.time(),
                            "items": _corrected_items})
                    except Exception as _e:
                        print(f"[WARN] emit sku_corrected failed: {_e}", flush=True)
            elif confirmed_sku is True:
                # 🔔 EventBus emit #9: sku_confirmed
                if _HAS_EVENT_BUS:
                    try:
                        _confirmed_items = []
                        for _sr in all_store_results:
                            for _sku in _sr.get("sku_results", []):
                                _confirmed_items.append({"seq": _sku.get("seq",0), "sku_code": _sku.get("sku_code",""),
                                    "sku_name": _sku.get("sku_name",""), "match_layer": _sku.get("match_method",""),
                                    "match_score": float(_sku.get("confidence",0) or 0),
                                    "confidence": float(_sku.get("confidence",0) or 0)})
                        EventBus.emit("sku_confirmed", {"session_id": order_session_id, "timestamp": time.time(),
                            "items": _confirmed_items})
                    except Exception as _e:
                        print(f"[WARN] emit sku_confirmed failed: {_e}", flush=True)

            # ── Step 4: 生成合并模板 ──
            self._generator.generate_multi(order_data, all_store_results, output_file)

            # 同步到 media/outbound
            try:
                import shutil
                outbound_dir = os.path.expanduser("~/.openclaw/media/outbound")
                os.makedirs(outbound_dir, exist_ok=True)
                shutil.copy2(output_file, os.path.join(outbound_dir, os.path.basename(output_file)))
            except Exception as copy_err:
                print(f"[WARN] 复制到 media/outbound 失败: {copy_err}")

            friendly_msg = format_success_message(store_names, total_items,
                total_items - total_unmatched, total_unmatched,
                os.path.basename(output_file), has_issues)

            response = {
                "success": True, "need_review": True,
                "output_file": output_file, "file_name": os.path.basename(output_file),
                "download_url": get_download_url(output_file),
                "order_no": order_data.get("order_no",""),
                "store_names": store_names, "store_count": len(all_store_results),
                "item_count": total_items, "matched_count": total_items - total_unmatched,
                "unmatched_count": total_unmatched, "unmatched_items": all_unmatched,
                "extracted_from": extracted_from, "review_data": review_data,
                "has_issues": has_issues, "all_store_results": all_store_results,
                "message": friendly_msg
            }
            # 🔔 EventBus emit #10: order_complete
            if _HAS_EVENT_BUS:
                try:
                    _elapsed_ms = int(time.time() * 1000) - _started_ms
                    _first_store = (all_store_results[0] if all_store_results else {}).get("store_info", {}) or {}
                    _total_skus = sum(len(r.get("sku_results") or []) for r in all_store_results)
                    _auto_matched = max(0, _total_skus - total_unmatched)
                    EventBus.emit("order_complete", {"session_id": order_session_id, "timestamp": time.time(),
                        "order_type": order_type,
                        "store": {"store_code": _first_store.get("store_code",""),
                            "store_name": _first_store.get("store_name",""),
                            "owner_code": _first_store.get("owner_code","")},
                        "sku_summary": {"total": _total_skus, "auto_matched": _auto_matched,
                            "user_confirmed": 0, "user_corrected": 0, "unmatched": total_unmatched},
                        "match_rates": {"store_match_rate": 1.0 if confirmed_store else 0.0,
                            "sku_match_rate": (_auto_matched / _total_skus) if _total_skus else 0.0},
                        "user_modified": False, "user_confirmed": not has_issues,
                        "processing_time_ms": _elapsed_ms,
                        "skill_version": self.__class__.VERSION,
                        "owner_code": _first_store.get("owner_code",""),
                        "source_file": order_input if isinstance(order_input, str) else "",
                        "output_file": output_file, "submitted_by": submitted_by})
                except Exception as _e:
                    print(f"[WARN] emit order_complete failed: {_e}", flush=True)
            return response

        except Exception as e:
            return {**wrap_error(e, "E999"), "_error_location": "execute()"}


# ════════════════════════════════════════════════════
# 全局配置（向后兼容）
# ════════════════════════════════════════════════════

_global_config = {"shipper_id": None, "db_config": None, "output_dir": "./output"}


def configure(shipper_id: str, db_config: Dict, output_dir: Optional[str] = None):
    """配置全局参数"""
    _global_config["shipper_id"] = shipper_id
    _global_config["db_config"] = db_config
    _global_config["output_dir"] = output_dir or "./output"


def convert_order_to_huading(order_file: str, output_file: str = None) -> Dict[str, Any]:
    """将客户订单转换为华鼎出库单模板"""
    if not _global_config["shipper_id"] or not _global_config["db_config"]:
        return {"success": False, "message": "请先调用 configure() 配置全局参数"}
    skill = OrderToHuadingTemplate(db_config=_global_config["db_config"], output_dir=_global_config["output_dir"])
    return skill.execute(order_file, output_file)
