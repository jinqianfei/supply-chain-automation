"""
数据库连接管理模块（v2.0 — 连接复用 + 自动重连）

提供：
- get_default_db_config() — 从环境变量/yaml 获取默认配置
- get_connection() — 获取原始 psycopg2 连接（向后兼容）
- DBConnection — 连接复用 + 自动重连的封装类
"""
import os
import time
from typing import Optional, List, Tuple, Any
import psycopg2
import yaml


# ---------------------------------------------------------------------------
# .env 加载
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 向后兼容的 get_connection()
# ---------------------------------------------------------------------------

def get_connection(db_config: Optional[dict] = None):
    """
    获取数据库连接（向后兼容）

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


# ---------------------------------------------------------------------------
# DBConnection — 连接复用 + 自动重连
# ---------------------------------------------------------------------------

class DBConnection:
    """
    数据库连接管理器

    特性：
    - 连接复用：同一实例共享一个 psycopg2 连接
    - 自动重连：连接断开时自动重试（最多 max_retries 次）
    - 上下文管理器：支持 with 语句自动关闭
    - 便捷方法：execute_query / execute_one / execute_many

    用法：
        db = DBConnection(db_config)
        rows = db.execute_query("SELECT * FROM store_list WHERE store_name LIKE %s", ("%铁牛%",))
        db.close()

        # 或
        with DBConnection(db_config) as db:
            row = db.execute_one("SELECT * FROM customer WHERE customer_id = %s", ("HZ001",))
    """

    def __init__(self, db_config: Optional[dict] = None, max_retries: int = 3, retry_delay: float = 0.5):
        """
        Args:
            db_config: 数据库配置字典（可选，缺省从环境变量读取）
            max_retries: 自动重连最大重试次数
            retry_delay: 重连间隔（秒）
        """
        self._config = db_config or get_default_db_config()
        self._conn: Optional[psycopg2.extensions.connection] = None
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    # --- 连接管理 ---

    def _ensure_connection(self):
        """确保连接可用，断开时自动重连"""
        if self._conn is not None:
            try:
                # 轻量级健康检查
                self._conn.cursor().execute("SELECT 1")
                return
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                # 连接已断开，关闭后重连
                self._close_silent()

        for attempt in range(1, self._max_retries + 1):
            try:
                self._conn = psycopg2.connect(
                    host=self._config.get("host", "localhost"),
                    port=self._config.get("port", 5432),
                    database=self._config.get("database", "neo"),
                    user=self._config.get("user", "your_username"),
                    password=self._config.get("password", "")
                )
                return
            except psycopg2.OperationalError as e:
                if attempt == self._max_retries:
                    raise ConnectionError(
                        f"数据库连接失败（已重试 {self._max_retries} 次）: {e}"
                    ) from e
                time.sleep(self._retry_delay * attempt)

    def _close_silent(self):
        """静默关闭连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def close(self):
        """关闭数据库连接"""
        self._close_silent()

    def __enter__(self):
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # --- 查询方法 ---

    def execute_query(self, sql: str, params: tuple = ()) -> List[Tuple[Any, ...]]:
        """
        执行查询并返回所有行

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            list of tuple（每行一个 tuple）
        """
        self._ensure_connection()
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # 连接问题 → 重连后重试一次
            cur.close()
            self._close_silent()
            self._ensure_connection()
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()

    def execute_one(self, sql: str, params: tuple = ()) -> Optional[Tuple[Any, ...]]:
        """
        执行查询并返回第一行

        Args:
            sql: SQL 查询语句
            params: 查询参数

        Returns:
            tuple 或 None
        """
        self._ensure_connection()
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchone()
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            cur.close()
            self._close_silent()
            self._ensure_connection()
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            cur.close()

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        """
        批量执行（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL 语句
            params_list: 参数列表

        Returns:
            受影响的行数
        """
        self._ensure_connection()
        cur = self._conn.cursor()
        try:
            cur.executemany(sql, params_list)
            self._conn.commit()
            return cur.rowcount
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            cur.close()
            self._close_silent()
            self._ensure_connection()
            cur = self._conn.cursor()
            cur.executemany(sql, params_list)
            self._conn.commit()
            return cur.rowcount
        finally:
            cur.close()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """
        执行单条写操作（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL 语句
            params: 查询参数

        Returns:
            受影响的行数
        """
        self._ensure_connection()
        cur = self._conn.cursor()
        try:
            cur.execute(sql, params)
            self._conn.commit()
            return cur.rowcount
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            cur.close()
            self._close_silent()
            self._ensure_connection()
            cur = self._conn.cursor()
            cur.execute(sql, params)
            self._conn.commit()
            return cur.rowcount
        finally:
            cur.close()

    @property
    def raw_connection(self):
        """获取底层 psycopg2 连接（向后兼容需要 raw connection 的场景）"""
        self._ensure_connection()
        return self._conn
