"""
数据库连接管理模块
"""
import os
from typing import Optional
import psycopg2
import yaml


def get_connection(db_config: Optional[dict] = None):
    """
    获取数据库连接
    
    Args:
        db_config: 数据库连接配置字典，可选
                   如果为None，从config/db_config.yaml读取
                   如果都不存在，从环境变量读取
    """
    config = db_config or _load_db_config()
    
    conn = psycopg2.connect(
        host=config.get("host", "localhost"),
        port=config.get("port", 5432),
        database=config.get("database", "neo"),
        user=config.get("user", os.getenv("DB_USER", "your_username")),
        password=config.get("password", "")
    )
    return conn


def _load_db_config() -> dict:
    """从配置文件或环境变量加载数据库配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config", "db_config.yaml"
    )
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            return data.get("database", {})
    
    # 兜底：硬编码默认值
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": 5432,
        "database": "neo",
        "user": "your_username",
        "password": ""
    }
