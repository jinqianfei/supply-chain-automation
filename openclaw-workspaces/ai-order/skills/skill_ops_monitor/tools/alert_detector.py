"""
alert_detector - 异常检测
基于阈值规则检测异常并生成告警
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None

from ..config import DB_CONFIG, ALERT_THRESHOLDS


def get_db_connection():
    """获取数据库连接"""
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed")
    return psycopg2.connect(**DB_CONFIG)


def check_order_alerts(order_data: Dict) -> List[Dict]:
    """
    检测单笔订单的异常
    
    Args:
        order_data: 订单数据
    
    Returns:
        list: 告警列表
    """
    alerts = []
    thresholds = ALERT_THRESHOLDS
    
    # 1. 检查 SKU 匹配率
    match_rate = order_data.get("match_rate", 100)
    if match_rate < thresholds["low_match_rate"]["critical"]:
        alerts.append({
            "alert_type": "low_match_rate",
            "severity": "critical",
            "message": f"SKU匹配率严重过低: {match_rate}%（<{thresholds['low_match_rate']['critical']*100}%）",
            "order_id": order_data.get("id")
        })
    elif match_rate < thresholds["low_match_rate"]["high"]:
        alerts.append({
            "alert_type": "low_match_rate",
            "severity": "high",
            "message": f"SKU匹配率过低: {match_rate}%（<{thresholds['low_match_rate']['high']*100}%）",
            "order_id": order_data.get("id")
        })
    elif match_rate < thresholds["low_match_rate"]["medium"]:
        alerts.append({
            "alert_type": "low_match_rate",
            "severity": "medium",
            "message": f"SKU匹配率偏低: {match_rate}%（<{thresholds['low_match_rate']['medium']*100}%）",
            "order_id": order_data.get("id")
        })
    
    # 2. 检查处理超时
    processing_time_ms = order_data.get("processing_time_ms", 0)
    if processing_time_ms > thresholds["processing_timeout_ms"]["high"]:
        alerts.append({
            "alert_type": "timeout",
            "severity": "high",
            "message": f"处理超时: {processing_time_ms/1000:.0f}秒（>{thresholds['processing_timeout_ms']['high']/1000}秒）",
            "order_id": order_data.get("id")
        })
    elif processing_time_ms > thresholds["processing_timeout_ms"]["medium"]:
        alerts.append({
            "alert_type": "timeout",
            "severity": "medium",
            "message": f"处理时间偏长: {processing_time_ms/1000:.0f}秒（>{thresholds['processing_timeout_ms']['medium']/1000}秒）",
            "order_id": order_data.get("id")
        })
    
    # 3. 检查未匹配 SKU
    unmatched_count = order_data.get("unmatched_sku_count", 0)
    if unmatched_count > 0 and match_rate < 80:
        alerts.append({
            "alert_type": "unmatched_skus",
            "severity": "medium",
            "message": f"存在 {unmatched_count} 个未匹配SKU",
            "order_id": order_data.get("id")
        })
    
    return alerts


def check_user_reject_pattern(session_traces: List[Dict]) -> Optional[Dict]:
    """
    检测用户连续拒绝模式
    
    Args:
        session_traces: session 的 traces
    
    Returns:
        dict: 告警 或 None
    """
    user_actions = [t for t in session_traces if t.get("step_type") == "user_action"]
    reject_count = sum(1 for t in user_actions if t.get("action") == "reject")
    
    if reject_count >= ALERT_THRESHOLDS["max_user_rejects"]:
        return {
            "alert_type": "user_reject",
            "severity": "high",
            "message": f"用户连续拒绝 {reject_count} 次",
            "session_id": session_traces[0].get("session_id") if session_traces else None
        }
    
    return None


def save_alerts_to_db(alerts: List[Dict], conn=None) -> int:
    """
    将告警保存到数据库
    
    Args:
        alerts: 告警列表
        conn: 数据库连接
    
    Returns:
        int: 保存的告警数量
    """
    if not alerts:
        return 0
    
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    
    try:
        cursor = conn.cursor()
        saved = 0
        
        for alert in alerts:
            cursor.execute("""
                INSERT INTO alert_events 
                (agent_id, order_id, alert_type, severity, message, raw_data, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                alert.get("agent_id"),
                alert.get("order_id"),
                alert.get("alert_type"),
                alert.get("severity"),
                alert.get("message"),
                json.dumps(alert.get("raw_data", {})),
                datetime.now()
            ))
            saved += 1
        
        conn.commit()
        cursor.close()
        
        return saved
    
    finally:
        if should_close:
            conn.close()


def get_unresolved_alerts(agent_id: str, severity: Optional[str] = None) -> List[Dict]:
    """
    获取未解决的告警
    
    Args:
        agent_id: Agent ID
        severity: 过滤严重级别（可选）
    
    Returns:
        list: 告警列表
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT ae.*, om.session_id, om.owner_code
            FROM alert_events ae
            LEFT JOIN order_metrics om ON ae.order_id = om.id
            WHERE ae.agent_id = %s AND ae.is_resolved = FALSE
        """
        params = [agent_id]
        
        if severity:
            query += " AND ae.severity = %s"
            params.append(severity)
        
        query += " ORDER BY ae.created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        
        return [dict(r) for r in rows]
    
    finally:
        conn.close()


def resolve_alert(alert_id: int) -> bool:
    """
    标记告警为已解决
    
    Args:
        alert_id: 告警 ID
    
    Returns:
        bool: 是否成功
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE alert_events 
            SET is_resolved = TRUE, resolved_at = %s
            WHERE id = %s
        """, (datetime.now(), alert_id))
        conn.commit()
        cursor.close()
        return True
    
    finally:
        conn.close()


def check_all_agents() -> Dict:
    """
    检查所有活跃 agent 的告警
    
    Returns:
        dict: 汇总结果
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 获取所有活跃 agent
        cursor.execute("""
            SELECT agent_id, agent_name 
            FROM monitored_agents 
            WHERE is_active = TRUE
        """)
        agents = cursor.fetchall()
        
        cursor.close()
        
        all_alerts = []
        for agent in agents:
            alerts = get_unresolved_alerts(agent["agent_id"])
            all_alerts.extend(alerts)
        
        return {
            "success": True,
            "agent_count": len(agents),
            "total_unresolved": len(all_alerts),
            "alerts": all_alerts
        }
    
    finally:
        conn.close()