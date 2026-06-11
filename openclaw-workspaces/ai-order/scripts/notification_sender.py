#!/usr/bin/env python3
"""
自学习模块 — 通知发送脚本

功能：
1. 加载 config/notification_config.yaml
2. 根据 approval_type 找到接收人
3. 根据 channel 调用对应的发送函数（飞书/钉钉）

用法：
    python3 scripts/notification_sender.py <approval_type> <message>

示例：
    python3 scripts/notification_sender.py alias_expansion "别名表改进建议..."
"""
import os
import sys
import yaml
import json
import requests
from typing import List, Dict

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_config() -> Dict:
    """加载通知配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "notification_config.yaml"
    )
    if not os.path.exists(config_path):
        print(f"[ERROR] Config not found: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_recipients(config: Dict, approval_type: str) -> List[Dict]:
    """根据审批类型获取接收人"""
    approver_rules = config.get("approvers", {}).get(approval_type, [])
    recipients = []
    for rule in approver_rules:
        role = rule.get("role")
        for user in config.get("users", []):
            if user.get("role") == role:
                recipients.append(user)
    return recipients


def send_feishu(user_id: str, message: str) -> bool:
    """发送飞书消息（webhook 方式）"""
    webhook = os.getenv("FEISHU_WEBHOOK")
    if not webhook:
        print("[WARN] FEISHU_WEBHOOK not set, skip feishu notification")
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": message}
    }

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[OK] Feishu notification sent to {user_id}")
            return True
        else:
            print(f"[ERROR] Feishu send failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] send_feishu failed: {e}")
        return False


def send_dingtalk(user_id: str, message: str) -> bool:
    """发送钉钉消息（webhook 方式）"""
    webhook = os.getenv("DINGTALK_ROBOT_WEBHOOK")
    if not webhook:
        print("[WARN] DINGTALK_ROBOT_WEBHOOK not set, skip dingtalk notification")
        return False

    payload = {
        "msgtype": "text",
        "text": {"content": message}
    }

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[OK] DingTalk notification sent to {user_id}")
            return True
        else:
            print(f"[ERROR] DingTalk send failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] send_dingtalk failed: {e}")
        return False


def send_notification(approval_type: str, message: str) -> bool:
    """发送通知"""
    config = load_config()
    if not config:
        return False

    recipients = get_recipients(config, approval_type)
    if not recipients:
        print(f"[WARN] No recipients for approval_type: {approval_type}")
        return False

    channels = config.get("channels", {})
    success_count = 0

    for recipient in recipients:
        channel = recipient.get("channel")
        user_id = recipient.get("user_id")

        if channel == "feishu" and channels.get("feishu", {}).get("enabled"):
            if send_feishu(user_id, message):
                success_count += 1
        elif channel == "dingtalk" and channels.get("dingtalk", {}).get("enabled"):
            if send_dingtalk(user_id, message):
                success_count += 1

    return success_count > 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python notification_sender.py <approval_type> <message>")
        print("Example: python notification_sender.py alias_expansion '别名表改进建议...'")
        sys.exit(1)

    approval_type = sys.argv[1]
    message = sys.argv[2]

    success = send_notification(approval_type, message)
    print(f"Notification sent: {success}")
    sys.exit(0 if success else 1)
