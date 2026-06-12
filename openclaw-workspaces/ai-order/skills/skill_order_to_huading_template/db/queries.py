"""
SQL 查询集中管理模块

所有 SQL 查询字符串按功能分组，统一维护。
表名使用 db.table_names 中的常量进行格式化。

提取来源：
- __init__.py（门店匹配、仓库货主、单位推断）
- tools/_store_matcher.py（门店匹配 6 层）
- tools/_sku_mapper.py（SKU 映射 6 层）
- tools/_template_generator.py（仓库编码查询）
- db/store_repo.py（门店 CRUD）
- db/sku_repo.py（SKU CRUD）
- db/customer_repo.py（货主 CRUD）
"""

from db.table_names import (
    SKU_TABLE,
    WAREHOUSE_TABLE,
    ALIAS_TABLE,
    STORE_TABLE,
    ACTIVE_STATUS,
    SKU_CACHE_LIMIT,
    SKU_MATCH_LIMIT,
)


# ===================================================================
# 门店匹配 SQL
# ===================================================================

# --- store_repo.py ---

# 按名称模糊匹配门店
STORE_FIND_BY_NAME = f"""
    SELECT store_code, store_name, owner_code, owner_name,
           province, city, district, address, phone, contact_person,
           warehouse
    FROM {STORE_TABLE}
    WHERE store_name LIKE %s
"""

# 按门店编码精确查询
STORE_GET_BY_CODE = f"""
    SELECT store_code, store_name, owner_code, owner_name,
           province, city, district, address, phone, contact_person,
           warehouse
    FROM {STORE_TABLE}
    WHERE store_code = %s
"""

# 按货主ID查询所有门店
STORE_GET_BY_OWNER = f"""
    SELECT store_code, store_name, owner_code, owner_name,
           province, city, district, address, phone, contact_person,
           warehouse
    FROM {STORE_TABLE}
    WHERE owner_code = %s
    LIMIT 20
"""

# 按手机号精确查询门店
STORE_FIND_BY_PHONE = f"""
    SELECT store_code, store_name, owner_code, owner_name,
           province, city, district, address, phone, contact_person,
           warehouse
    FROM {STORE_TABLE}
    WHERE phone = %s
    LIMIT 1
"""

# --- _store_matcher.py ---

# 关键词搜索门店编码（分词匹配）
STORE_SEARCH_CODES_BY_KEYWORD = f"""
    SELECT store_code FROM {STORE_TABLE} WHERE store_name LIKE %s
"""

# 按门店编码批量查询（动态 placeholders）
STORE_GET_BY_CODES = f"""
    SELECT store_code, store_name, owner_name, owner_code, phone, address, warehouse
    FROM {STORE_TABLE} WHERE store_code IN ({{placeholders}})
"""

# --- __init__.py 门店匹配 ---

# 精确匹配门店名
STORE_EXACT_MATCH = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE store_name = %s
    LIMIT 1
"""

# 门店名 LIKE 模糊匹配
STORE_FUZZY_MATCH = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE store_name LIKE %s
    LIMIT 50
"""

# 关键词拆分后逐个 LIKE 查询
STORE_KEYWORD_MATCH = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE store_name LIKE %s
    LIMIT 20
"""

# 按 owner_code 查门店（客户公司匹配后取门店）
STORE_BY_OWNER_CODE = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE owner_code = %s
    LIMIT 1
"""

# 按 owner_code 查门店（多结果）
STORE_BY_OWNER_CODE_MULTI = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE owner_code = %s
    LIMIT 5
"""

# 仓库名精确匹配 owner_code（品牌+仓库名匹配策略）
STORE_FIND_OWNER_BY_WAREHOUSE = f"""
    SELECT DISTINCT owner_code, warehouse
    FROM {STORE_TABLE}
    WHERE warehouse = %s AND owner_code IS NOT NULL AND owner_code != ''
"""

# 仓库名 + 货主ID 查门店
STORE_BY_WAREHOUSE_AND_OWNER = f"""
    SELECT store_code, store_name, warehouse, address, contact_person, phone, owner_code
    FROM {STORE_TABLE}
    WHERE warehouse = %s AND owner_code = %s
    LIMIT 5
"""


# ===================================================================
# 货主/客户查询 SQL
# ===================================================================

# --- customer_repo.py ---

# 按货主ID查询
CUSTOMER_GET_BY_ID = """
    SELECT customer_id, customer_name, customer_type, contact_person,
           contact_phone, address, warehouse_name, status
    FROM customer
    WHERE customer_id = %s
"""

# 按名称模糊搜索货主
CUSTOMER_SEARCH_BY_NAME = f"""
    SELECT customer_id, customer_name, customer_type, contact_person,
           contact_phone, address, warehouse_name, status
    FROM customer
    WHERE status = '{ACTIVE_STATUS}' AND customer_name LIKE %s
    ORDER BY customer_name
    LIMIT 10
"""

# --- __init__.py 货主匹配 ---

# 客户公司名 LIKE 查询（取 owner_code）
CUSTOMER_COMPANY_MATCH = f"""
    SELECT customer_id, customer_name, warehouse_name
    FROM customer
    WHERE status = '{ACTIVE_STATUS}' AND customer_name LIKE %s
    LIMIT 5
"""

# 品牌名查货主（品牌映射匹配）
CUSTOMER_BRAND_MATCH = f"""
    SELECT customer_id, customer_name
    FROM customer
    WHERE status = '{ACTIVE_STATUS}' AND customer_name LIKE %s
    LIMIT 5
"""

# 品牌名查货主（无 LIMIT）
CUSTOMER_BRAND_MATCH_NO_LIMIT = f"""
    SELECT customer_id, customer_name
    FROM customer
    WHERE status = '{ACTIVE_STATUS}' AND customer_name LIKE %s
"""

# 按 owner_id 列表反查货主
CUSTOMER_GET_BY_IDS = f"""
    SELECT customer_id, customer_name
    FROM customer
    WHERE status = '{ACTIVE_STATUS}' AND customer_id = ANY(%s)
"""

# 搜索所有活跃货主（相似度匹配用）
CUSTOMER_ALL_ACTIVE = f"""
    SELECT customer_id, customer_name, warehouse_name, status
    FROM customer
    WHERE status = '{ACTIVE_STATUS}'
    LIMIT 20
"""


# ===================================================================
# SKU 匹配 SQL
# ===================================================================

# --- sku_repo.py（原 shipper_sku_mapping 表，已合并到 product_sku）---

# 按货主ID和关键词模糊匹配SKU（旧表 shipper_sku_mapping，保留兼容）
SKU_FIND_BY_KEYWORD_LEGACY = """
    SELECT id, shipper_id, shipper_name,
           customer_sku_code, customer_sku_name,
           system_sku_code, system_sku_name,
           unit_conversion_rule, confidence, status
    FROM shipper_sku_mapping
    WHERE shipper_id = %s AND customer_sku_name LIKE %s
    ORDER BY LENGTH(customer_sku_name) ASC
"""

# 按货主ID和客户SKU编码精确匹配（旧表）
SKU_FIND_BY_CODE_LEGACY = """
    SELECT id, shipper_id, shipper_name,
           customer_sku_code, customer_sku_name,
           system_sku_code, system_sku_name,
           unit_conversion_rule, confidence, status
    FROM shipper_sku_mapping
    WHERE shipper_id = %s AND customer_sku_code = %s
"""

# 获取某个货主的所有SKU映射（旧表）
SKU_ALL_BY_SHIPPER_LEGACY = f"""
    SELECT id, shipper_id, shipper_name,
           customer_sku_code, customer_sku_name,
           system_sku_code, system_sku_name,
           unit_conversion_rule, confidence, status
    FROM shipper_sku_mapping
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
    ORDER BY customer_sku_name
"""

# --- _sku_mapper.py（product_sku 表）---

# Layer 0: 别名表 JOIN 查询（精确匹配订单商品名）
SKU_ALIAS_EXACT = f"""
    SELECT p.sku_code, p.sku_name, p.unit, p.unit_type, p.conversion_ratio, p.product_spec, p.customer_code
    FROM {ALIAS_TABLE} a
    JOIN {SKU_TABLE} p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
    WHERE a.shipper_id = %s AND a.order_product_name = %s
"""

# Layer 1: 精确匹配（原始名称 — sku_name 或 customer_code）
SKU_EXACT_MATCH = f"""
    SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
    FROM {SKU_TABLE}
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
      AND (sku_name = %s OR customer_code = %s)
"""

# Layer 1b: 精确匹配（清洗后名称）— 与 Layer 1 相同 SQL，不同参数
# 复用 SKU_EXACT_MATCH

# Layer 2: 模糊匹配（LIKE 查询 + 规格校验）
SKU_FUZZY_MATCH = f"""
    SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
    FROM {SKU_TABLE}
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
      AND sku_name LIKE %s
    LIMIT {SKU_MATCH_LIMIT}
"""

# Layer 2.5: 全量加载（内存中做相似度匹配）
SKU_LOAD_ALL_ACTIVE = f"""
    SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
    FROM {SKU_TABLE}
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
    LIMIT {SKU_CACHE_LIMIT}
"""

# Layer 2.5 变体（无 LIMIT，用于 SKUCache 批量加载）
SKU_LOAD_ALL_ACTIVE_NO_LIMIT = f"""
    SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
    FROM {SKU_TABLE}
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
"""

# Layer 3: 分词关键词匹配
SKU_KEYWORD_MATCH = f"""
    SELECT sku_code, sku_name, unit, unit_type, conversion_ratio, product_spec, customer_code
    FROM {SKU_TABLE}
    WHERE shipper_id = %s AND status = '{ACTIVE_STATUS}'
      AND sku_name LIKE %s
    LIMIT {SKU_MATCH_LIMIT}
"""

# 别名表全量加载（批量映射用）
SKU_ALIAS_LOAD_ALL = f"""
    SELECT a.order_product_name, p.sku_code, p.sku_name, p.unit, p.unit_type,
           p.conversion_ratio, p.product_spec, p.customer_code
    FROM {ALIAS_TABLE} a
    JOIN {SKU_TABLE} p ON p.sku_name = a.system_product_name AND p.shipper_id = a.shipper_id
    WHERE a.shipper_id = %s
"""

# --- __init__.py 单位推断 ---

# 用 sku_code 查 SKU 信息（单位推断 Step 1）
SKU_GET_BY_CODE_AND_OWNER = f"""
    SELECT sku_name, unit, unit_type, conversion_ratio
    FROM {SKU_TABLE}
    WHERE sku_code = %s AND shipper_id = %s
    LIMIT 1
"""

# 找同名 SKU（单位推断 Step 2）
SKU_GET_SAME_NAME = f"""
    SELECT sku_code, conversion_ratio, unit
    FROM {SKU_TABLE}
    WHERE sku_name = %s AND shipper_id = %s
"""


# ===================================================================
# 仓库编码 SQL
# ===================================================================

# --- _template_generator.py ---

# 按仓库名查仓库编码
WAREHOUSE_GET_CODE = f"""
    SELECT warehouse_code FROM {WAREHOUSE_TABLE}
    WHERE warehouse_name = %s
"""

# --- __init__.py ---

# 加载全部仓库编码映射
WAREHOUSE_LOAD_ALL = f"""
    SELECT warehouse_name, warehouse_code FROM {WAREHOUSE_TABLE}
"""
