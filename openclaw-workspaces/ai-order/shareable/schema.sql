-- =============================================================
-- skill_order_to_huading_template v5.11.1 数据库 Schema
-- PostgreSQL >= 12 (建议 14+)
-- 适用: 客户订单 → 华鼎出库单 转换场景
-- =============================================================

-- 启用 trgm 扩展（用于 GIN 模糊搜索索引）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================
-- 1. product_sku (SKU 主表)
-- =============================================================
CREATE TABLE IF NOT EXISTS product_sku (
    sku_code VARCHAR(50) NOT NULL,
    customer_code VARCHAR(50),
    sku_name VARCHAR(200) NOT NULL,
    product_spec VARCHAR(200),
    unit VARCHAR(20),
    unit_type VARCHAR(20),          -- 大单位/小单位
    conversion_ratio NUMERIC(10,2),  -- 换算比
    shipper_id VARCHAR(20) NOT NULL, -- 货主 ID
    category VARCHAR(50),
    warehouse_code VARCHAR(20),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sku_code, shipper_id)
);
CREATE INDEX IF NOT EXISTS idx_product_sku_sku_name_trgm
    ON product_sku USING GIN (sku_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_product_sku_shipper_id
    ON product_sku (shipper_id);
CREATE INDEX IF NOT EXISTS idx_product_sku_customer_code
    ON product_sku (customer_code);

-- =============================================================
-- 2. product_name_alias (商品名别名)
-- =============================================================
CREATE TABLE IF NOT EXISTS product_name_alias (
    order_product_name VARCHAR(200) NOT NULL,
    system_product_name VARCHAR(200) NOT NULL,
    shipper_id VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_product_name, shipper_id)
);
CREATE INDEX IF NOT EXISTS idx_product_name_alias_order_name_trgm
    ON product_name_alias USING GIN (order_product_name gin_trgm_ops);

-- =============================================================
-- 3. store_list (门店列表)
-- =============================================================
CREATE TABLE IF NOT EXISTS store_list (
    id SERIAL PRIMARY KEY,
    store_code VARCHAR(50) UNIQUE,
    store_name VARCHAR(200) NOT NULL,
    store_status VARCHAR(20) DEFAULT 'ACTIVE',
    owner_code VARCHAR(20),         -- 货主 ID
    owner_name VARCHAR(200),
    owner_level VARCHAR(20),
    third_party_code VARCHAR(50),
    province VARCHAR(50),
    city VARCHAR(50),
    district VARCHAR(50),
    address TEXT,
    phone VARCHAR(50),
    contact_person VARCHAR(50),
    warehouse VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_store_list_store_name_trgm
    ON store_list USING GIN (store_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_store_list_owner_code
    ON store_list (owner_code);

-- =============================================================
-- 4. warehouse_code_mapping (仓库编码)
-- =============================================================
CREATE TABLE IF NOT EXISTS warehouse_code_mapping (
    id SERIAL PRIMARY KEY,
    warehouse_name VARCHAR(100) NOT NULL,
    warehouse_code VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_warehouse_code_mapping_code
    ON warehouse_code_mapping (warehouse_code);

-- =============================================================
-- 5. customer (货主信息)
-- =============================================================
CREATE TABLE IF NOT EXISTS customer (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) UNIQUE NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    customer_type VARCHAR(50),
    contact_person VARCHAR(50),
    contact_phone VARCHAR(50),
    address TEXT,
    warehouse_code VARCHAR(20),
    warehouse_name VARCHAR(100),
    delivery_type VARCHAR(20),
    default_region VARCHAR(50),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_customer_customer_id
    ON customer (customer_id);

-- =============================================================
-- 完成
-- =============================================================
-- 接下来导入你的数据:
--   \COPY product_sku FROM 'product_sku.csv' WITH (FORMAT csv, HEADER true);
--   \COPY product_name_alias FROM 'product_name_alias.csv' WITH (FORMAT csv, HEADER true);
--   \COPY store_list FROM 'store_list.csv' WITH (FORMAT csv, HEADER true);
--   \COPY warehouse_code_mapping FROM 'warehouse_code_mapping.csv' WITH (FORMAT csv, HEADER true);
--   \COPY customer FROM 'customer.csv' WITH (FORMAT csv, HEADER true);
