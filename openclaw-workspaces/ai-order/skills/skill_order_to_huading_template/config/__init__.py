"""
config package — 统一加载 yaml 配置
"""
import os
from functools import lru_cache

import yaml

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=None)
def _load_yaml(name: str) -> dict:
    """加载 config/ 下的 yaml 文件（带缓存）"""
    path = os.path.join(_CONFIG_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def get_template_defaults() -> dict:
    """华鼎模板默认配置（defaults 字典）"""
    data = _load_yaml("template_defaults.yaml")
    return data.get("huading_template", {}).get("defaults", {})


def get_huading_fields() -> list:
    """华鼎模板 31 字段顺序（v5.11.2 统一来源，消除双重定义）"""
    data = _load_yaml("template_defaults.yaml")
    return list(data.get("huading_template", {}).get("fields", []))


def get_default_values() -> dict:
    """华鼎模板字段默认值（与 get_template_defaults 同源）"""
    return get_template_defaults()


def get_db_config() -> dict:
    """数据库配置（已迁移到环境变量优先，yaml 兜底）"""
    return _load_yaml("db_config.yaml").get("database", {})


def get_llm_providers() -> dict:
    """LLM provider 配置"""
    return _load_yaml("llm.yaml")
