"""
feishu_publisher - 飞书推送
将报表和告警通过飞书机器人发送
"""

import json
from datetime import datetime
from typing import Dict, Optional, List

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from ..config import DB_CONFIG
from .report_generator import generate_daily_report, format_feishu_card


def get_db_connection():
    """获取数据库连接"""
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed")
    return psycopg2.connect(**DB_CONFIG)


def get_agent_channel(agent_id: str) -> Optional[str]:
    """
    获取 agent 的通知渠道（飞书 open_id）
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT owner_channel 
            FROM monitored_agents 
            WHERE agent_id = %s AND is_active = TRUE
        """, (agent_id,))
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None
    finally:
        conn.close()


def send_daily_report(target: Optional[str] = None, agent_id: Optional[str] = None) -> Dict:
    """
    发送日报
    
    Args:
        target: 飞书目标（open_id / chat_id），默认发给自己
        agent_id: 指定 agent（默认全部）
    
    Returns:
        dict: 发送结果
    """
    # 生成报表
    report = generate_daily_report(agent_id=agent_id)
    
    # 格式化为飞书卡片
    card = format_feishu_card(report)
    
    # 通过 OpenClaw message tool 发送
    from openclaw_core.message import send
    from openclaw_core.config import get_channel_config
    
    try:
        result = send(
            channel="feishu",
            target=target,  # None = 发给当前对话
            content=json.dumps(card),
            msg_type="interactive"
        )
        
        return {
            "success": True,
            "report_date": report["date"],
            "agent_count": report["agent_count"],
            "message_id": result.get("message_id")
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def send_alert(alert: Dict, target: Optional[str] = None) -> Dict:
    """
    发送告警通知
    
    Args:
        alert: 告警数据
        target: 飞书目标
    
    Returns:
        dict: 发送结果
    """
    severity = alert.get("severity", "medium")
    severity_icon = {
        "critical": "🔴 严重",
        "high": "🔴 高",
        "medium": "🟡 中",
        "low": "🟢 低"
    }.get(severity, "⚪")
    
    content = f"""
{severity_icon} **异常告警**

**类型**: {alert.get('alert_type')}
**Agent**: {alert.get('agent_id')}
**消息**: {alert.get('message')}

时间: {alert.get('created_at', datetime.now().isoformat())}
"""
    
    from openclaw_core.message import send
    
    try:
        result = send(
            channel="feishu",
            target=target,
            content=content,
            msg_type="text"
        )
        
        return {
            "success": True,
            "message_id": result.get("message_id")
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def send_bulk_alerts(alerts: List[Dict], target: Optional[str] = None) -> Dict:
    """
    批量发送告警（合并为一条消息）
    
    Args:
        alerts: 告警列表
        target: 飞书目标
    
    Returns:
        dict: 发送结果
    """
    if not alerts:
        return {"success": True, "count": 0}
    
    # 按 severity 分组
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for a in alerts:
        sev = a.get("severity", "medium")
        if sev in by_severity:
            by_severity[sev].append(a)
    
    # 构建消息
    lines = ["🔔 **异常告警汇总**\n"]
    
    for sev in ["critical", "high", "medium", "low"]:
        items = by_severity[sev]
        if not items:
            continue
        
        icon = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
        lines.append(f"{icon} **{sev.upper()} 级（{len(items)} 条）**\n")
        
        for a in items:
            lines.append(f"  • {a.get('message', '')}")
        
        lines.append("")
    
    content = "\n".join(lines)
    
    from openclaw_core.message import send
    
    try:
        result = send(
            channel="feishu",
            target=target,
            content=content,
            msg_type="text"
        )
        
        return {
            "success": True,
            "count": len(alerts),
            "message_id": result.get("message_id")
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    # 测试发送
    result = send_daily_report()
    print(f"发送结果: {result}")