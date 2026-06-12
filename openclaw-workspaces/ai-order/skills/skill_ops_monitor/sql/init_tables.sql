-- skill_ops_monitor 数据库初始化脚本
-- Database: neo
-- Date: 2026-05-29

-- ============================================================
-- 表 1: order_metrics（订单指标）
-- ============================================================
CREATE TABLE IF NOT EXISTS order_metrics (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           
    session_id TEXT,                  
    order_date DATE,
    order_type TEXT,                  
    store_count INT,                   
    sku_count INT,                    
    matched_sku_count INT,           
    unmatched_sku_count INT,          
    match_rate FLOAT,                 
    owner_code TEXT,                  
    output_file TEXT,                 
    processing_time_ms INT,           
    status TEXT,                      
    error_message TEXT,               
    skill_version TEXT,               
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_metrics_agent_id ON order_metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_order_metrics_order_date ON order_metrics(order_date);
CREATE INDEX IF NOT EXISTS idx_order_metrics_status ON order_metrics(status);

-- ============================================================
-- 表 2: session_traces（会话链路）
-- ============================================================
CREATE TABLE IF NOT EXISTS session_traces (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           
    session_id TEXT,                  
    order_id INT REFERENCES order_metrics(id) ON DELETE SET NULL,
    step_name TEXT,                   
    step_type TEXT,                   
    content TEXT,                     
    tool_name TEXT,                   
    tool_args JSONB,                   
    tool_result TEXT,                 
    confidence FLOAT,                
    duration_ms INT,                  
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_agent_id ON session_traces(agent_id);
CREATE INDEX IF NOT EXISTS idx_traces_session_id ON session_traces(session_id);
CREATE INDEX IF NOT EXISTS idx_traces_step_type ON session_traces(step_type);

-- ============================================================
-- 表 3: user_feedback（用户反馈）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_feedback (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           
    session_id TEXT,
    order_id INT REFERENCES order_metrics(id) ON DELETE SET NULL,
    feedback_type TEXT,              
    original_value TEXT,              
    user_value TEXT,                  
    comment TEXT,                     
    confidence FLOAT,                
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_agent_id ON user_feedback(agent_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON user_feedback(feedback_type);

-- ============================================================
-- 表 4: monitored_agents（被监控 Agent 注册表）
-- ============================================================
CREATE TABLE IF NOT EXISTS monitored_agents (
    id SERIAL PRIMARY KEY,
    agent_id TEXT UNIQUE NOT NULL,    
    agent_name TEXT,                  
    description TEXT,                
    owner_channel TEXT,              
    webhook_url TEXT,                
    notification_schedule TEXT,      
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 初始数据：AI建单助手
INSERT INTO monitored_agents (agent_id, agent_name, description, notification_schedule) 
VALUES ('ai-order', 'AI建单助手', '订单转换机器人，基于 skill_order_to_huading_template v5.3', 'daily_17:00')
ON CONFLICT (agent_id) DO NOTHING;

-- ============================================================
-- 表 5: alert_events（告警事件）
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_events (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,           
    order_id INT REFERENCES order_metrics(id) ON DELETE SET NULL,
    alert_type TEXT,                 
    severity TEXT,                   
    message TEXT,                    
    raw_data JSONB,                  
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_agent_id ON alert_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alert_events(is_resolved) WHERE is_resolved = FALSE;