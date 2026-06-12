"""
core/ — 核心业务逻辑模块（Phase 3 重构）

将 __init__.py 中的三大核心功能提取为独立模块：
- StoreMatcher: 门店匹配（含确认状态管理）
- SKUMatcher: SKU 映射（含单位推断）
- TemplateGenerator: 模板生成 + 映射对照表
- OrderParser: 订单解析（LLM + 文本 + Excel）
"""
from .store_matcher import StoreMatcher
from .sku_matcher import SKUMatcher
from .generator import TemplateGenerator
from .parser import OrderParser

__all__ = ["StoreMatcher", "SKUMatcher", "TemplateGenerator", "OrderParser"]
