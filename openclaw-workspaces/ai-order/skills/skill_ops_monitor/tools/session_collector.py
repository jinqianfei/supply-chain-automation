"""
session_collector - 会话采集工具
从 OpenClaw sessions_list / sessions_history 采集数据
"""

import re
import json
from datetime import datetime, timedelta

from ..config import DB_CONFIG

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def get_db_connection():
    """获取数据库连接"""
    if psycopg2 is None:
        raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
    return psycopg2.connect(**DB_CONFIG)


def collect_agent_sessions(agent_id="ai-order", active_minutes=60):
    """
    采集指定 agent 的活跃 session
    
    Args:
        agent_id: Agent ID（默认 ai-order）
        active_minutes: 最近 N 分钟有活动的 session
    
    Returns:
        dict: 采集结果
    """
    # 使用 sessions_list 获取活跃 sessions
    from openclaw_core.sessions import sessions_list
    
    sessions = sessions_list(
        agentId=agent_id,
        activeMinutes=active_minutes,
        includeLastMessage=True
    )
    
    collected = []
    for session in sessions:
        session_key = session.get("sessionKey") or session.get("key")
        if not session_key:
            continue
        
        # 拉取完整链路
        from openclaw_core.sessions import sessions_history
        
        history = sessions_history(
            sessionKey=session_key,
            includeTools=True
        )
        
        # 解析链路
        traces = parse_session_traces(history, agent_id, session_key)
        collected.append({
            "session_id": session_key,
            "traces": traces,
            "message_count": len(history.get("messages", []))
        })
    
    return {
        "success": True,
        "agent_id": agent_id,
        "session_count": len(collected),
        "data": collected
    }


def parse_session_traces(history, agent_id, session_id):
    """
    解析 session history，提取思维链、工具链、用户交互
    
    Args:
        history: sessions_history 返回的原始数据
        agent_id: Agent ID
        session_id: Session ID
    
    Returns:
        list: 解析后的 traces
    """
    traces = []
    messages = history.get("messages", [])
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "assistant":
            # 解析思维链（reasoning）
            reasoning_blocks = extract_reasoning(content)
            for block in reasoning_blocks:
                traces.append({
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "step_type": "reasoning",
                    "content": block,
                    "created_at": msg.get("created_at")
                })
            
            # 解析工具调用
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                traces.append({
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "step_type": "tool_call",
                    "tool_name": tc.get("name", ""),
                    "tool_args": tc.get("arguments"),
                    "created_at": msg.get("created_at")
                })
        
        elif role == "user":
            # 解析用户交互
            action = detect_user_action(content)
            if action:
                traces.append({
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "step_type": "user_action",
                    "content": content,
                    "action": action,
                    "created_at": msg.get("created_at")
                })
    
    return traces


def extract_reasoning(content):
    """
    从 assistant 消息中提取思维链
    匹配 **思考** 或 **思** 开头的段落
    """
    # 匹配 **思考**...** 或 **思**...** 格式
    pattern = r'\*\*(?:思|思考)[^*]*(?:\*\*(.*?)\*\*|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    results = []
    for m in matches:
        text = m.strip()
        if text:
            results.append(text[:1000])  # 截断到 1000 字符
    
    # 如果没找到，尝试简单匹配
    if not results:
        lines = content.split('\n')
        for line in lines:
            if '思' in line and ('**' in line or '推理' in line or '判断' in line):
                results.append(line.strip()[:500])
    
    return results


def detect_user_action(content):
    """
    检测用户动作类型
    
    Returns:
        str: action type 或 None
    """
    content_lower = content.lower()
    
    if 'confirm' in content_lower or '确认' in content:
        return 'confirm'
    elif 'reject' in content_lower or '拒绝' in content:
        return 'reject'
    elif 'modify' in content_lower or '修改' in content or '改' in content:
        return 'modify'
    elif 'yes' in content_lower or '对' in content or '正确' in content:
        return 'accept'
    elif 'no' in content_lower or '错' in content:
        return 'reject'
    
    return None


def save_traces_to_db(traces, conn=None):
    """
    将 traces 保存到数据库
    
    Args:
        traces: parse_session_traces 返回的数据
        conn: 数据库连接（可选）
    """
    if not traces:
        return
    
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    
    try:
        cursor = conn.cursor()
        
        for trace in traces:
            cursor.execute("""
                INSERT INTO session_traces 
                (agent_id, session_id, step_type, content, tool_name, tool_args, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                trace.get("agent_id"),
                trace.get("session_id"),
                trace.get("step_type"),
                trace.get("content"),
                trace.get("tool_name"),
                json.dumps(trace.get("tool_args")) if trace.get("tool_args") else None,
                trace.get("created_at") or datetime.now()
            ))
        
        conn.commit()
        cursor.close()
    
    finally:
        if should_close:
            conn.close()


if __name__ == "__main__":
    # 测试采集
    result = collect_agent_sessions("ai-order", active_minutes=60)
    print(f"采集完成: {result['session_count']} 个 session")
    for session in result.get("data", []):
        print(f"  Session {session['session_id']}: {len(session['traces'])} 条 traces")