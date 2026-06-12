"""
skill_ops_monitor 配置
"""

# 数据库配置（neo 数据库）
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "neo",
    "user": "jinqianfei"
}

# 被监控 Agent 注册表
AGENT_REGISTRY = {
    "ai-order": {
        "agent_name": "AI建单助手",
        "description": "订单转换机器人，基于 skill_order_to_huading_template v5.8",
        "skill_version": "v5.8",
        "notification_schedule": "daily_17:00",
        "owner_channel": None  # 飞书 open_id，后续配置
    }
}

# 告警阈值配置
ALERT_THRESHOLDS = {
    "low_match_rate": {
        "critical": 0.50,   # <50% 严重
        "high": 0.70,      # <70% 高
        "medium": 0.80,    # <80% 中
    },
    "processing_timeout_ms": {
        "high": 300000,    # >5分钟 高
        "medium": 180000,  # >3分钟 中
    },
    "max_user_rejects": 2   # 连续2次拒绝 触发告警
}

# 报表配置
REPORT_CONFIG = {
    "daily_time": "17:00",  # 每日17:00推送
    "format": "feishu_card"   # 飞书卡片格式
}