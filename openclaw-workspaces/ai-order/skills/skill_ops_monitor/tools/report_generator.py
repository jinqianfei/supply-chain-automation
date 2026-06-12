"""
report_generator - 报表生成
生成日报、周报、异常报告
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

from ..config import DB_CONFIG, AGENT_REGISTRY
from .metrics_calculator import get_daily_summary, get_weekly_summary
from .alert_detector import get_unresolved_alerts


def get_db_connection():
    """获取数据库连接"""
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed")
    return psycopg2.connect(**DB_CONFIG)


def generate_daily_report(agent_id: Optional[str] = None, date: Optional[str] = None) -> Dict:
    """
    生成日报
    
    Args:
        agent_id: 指定 agent（默认全部）
        date: 日期（默认今天）
    
    Returns:
        dict: 报表结果
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # 获取需要汇报的 agents
    agents = []
    if agent_id:
        agents = [(agent_id, AGENT_REGISTRY.get(agent_id, {}).get("agent_name", agent_id))]
    else:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT agent_id, agent_name 
                FROM monitored_agents 
                WHERE is_active = TRUE
            """)
            rows = cursor.fetchall()
            cursor.close()
            agents = [(r["agent_id"], r["agent_name"]) for r in rows]
        finally:
            conn.close()
    
    # 生成每个 agent 的详情
    agent_details = []
    for aid, aname in agents:
        metrics = get_daily_summary(aid, date)
        alerts = get_unresolved_alerts(aid)
        feedback = get_feedback_summary(aid, date)
        tool_usage = get_tool_usage_summary(aid, date)
        
        detail = {
            "agent_id": aid,
            "agent_name": aname,
            "skill_version": AGENT_REGISTRY.get(aid, {}).get("skill_version", "unknown"),
            "metrics": metrics,
            "alerts": alerts,
            "feedback": feedback,
            "tool_usage": tool_usage
        }
        agent_details.append(detail)
    
    # 构建日报内容
    report = {
        "date": date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agent_count": len(agents),
        "agents": agent_details,
        "summary": build_summary_text(agent_details)
    }
    
    return report


def get_feedback_summary(agent_id: str, date: str) -> Dict:
    """
    获取用户反馈汇总
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT feedback_type, COUNT(*) as count
            FROM user_feedback
            WHERE agent_id = %s AND DATE(created_at) = %s
            GROUP BY feedback_type
        """, (agent_id, date))
        
        rows = cursor.fetchall()
        cursor.close()
        
        total = sum(r["count"] for r in rows)
        return {
            "total": total,
            "by_type": {r["feedback_type"]: r["count"] for r in rows}
        }
    
    finally:
        conn.close()


def get_tool_usage_summary(agent_id: str, date: str) -> List[Dict]:
    """
    获取工具使用统计
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT tool_name, COUNT(*) as call_count
            FROM session_traces
            WHERE agent_id = %s AND DATE(created_at) = %s AND step_type = 'tool_call'
            GROUP BY tool_name
            ORDER BY call_count DESC
            LIMIT 10
        """, (agent_id, date))
        
        rows = cursor.fetchall()
        cursor.close()
        
        return [dict(r) for r in rows]
    
    finally:
        conn.close()


def build_summary_text(agent_details: List[Dict]) -> str:
    """
    构建简明摘要文本（用于飞书消息）
    """
    lines = []
    
    for agent in agent_details:
        lines.append(f"🤖 **{agent['agent_name']}**（{agent['skill_version']}）")
        lines.append("")
        
        m = agent["metrics"]
        lines.append(f"📈 今日概览")
        lines.append(f"├── 新增订单：{m['total_orders']} 单")
        lines.append(f"├── 成功处理：{m['success_count']} 单（{m['success_rate']}%）")
        lines.append(f"├── 失败处理：{m['failed_count']} 单")
        lines.append(f"├── 用户拒绝：{m['rejected_count']} 单")
        lines.append(f"└── 平均处理时长：{m['avg_processing_time_ms']/1000:.0f}s")
        lines.append("")
        
        lines.append(f"📦 门店 & SKU 统计")
        lines.append(f"├── SKU 总匹配率：{m['avg_match_rate']}%")
        lines.append(f"└── 未匹配SKU：{m['total_unmatched']} 个")
        lines.append("")
        
        # 告警
        alerts = agent.get("alerts", [])
        if alerts:
            lines.append(f"⚠️ 异常告警（{len(alerts)} 条）")
            for a in alerts[:3]:
                severity_icon = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(a["severity"], "⚪")
                lines.append(f"├── {severity_icon} {a['message']}")
        else:
            lines.append("✅ 无异常告警")
        lines.append("")
        
        # 工具使用
        tool_usage = agent.get("tool_usage", [])
        if tool_usage:
            lines.append(f"🛠️ 工具使用 Top5")
            for t in tool_usage[:5]:
                lines.append(f"├── {t['tool_name']}：{t['call_count']}次")
            lines.append("")
        
        lines.append("─" * 30)
        lines.append("")
    
    return "\n".join(lines)


def format_feishu_card(report: Dict) -> Dict:
    """
    格式化为飞书卡片消息
    
    Args:
        report: generate_daily_report 返回的数据
    
    Returns:
        dict: 飞书卡片元素
    """
    elements = []
    
    # 标题
    elements.append({
        "tag": "markdown",
        "content": f"📊 **OpenClaw 运营日报** | {report['date']}"
    })
    
    elements.append({"tag": "hr"})
    
    for agent in report["agents"]:
        m = agent["metrics"]
        skill_ver = agent["skill_version"]
        
        # Agent 区块标题
        elements.append({
            "tag": "markdown",
            "content": f"🤖 **{agent['agent_name']}**（skill {skill_ver}）"
        })
        
        # 指标卡片
        elements.append({
            "tag": "column_set",
            "flex_mode": "split_title",
            "columns": [
                {
                    "tag": "column",
                    "width": "stretched",
                    "vertical_align": "top",
                    "elements": [
                        {"tag": "markdown", "content": "**📈 今日概览**"},
                        {"tag": "markdown", "content": f"订单数：{m['total_orders']}"},
                        {"tag": "markdown", "content": f"成功率：{m['success_rate']}%"},
                        {"tag": "markdown", "content": f"平均时长：{m['avg_processing_time_ms']/1000:.0f}s"},
                    ]
                },
                {
                    "tag": "column",
                    "width": "stretched",
                    "vertical_align": "top",
                    "elements": [
                        {"tag": "markdown", "content": "**📦 SKU 统计**"},
                        {"tag": "markdown", "content": f"匹配率：{m['avg_match_rate']}%"},
                        {"tag": "markdown", "content": f"已匹配：{m['total_matched']} 个"},
                        {"tag": "markdown", "content": f"未匹配：{m['total_unmatched']} 个"},
                    ]
                }
            ]
        })
        
        # 告警
        alerts = agent.get("alerts", [])
        if alerts:
            alert_content = "⚠️ **异常告警**\n"
            for a in alerts[:3]:
                icon = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(a["severity"], "⚪")
                alert_content += f"{icon} {a['message']}\n"
            
            elements.append({
                "tag": "markdown",
                "content": alert_content
            })
        
        elements.append({"tag": "hr"})
    
    # 页脚
    elements.append({
        "tag": "markdown",
        "content": f"_由 Ops Monitor 生成 | {report['generated_at']}_"
    })
    
    return {
        "msg_type": "interactive",
        "card": {
            "elements": elements
        }
    }


def generate_weekly_report(agent_id: Optional[str] = None) -> Dict:
    """
    生成周报
    
    Args:
        agent_id: 指定 agent（默认全部）
    
    Returns:
        dict: 周报数据
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    agents = []
    if agent_id:
        agents = [(agent_id, AGENT_REGISTRY.get(agent_id, {}).get("agent_name", agent_id))]
    else:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT agent_id, agent_name 
                FROM monitored_agents 
                WHERE is_active = TRUE
            """)
            rows = cursor.fetchall()
            cursor.close()
            agents = [(r["agent_id"], r["agent_name"]) for r in rows]
        finally:
            conn.close()
    
    agent_details = []
    for aid, aname in agents:
        weekly = get_weekly_summary(aid, end_date)
        alerts = get_unresolved_alerts(aid)
        
        detail = {
            "agent_id": aid,
            "agent_name": aname,
            "weekly": weekly,
            "alerts": alerts
        }
        agent_details.append(detail)
    
    return {
        "start_date": agent_details[0]["weekly"].get("start_date") if agent_details else "",
        "end_date": end_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agents": agent_details
    }