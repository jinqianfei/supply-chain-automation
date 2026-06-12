"""
core/parser.py — 订单解析核心模块

职责：
1. LLM 订单解析（parse_with_llm）
2. Excel → 文本转换（_excel_to_text）
3. LLM 结果标准化（_normalize_llm_result）
4. 原始文本解析（_parse_raw_text）
5. 提取数据规范化（_normalize_extracted_data）
6. 旧版 Excel 解析（_parse_order_excel）

提取来源：__init__.py 中的解析相关方法
"""
import os
import re
import importlib
from typing import Dict, Any, Optional, List, Tuple


# ---------------------------------------------------------------------------
# 动态导入
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
# LLM 提示词模板
# ---------------------------------------------------------------------------

LLM_PARSE_PROMPT = """你是一个订单数据提取专家。请从客户订单中提取结构化信息。

【重要】一个订单可能包含多个门店，每个门店有独立的商品明细。请将所有门店都提取出来。

【输出格式】
请直接输出JSON格式（不要有其他文字）：
{{
  "confidence": 0.95,
  "stores": {{
    "门店A名称": {{
      "store_name": "门店A完整名称",
      "contact_person": "联系人姓名",
      "phone": "联系电话",
      "address": "收货地址",
      "order_no": "订单编号（如有）",
      "items": [
        {{
          "seq": 1,
          "product_name": "商品名称",
          "spec": "规格（如有）",
          "quantity": 数量,
          "unit": "单位",
          "product_code": "商品编码（如有）",
          "remark": "商品备注（如有）"
        }}
      ]
    }},
    "门店B名称": {{
      "store_name": "门店B完整名称",
      "contact_person": "...",
      "phone": "...",
      "address": "...",
      "items": [...]
    }}
  }},
  "warnings": ["告警信息"]
}}

【重要规则】
1. 一个订单文件如果包含多个门店，必须把所有门店都列在 stores 对象里
2. 每个门店的 items 只包含该门店的商品
3. 如果订单只有一个门店，仍需放在 stores 对象里（单键）
4. product_name 必须是完整商品名称，quantity 必须是数字
5. 只返回JSON，不要有其他解释文字

【订单内容】：
{content}
"""


# ---------------------------------------------------------------------------
# 字段别名映射
# ---------------------------------------------------------------------------

FIELD_ALIAS_MAPPING = {
    "store_name": ["门店", "店名", "店铺名称", "店铺", "shop", "shop_name", "name", "收货方", "客户名称", "公司名称", "客户"],
    "phone": ["电话", "手机", "联系电话", "tel", "mobile", "号码", "联系手机", "手机号"],
    "contact_person": ["联系人", "收货人", "contact", "收货人姓名", "收件人"],
    "address": ["地址", "收货地址", "配送地址", "addr", "详细地址"],
    "product_name": ["商品", "货品", "产品名", "product", "goods", "品名", "商品名称", "名称", "货品名称"],
    "quantity": ["数量", "件数", "箱数", "qty", "num", "订单数量", "订货数量"],
    "unit": ["单位", "件", "箱", "unit", "包装", "包装单位", "计量单位"],
    "spec": ["规格", "spec", "规格型号", "型号", "商品规格"],
    "product_code": ["编码", "商品编码", "SKU", "货号", "编号"],
    "remark": ["备注", "note", "备注信息"],
    "items": ["items", "商品明细", "商品列表", "订货明细", "明细"],
    "order_no": ["订单号", "单号", "订单编号", "order", "order_no", "送货单号", "单据编号"],
    "customer_company": ["客户公司", "公司名", "货主公司", "供应商", "发货方", "厂商"],
}


# ---------------------------------------------------------------------------
# OrderParser 类
# ---------------------------------------------------------------------------

class OrderParser:
    """
    订单解析器

    用法：
        parser = OrderParser()
        result = parser.parse_with_llm(content, content_type)
        normalized = parser.normalize_llm_result(llm_result)
    """

    def parse_with_llm(self, content: str, content_type: str = "text") -> Dict[str, Any]:
        """使用 LLM 解析订单内容"""
        try:
            import json

            from db.connection import _load_dotenv_to_environ
            _load_dotenv_to_environ()

            api_key = os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("未设置 MINIMAX_API_KEY 或 OPENAI_API_KEY")

            if content_type == "excel" and os.path.exists(content):
                import pandas as pd
                df = pd.read_excel(content, header=None)
                content = self.excel_to_text(df)

            prompt = LLM_PARSE_PROMPT.format(content=content[:8000] if len(content) > 8000 else content)

            if os.getenv("MINIMAX_API_KEY"):
                import openai
                client = openai.OpenAI(api_key=api_key, base_url="https://api.minimax.chat/v1")
                response = client.chat.completions.create(
                    model="MiniMax-M2.7",
                    messages=[
                        {"role": "system", "content": "你是一个专业的订单数据提取专家。请从用户提供的订单内容中准确提取结构化信息。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )
            else:
                import openai
                client = openai.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "你是一个专业的订单数据提取专家。请从用户提供的订单内容中准确提取结构化信息。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )

            raw_output = response.choices[0].message.content.strip()

            json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw_output)
            llm_data = None
            last_parse_error = ""
            for block in json_blocks:
                block = block.strip()
                if not block:
                    continue
                try:
                    llm_data = json.loads(block)
                    break
                except (json.JSONDecodeError, ValueError) as e:
                    last_parse_error = str(e)
                    continue

            if llm_data is None:
                cleaned = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL)
                cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
                cleaned = cleaned.strip()
                try:
                    llm_data = json.loads(cleaned)
                except (json.JSONDecodeError, ValueError):
                    return {
                        "success": False,
                        "error": f"LLM输出无法解析为JSON（代码块解析失败: {last_parse_error}）",
                        "llm_raw_output": raw_output[:500]
                    }

            if "stores" in llm_data:
                return {
                    "success": True,
                    "confidence": llm_data.get("confidence", 0.9),
                    "stores": llm_data.get("stores", {}),
                    "order_no": "",
                    "shipper_name": "",
                    "warehouse_name": "",
                    "warnings": llm_data.get("warnings", []),
                    "llm_raw_output": raw_output,
                }

            store_info = llm_data.get("store_info", {})
            order_info = llm_data.get("order_info", {})
            items = llm_data.get("items", [])

            store_name = store_info.get("name", "")
            for prefix in ['河北-', '天津-', '沧州-']:
                if store_name.startswith(prefix):
                    store_name = store_name[len(prefix):]
                    break

            return {
                "success": True,
                "confidence": llm_data.get("confidence", 0.9),
                "store_name": store_name,
                "contact_person": store_info.get("contact_person", ""),
                "phone": store_info.get("phone", ""),
                "address": store_info.get("address", ""),
                "order_no": order_info.get("order_no", ""),
                "shipper_name": order_info.get("shipper_name", ""),
                "warehouse_name": order_info.get("warehouse_name", ""),
                "remark": order_info.get("remark", ""),
                "items": items,
                "warnings": llm_data.get("warnings", []),
                "llm_raw_output": raw_output
            }

        except Exception as e:
            return {
                "success": False,
                "confidence": 0,
                "error": str(e),
                "store_name": "", "contact_person": "", "phone": "", "address": "",
                "order_no": "", "shipper_name": "", "warehouse_name": "", "remark": "",
                "items": [],
                "warnings": [f"LLM解析失败: {str(e)}"],
                "llm_raw_output": ""
            }

    def excel_to_text(self, df) -> str:
        """将 Excel DataFrame 转为文本描述"""
        lines = ["【Excel订单内容开始】"]
        for i in range(len(df)):
            row_data = []
            for j in range(min(len(df.columns), 10)):
                val = df.iloc[i, j]
                if val is not None and str(val) != 'nan' and str(val).strip():
                    row_data.append(str(val).strip())
            if row_data:
                lines.append(f"行{i+1}: {' | '.join(row_data)}")
        lines.append("【Excel订单内容结束】")
        return "\n".join(lines)

    def normalize_llm_result(self, llm_result: Dict) -> Dict:
        """将 LLM 解析结果转换为标准订单数据格式"""
        stores_data = llm_result.get("stores", {})
        if stores_data:
            all_items = []
            for store_key, store_data in stores_data.items():
                for idx, item in enumerate(store_data.get("items", []), start=1):
                    all_items.append({
                        "seq": item.get("seq", idx),
                        "product_code": str(item.get("product_code", "")).strip(),
                        "product_name": str(item.get("product_name", "")).strip(),
                        "spec": str(item.get("spec", "")).strip(),
                        "quantity": int(item.get("quantity", 0)),
                        "unit": str(item.get("unit", "件")).strip(),
                        "remark": str(item.get("remark", "")).strip(),
                        "_store_name": store_data.get("store_name", store_key),
                    })
            return {
                "order_no": llm_result.get("order_no", ""),
                "store_name": "",
                "stores": stores_data,
                "items": all_items,
                "_confidence": llm_result.get("confidence", 0.9),
                "_llm_warnings": llm_result.get("warnings", []),
                "_multi_store": True,
            }

        items = []
        for idx, item in enumerate(llm_result.get("items", []), start=1):
            items.append({
                "seq": item.get("seq", idx),
                "product_code": str(item.get("product_code", "")).strip(),
                "product_name": str(item.get("product_name", "")).strip(),
                "spec": str(item.get("spec", "")).strip(),
                "quantity": int(item.get("quantity", 0)),
                "unit": str(item.get("unit", "件")).strip(),
                "remark": str(item.get("remark", "")).strip()
            })

        return {
            "order_no": llm_result.get("order_no", ""),
            "store_name": llm_result.get("store_name", ""),
            "contact_person": llm_result.get("contact_person", ""),
            "phone": llm_result.get("phone", ""),
            "address": llm_result.get("address", ""),
            "shipper_name": llm_result.get("shipper_name", ""),
            "warehouse_name": llm_result.get("warehouse_name", ""),
            "remark": llm_result.get("remark", ""),
            "items": items,
            "_confidence": llm_result.get("confidence", 0.9),
            "_llm_warnings": llm_result.get("warnings", []),
            "_llm_raw_output": llm_result.get("llm_raw_output", ""),
            "_multi_store": False,
        }

    def parse_raw_text(self, text: str) -> Optional[Dict]:
        """解析原始粘贴文本"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        warnings = []
        order_no = ""
        store_name = ""
        contact_person = ""
        phone = ""
        address = ""
        items = []
        matched_fields = set()

        for line in lines:
            if not line or line.startswith("#"):
                continue
            line_matched = False
            for std_field, aliases in FIELD_ALIAS_MAPPING.items():
                if std_field == "items":
                    continue
                for alias in aliases:
                    if line.startswith(alias):
                        value = line[len(alias):]
                        value = re.sub(r'^[\s：:,，、]+', '', value)
                        if std_field == "store_name" and not store_name:
                            store_name = value
                            matched_fields.add("store_name")
                            warnings.append(f"文本字段'{alias}'→'store_name'")
                            line_matched = True
                        elif std_field == "order_no" and not order_no:
                            order_no = value
                            matched_fields.add("order_no")
                            line_matched = True
                        elif std_field == "contact_person" and not contact_person:
                            contact_person = value
                            matched_fields.add("contact_person")
                            line_matched = True
                        elif std_field == "phone" and not phone:
                            phone = value
                            matched_fields.add("phone")
                            line_matched = True
                        elif std_field == "address" and not address:
                            address = value
                            matched_fields.add("address")
                            line_matched = True
                        if line_matched:
                            break
                if line_matched:
                    break
            if line_matched:
                continue

            from .store_matcher import _import_skill_attr as _imp
            _parse_item_row = _imp("__init__", "_parse_item_row") if False else None
            # Inline fallback for _parse_item_row
            item_result = _parse_item_row_inline(line)
            if item_result:
                items.append({
                    "seq": len(items) + 1,
                    "product_code": item_result.get("product_code", ""),
                    "product_name": item_result["product_name"],
                    "spec": item_result.get("spec", ""),
                    "quantity": item_result["quantity"],
                    "unit": item_result.get("unit", "件"),
                    "remark": item_result.get("remark", "")
                })
                continue

            if re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]{4,}$', line):
                if not store_name and "store_name" not in matched_fields:
                    store_name = line
                    warnings.append(f"推断门店名: '{line}'")

        for prefix in ['河北-', '天津-', '沧州-']:
            if store_name.startswith(prefix):
                store_name = store_name[len(prefix):]
                break

        if not store_name and not items:
            warnings.append("未能从文本中提取到门店名和商品明细")

        return {
            "order_no": order_no,
            "store_name": store_name,
            "contact_person": contact_person,
            "phone": phone,
            "address": address,
            "items": items,
            "_norm_warnings": warnings
        }

    def normalize_extracted_data(self, extracted: Dict) -> Optional[Dict]:
        """规范化从 OCR/文本提取的数据"""
        raw_text = extracted.get("raw_text", "")
        if raw_text:
            return self.parse_raw_text(raw_text)

        normalized_fields, norm_warnings = _normalize_ai_result_static(extracted)

        if not normalized_fields.get("store_name") and not extracted.get("items"):
            if not normalized_fields:
                normalized_fields = {k: v for k, v in extracted.items()
                                     if not k.startswith("__") and k != "raw_text"}

        order_no = str(normalized_fields.get("order_no", extracted.get("order_no", ""))).strip()
        store_name = str(normalized_fields.get("store_name", extracted.get("store_name", ""))).strip()

        for prefix in ['河北-', '天津-', '沧州-']:
            if store_name.startswith(prefix):
                store_name = store_name[len(prefix):]
                break

        items_raw = normalized_fields.get("items", extracted.get("items", []))
        items = []
        for idx, item in enumerate(items_raw if isinstance(items_raw, list) else [], start=1):
            if not isinstance(item, dict):
                continue
            product_name = None
            for pn_key in ["product_name", "product", "goods", "name", "品名"]:
                if pn_key in item:
                    product_name = str(item.get(pn_key, "")).strip()
                    break
            if not product_name or product_name == "nan":
                continue
            qty = None
            for qty_key in ["quantity", "qty", "num", "数量"]:
                if qty_key in item:
                    qty = item.get(qty_key, 0)
                    break
            if qty is None:
                qty = 0
            if isinstance(qty, str):
                qty = int(float(re.sub(r'[^0-9.]', '', qty)))
            qty = int(qty) if qty else 0
            items.append({
                "seq": item.get("seq", idx),
                "product_code": str(item.get("product_code", item.get("code", ""))).strip(),
                "product_name": product_name,
                "spec": str(item.get("spec", item.get("规格", ""))).strip(),
                "quantity": qty,
                "unit": str(item.get("unit", item.get("单位", "件"))).strip(),
                "remark": str(item.get("remark", item.get("note", ""))).strip()
            })

        if not store_name and not items:
            return None

        customer_company = str(normalized_fields.get("customer_company", extracted.get("customer_company", ""))).strip()

        return {
            "order_no": order_no,
            "store_name": store_name,
            "contact_person": str(normalized_fields.get("contact_person", extracted.get("contact_person", ""))).strip(),
            "phone": str(normalized_fields.get("phone", extracted.get("phone", ""))).strip(),
            "address": str(normalized_fields.get("address", extracted.get("address", ""))).strip(),
            "items": items,
            "customer_company": customer_company,
            "_norm_warnings": norm_warnings
        }


# ---------------------------------------------------------------------------
# 静态辅助函数（从 __init__.py 提取）
# ---------------------------------------------------------------------------

def _is_sku_code(s: str) -> bool:
    """判断字符串是否像商品编码"""
    return bool(re.match(r'^[A-Z][A-Z0-9]{2,}$', s))


def _parse_item_row_inline(line: str) -> Optional[Dict]:
    """解析订单商品行（内联版本）"""
    parts = line.split()
    if len(parts) < 2:
        return None
    n = len(parts)
    i = n - 1
    unit = "件"
    quantity = 1
    while i >= 0:
        p = parts[i]
        if re.match(r'^\d+$', p):
            quantity = int(p)
            i -= 1
            if i >= 0 and parts[i] in ["箱", "件", "袋", "包", "个", "瓶", "桶", "条", "盒", "台"]:
                unit = parts[i]
                i -= 1
            break
        elif p in ["箱", "件", "袋", "包", "个", "瓶", "桶", "条", "盒", "台"]:
            unit = p
            i -= 1
            continue
        else:
            i -= 1
            continue
    remaining = parts[1:i+1]
    has_sku_code = len(remaining) > 0 and _is_sku_code(remaining[0])
    if has_sku_code:
        product_code = remaining[0]
        product_name = remaining[1] if len(remaining) > 1 else remaining[0]
        spec = " ".join(remaining[2:]) if len(remaining) > 2 else ""
    else:
        product_code = ""
        product_name = remaining[0] if remaining else ""
        spec = " ".join(remaining[1:]) if len(remaining) > 1 else ""
    if not product_name or len(product_name) <= 1:
        item_match = re.match(r'^[\-\*\d]+[\.、\s]+(.+?)(?:\s+(\d+)\s*[\u4e00-\u9fa5件个箱袋台]?)?$', line)
        if item_match:
            return {
                "product_name": item_match.group(1).strip(),
                "spec": "", "quantity": int(item_match.group(2)) if item_match.group(2) else 1,
                "unit": "件", "remark": "", "product_code": ""
            }
    return {
        "product_name": product_name, "spec": spec,
        "quantity": quantity, "unit": unit,
        "remark": "", "product_code": product_code
    }


def _normalize_ai_result_static(raw_data: Dict, alias_mapping: Dict = None) -> Tuple[Dict, List[str]]:
    """AI 返回的字段名标准化（静态版本）"""
    if alias_mapping is None:
        alias_mapping = FIELD_ALIAS_MAPPING
    normalized = {}
    warnings = []
    unknown_fields = []
    for ai_field_name, value in raw_data.items():
        if ai_field_name.startswith("__") or ai_field_name in ["raw_text"]:
            continue
        std_field = None
        ai_lower = ai_field_name.strip().lower()
        for std, aliases in alias_mapping.items():
            if ai_lower == std.lower():
                std_field = std
                break
            for alias in aliases:
                if ai_lower == alias.lower():
                    std_field = std
                    break
            if std_field:
                break
        if std_field:
            normalized[std_field] = value
            if std_field != ai_field_name and ai_field_name.lower() != std_field.lower():
                warnings.append(f"字段名'{ai_field_name}'→'{std_field}'")
        else:
            unknown_fields.append(ai_field_name)
    if unknown_fields:
        warnings.append(f"未知字段名{len(unknown_fields)}个，已忽略: {', '.join(unknown_fields[:5])}")
    return normalized, warnings


# Keep _parse_item_row as module-level for backward compat
_parse_item_row = _parse_item_row_inline
