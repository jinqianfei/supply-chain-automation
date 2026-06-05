"""
规则引擎 - 加载规则、校正字段、校验数据
"""
import os
import yaml
from typing import Optional, Dict, Any, List


def load_rules(customer: str = "default") -> dict:
    """加载指定客户的字段映射规则"""
    rules_dir = os.path.join(
        os.path.dirname(__file__), "rules"
    )
    
    # 尝试加载客户规则
    paths_to_try = [
        os.path.join(rules_dir, f"{customer}.yaml"),
        os.path.join(rules_dir, f"{customer}.yml"),
    ]
    
    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return yaml.safe_load(f)
    
    # 如果客户规则不存在，尝试根据客户名称智能匹配
    if os.path.exists(rules_dir):
        for fname in os.listdir(rules_dir):
            if fname.endswith((".yaml", ".yml")) and fname not in ("default.yaml", "default.yml"):
                with open(os.path.join(rules_dir, fname), "r") as f:
                    rule = yaml.safe_load(f)
                    rule_name = rule.get("customer_name", "")
                    if rule_name and rule_name in customer:
                        return rule
    
    # 兜底加载默认规则
    default_path = os.path.join(rules_dir, "default.yaml")
    if os.path.exists(default_path):
        with open(default_path, "r") as f:
            return yaml.safe_load(f)
    
    return {"field_aliases": {}, "validation": {"required": ["store_name", "product_name", "quantity"]}, "correction": {}}


def list_available_rules() -> List[dict]:
    """列出所有可用的规则配置"""
    rules_dir = os.path.join(os.path.dirname(__file__), "rules")
    if not os.path.exists(rules_dir):
        return []
    
    rules = []
    for fname in sorted(os.listdir(rules_dir)):
        if fname.endswith((".yaml", ".yml")) and not fname.startswith("_"):
            with open(os.path.join(rules_dir, fname), "r") as f:
                rule = yaml.safe_load(f)
                rules.append({
                    "filename": fname,
                    "customer_name": rule.get("customer_name", fname.replace(".yaml", "")),
                    "description": rule.get("description", ""),
                    "field_count": len(rule.get("field_aliases", {})),
                })
    return rules
