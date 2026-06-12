"""
metrics_calculator - 指标计算
计算订单匹配率、处理时长、成功率等
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

from ..config import DB_CONFIG


def get_db_connection():
    """获取数据库连接"""
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed")
    return psycopg2.connect(**DB_CONFIG)


def calculate_session_metrics(session_traces: List[Dict]) -> Dict:
    """
    计算单个 session 的指标
    
    Args:
        session_traces: 该 session 的所有 traces
    
    Returns:
        dict: 指标数据
    """
    tool_calls = [t for t in session_traces if t.get("step_type") == "tool_call"]
    reasoning_steps = [t for t in session_traces if t.get("step_type") == "reasoning"]
    user_actions = [t for t in session_traces if t.get("step_type") == "user_action"]
    
    return {
        "tool_call_count": len(tool_calls),
        "reasoning_count": len(reasoning_steps),
        "user_action_count": len(user_actions),
        "tool_names": list(set(t.get("tool_name", "") for t in tool_calls)),
        "actions": [t.get("action") for t in user_actions if t.get("action")]
    }


def calculate_order_metrics(order_data: Dict) -> Dict:
    """
    计算订单指标
    
    Args:
        order_data: 订单数据
    
    Returns:
        dict: 订单指标
    """
    sku_count = order_data.get("sku_count", 0)
    matched_count = order_data.get("matched_sku_count", 0)
    unmatched_count = order_data.get("unmatched_sku_count", 0)
    
    match_rate = (matched_count / sku_count * 100) if sku_count > 0 else 0
    
    return {
        "sku_count": sku_count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "match_rate": round(match_rate, 1),
        "match_status": "success" if match_rate >= 80 else "warning" if match_rate >= 70 else "critical"
    }


def get_daily_summary(agent_id: str, date: Optional[str] = None) -> Dict:
    """
    获取指定 agent 指定日期的汇总指标
    
    Args:
        agent_id: Agent ID
        date: 日期（YYYY-MM-DD），默认今天
    
    Returns:
        dict: 汇总指标
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 查询当日订单统计
        cursor.execute("""
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                SUM(CASE WHEN status = 'user_rejected' THEN 1 ELSE 0 END) as rejected_count,
                AVG(processing_time_ms) as avg_processing_time,
                AVG(match_rate) as avg_match_rate,
                SUM(matched_sku_count) as total_matched,
                SUM(unmatched_sku_count) as total_unmatched
            FROM order_metrics
            WHERE agent_id = %s AND order_date = %s
        """, (agent_id, date))
        
        row = cursor.fetchone()
        
        # 查询当日告警
        cursor.execute("""
            SELECT COUNT(*) as alert_count
            FROM alert_events
            WHERE agent_id = %s AND DATE(created_at) = %s AND is_resolved = FALSE
        """, (agent_id, date))
        
        alert_row = cursor.fetchone()
        
        # 查询工具使用统计
        cursor.execute("""
            SELECT tool_name, COUNT(*) as call_count
            FROM session_traces
            WHERE agent_id = %s AND DATE(created_at) = %s AND step_type = 'tool_call'
            GROUP BY tool_name
            ORDER BY call_count DESC
        """, (agent_id, date))
        
        tool_rows = cursor.fetchall()
        
        cursor.close()
        
        total = row['total_orders'] or 0
        success = row['success_count'] or 0
        
        return {
            "date": date,
            "agent_id": agent_id,
            "total_orders": total,
            "success_count": success,
            "failed_count": row['failed_count'] or 0,
            "rejected_count": row['rejected_count'] or 0,
            "success_rate": round(success / total * 100, 1) if total > 0 else 0,
            "avg_processing_time_ms": round(row['avg_processing_time'] or 0),
            "avg_match_rate": round(row['avg_match_rate'] or 0, 1),
            "total_matched": row['total_matched'] or 0,
            "total_unmatched": row['total_unmatched'] or 0,
            "alert_count": alert_row['alert_count'] or 0,
            "tool_usage": [dict(r) for r in tool_rows]
        }
    
    finally:
        conn.close()


def get_weekly_summary(agent_id: str, end_date: Optional[str] = None) -> Dict:
    """
    获取指定 agent 最近 7 天汇总
    
    Args:
        agent_id: Agent ID
        end_date: 结束日期，默认今天
    
    Returns:
        dict: 周汇总
    """
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    start_dt = end_dt - timedelta(days=6)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 按天统计
        cursor.execute("""
            SELECT 
                order_date,
                COUNT(*) as daily_orders,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as daily_success
            FROM order_metrics
            WHERE agent_id = %s AND order_date BETWEEN %s AND %s
            GROUP BY order_date
            ORDER BY order_date
        """, (agent_id, start_date, end_str))
        
        daily_rows = cursor.fetchall()
        
        # 汇总
        cursor.execute("""
            SELECT 
                COUNT(*) as total_orders,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                AVG(processing_time_ms) as avg_processing_time,
                AVG(match_rate) as avg_match_rate
            FROM order_metrics
            WHERE agent_id = %s AND order_date BETWEEN %s AND %s
        """, (agent_id, start_date, end_str))
        
        summary = cursor.fetchone()
        
        cursor.close()
        
        return {
            "start_date": start_date,
            "end_date": end_str,
            "daily_trend": [dict(r) for r in daily_rows],
            "total_orders": summary['total_orders'] or 0,
            "success_count": summary['success_count'] or 0,
            "success_rate": round(summary['success_count'] / summary['total_orders'] * 100, 1) if summary['total_orders'] > 0 else 0,
            "avg_processing_time_ms": round(summary['avg_processing_time'] or 0),
            "avg_match_rate": round(summary['avg_match_rate'] or 0, 1)
        }
    
    finally:
        conn.close()