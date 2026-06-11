-- AI建单助手自适应学习系统 - Phase 1 数据库表
-- Feedback Collector 数据层
-- 执行方式: psql -d neo -f schema.sql

-- ============================================================
-- order_feedback：订单处理反馈主表
-- ============================================================
CREATE TABLE IF NOT EXISTS order_feedback (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    order_date DATE DEFAULT CURRENT_DATE,
    order_type TEXT CHECK (order_type IN ('excel', 'image', 'pdf', 'word', 'text', 'auto')),
    store_count INT DEFAULT 0,
    sku_count INT DEFAULT 0,
    matched_store_count INT DEFAULT 0,
    matched_sku_count INT DEFAULT 0,
    store_match_rate FLOAT DEFAULT 0 CHECK (store_match_rate >= 0 AND store_match_rate <= 1),
    sku_match_rate FLOAT DEFAULT 0 CHECK (sku_match_rate >= 0 AND sku_match_rate <= 1),
    user_confirmed BOOLEAN DEFAULT FALSE,
    user_modified BOOLEAN DEFAULT FALSE,
    corrections JSONB DEFAULT '[]',
    modifications JSONB DEFAULT '[]',
    processing_time_ms INT DEFAULT 0,
    skill_version TEXT,
    owner_code TEXT,
    source_file TEXT,
    output_file TEXT,
    data_source TEXT DEFAULT 'event_bus',
    alerts JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE order_feedback IS '订单处理反馈主表 - 记录每次处理的完整反馈数据';
COMMENT ON COLUMN order_feedback.order_type IS '订单类型：excel/image/pdf/word/text/auto';
COMMENT ON COLUMN order_feedback.user_confirmed IS '用户是否最终确认（无拒绝）';
COMMENT ON COLUMN order_feedback.user_modified IS '用户是否有修改（门店或SKU）';
COMMENT ON COLUMN order_feedback.corrections IS '[{type, original_*, corrected_*, layer, score}] 纠正详情';
COMMENT ON COLUMN order_feedback.modifications IS '[{row, field, old_value, new_value}] 字段修改详情';

CREATE INDEX IF NOT EXISTS idx_feedback_order_date ON order_feedback(order_date);
CREATE INDEX IF NOT EXISTS idx_feedback_skill_version ON order_feedback(skill_version);
CREATE INDEX IF NOT EXISTS idx_feedback_owner ON order_feedback(owner_code);
CREATE INDEX IF NOT EXISTS idx_feedback_session ON order_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON order_feedback(created_at DESC);

ALTER TABLE order_feedback ADD COLUMN IF NOT EXISTS output_file TEXT;
ALTER TABLE order_feedback ADD COLUMN IF NOT EXISTS data_source TEXT DEFAULT 'event_bus';
ALTER TABLE order_feedback ADD COLUMN IF NOT EXISTS submitted_by TEXT;

-- ============================================================
-- order_corrections：用户纠正记录（结构化）
-- ============================================================
CREATE TABLE IF NOT EXISTS order_corrections (
    id SERIAL PRIMARY KEY,
    feedback_id INT REFERENCES order_feedback(id) ON DELETE CASCADE,
    correction_type TEXT CHECK (correction_type IN ('store', 'sku', 'unit', 'quantity', 'spec', 'store_name', 'sku_code', 'huading_unit', 'unit_type')),
    entity_name TEXT,
    original_value TEXT,
    corrected_value TEXT,
    match_layer TEXT,
    match_score FLOAT,
    auto_matched BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE order_corrections IS '用户纠正记录 - 每条纠正一条记录';
COMMENT ON COLUMN order_corrections.correction_type IS '纠正类型：store(门店)/sku(sku)/unit(单位)/quantity(数量)/spec(规格)';
COMMENT ON COLUMN order_corrections.entity_name IS '被纠正的实体名称（商品名或门店名）';
COMMENT ON COLUMN order_corrections.auto_matched IS '原始是否自动匹配（True=匹配后被纠正，False=未匹配）';

CREATE INDEX IF NOT EXISTS idx_corrections_feedback ON order_corrections(feedback_id);
CREATE INDEX IF NOT EXISTS idx_corrections_type ON order_corrections(correction_type);
CREATE INDEX IF NOT EXISTS idx_corrections_entity ON order_corrections(entity_name);
CREATE INDEX IF NOT EXISTS idx_corrections_created ON order_corrections(created_at DESC);

-- ============================================================
-- layer_success_rate：匹配层成功率统计
-- ============================================================
CREATE TABLE IF NOT EXISTS layer_success_rate (
    id SERIAL PRIMARY KEY,
    entity_type TEXT CHECK (entity_type IN ('store', 'sku')),
    layer_name TEXT,
    layer_description TEXT,
    total_attempts INT DEFAULT 0,
    success_count INT DEFAULT 0,
    auto_success_count INT DEFAULT 0,
    user_corrected_count INT DEFAULT 0,
    success_rate FLOAT DEFAULT 0 CHECK (success_rate >= 0 AND success_rate <= 1),
    avg_match_score FLOAT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (entity_type, layer_name)
);

COMMENT ON TABLE layer_success_rate IS '匹配层成功率统计 - 动态计算各层的实际成功率';
COMMENT ON COLUMN layer_success_rate.total_attempts IS '该层总尝试次数';
COMMENT ON COLUMN layer_success_rate.success_count IS '用户直接确认（无修改）次数';
COMMENT ON COLUMN layer_success_rate.auto_success_count IS '自动确认（相似度>=90%）次数';
COMMENT ON COLUMN layer_success_rate.user_corrected_count IS '被用户纠正次数';

CREATE INDEX IF NOT EXISTS idx_layer_entity ON layer_success_rate(entity_type);

-- ============================================================
-- 初始化层统计基础数据（5层SKU + 6层门店）
-- ============================================================
INSERT INTO layer_success_rate (entity_type, layer_name, layer_description, total_attempts, success_count, auto_success_count, user_corrected_count, success_rate)
VALUES
    ('store', 'layer_1', '精确匹配（门店全名）', 0, 0, 0, 0, 0),
    ('store', 'layer_2', '前缀/后缀匹配', 0, 0, 0, 0, 0),
    ('store', 'layer_3', '模糊匹配（相似度）', 0, 0, 0, 0, 0),
    ('store', 'layer_4', '关键词匹配', 0, 0, 0, 0, 0),
    ('store', 'layer_5', '地址/电话辅助匹配', 0, 0, 0, 0, 0),
    ('store', 'layer_6', '兜底（无匹配时强制）', 0, 0, 0, 0, 0),
    ('sku',   'layer_1', '精确匹配（SKU编码）', 0, 0, 0, 0, 0),
    ('sku',   'layer_2', '清理后精确匹配', 0, 0, 0, 0, 0),
    ('sku',   'layer_3', '别名表匹配', 0, 0, 0, 0, 0),
    ('sku',   'layer_4', '规格匹配', 0, 0, 0, 0, 0),
    ('sku',   'layer_5', '兜底匹配（模糊相似度）', 0, 0, 0, 0, 0)
ON CONFLICT (entity_type, layer_name) DO NOTHING;

-- ============================================================
-- 视图：每日统计
-- ============================================================
CREATE OR REPLACE VIEW v_daily_feedback_stats AS
SELECT
    order_date,
    COUNT(*) as total_orders,
    AVG(store_match_rate) as avg_store_match_rate,
    AVG(sku_match_rate) as avg_sku_match_rate,
    AVG(processing_time_ms) as avg_processing_time_ms,
    SUM(CASE WHEN user_confirmed THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as confirm_rate,
    SUM(CASE WHEN user_modified THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as modify_rate,
    AVG(JSONB_ARRAY_LENGTH(corrections)) as avg_corrections
FROM order_feedback
GROUP BY order_date
ORDER BY order_date DESC;

-- ============================================================
-- 视图：层成功率（实时）
-- ============================================================
CREATE OR REPLACE VIEW v_layer_success_rate AS
SELECT
    entity_type,
    layer_name,
    layer_description,
    total_attempts,
    success_count,
    auto_success_count,
    user_corrected_count,
    CASE WHEN total_attempts > 0
         THEN (success_count + auto_success_count)::FLOAT / total_attempts
         ELSE 0 END as success_rate,
    avg_match_score
FROM layer_success_rate
ORDER BY entity_type, layer_name;
