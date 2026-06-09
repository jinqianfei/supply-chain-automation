# db/table_names.py
# 表名常量（v5.11.2 统一来源，消除散落硬编码）
SKU_TABLE = "product_sku"
WAREHOUSE_TABLE = "warehouse_code_mapping"
ALIAS_TABLE = "product_name_alias"
STORE_TABLE = "store_list"

# 状态常量
ACTIVE_STATUS = "ACTIVE"

# 分页限制常量
SKU_CACHE_LIMIT = 200
SKU_MATCH_LIMIT = 20