"""
数据库连接管理模块
"""
import os
from typing import Optional
import psycopg2
import yaml


def _find_dotenv_path() -> Optional[str]:
    """
    查找 .env 文件路径

    优先级：
    1. 环境变量 DOTENV_PATH（强制指定）
    2. skill 父目录的 .env（兼容金姐当前结构：ai-order/.env）
    3. skill 父目录的父目录的 .env（兼容 monorepo 结构）
    4. 当前工作目录的 .env
    """
    explicit = os.getenv("DOTENV_PATH")
    if explicit and os.path.exists(explicit):
        return explicit

    # skill 根目录 = db/connection.py 的祖父目录
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(skill_root, "..", ".env"),                # 父目录
        os.path.join(skill_root, "..", "..", ".env"),           # 祖父目录
        os.path.join(os.getcwd(), ".env"),                      # CWD
    ]
    for c in candidates:
        c = os.path.abspath(c)
        if os.path.exists(c):
            return c
    return None


def _load_dotenv_to_environ() -> dict:
    """
    从 .env 文件加载 KEY=VALUE 到 os.environ（不覆盖已存在的 env）

    Returns:
        加载的 key->value 字典（调试用）
    """
    env_path = _find_dotenv_path()
    loaded = {}
    if not env_path:
        return loaded
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v
                    loaded[k] = v
    except Exception:
        pass
    return loaded


def get_default_db_config() -> dict:
    """
    获取默认数据库配置（从环境变量或 yaml 配置文件读取）
    
    优先级：
    1. 环境变量 DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
    2. config/db_config.yaml 文件
    3. 中性 fallback（localhost / your_username / neo）
    
    注意：fallback 必须是中性值，严防具体的主机名/用户名
    """
    # 先加载 .env，确保环境变量有值（但不要覆盖已有的 env）
    _load_dotenv_to_environ()
    
    yaml_config = _load_db_config()
    return {
        "host": os.getenv("DB_HOST") or yaml_config.get("host") or "localhost",
        "port": int(os.getenv("DB_PORT") or yaml_config.get("port") or 5432),
        "database": os.getenv("DB_NAME") or yaml_config.get("database") or "neo",
        "user": os.getenv("DB_USER") or yaml_config.get("user") or "your_username",
        "password": os.getenv("DB_PASSWORD") or yaml_config.get("password") or "",
    }


def get_connection(db_config: Optional[dict] = None):
    """
    获取数据库连接
    
    Args:
        db_config: 数据库连接配置字典，可选
                   如果为None，从config/db_config.yaml读取
                   如果都不存在，从环境变量读取
    """
    config = db_config or get_default_db_config()
    
    conn = psycopg2.connect(
        host=config.get("host", "localhost"),
        port=config.get("port", 5432),
        database=config.get("database", "neo"),
        user=config.get("user", "your_username"),
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
