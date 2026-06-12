"""
skill_ops_monitor - 运营监控平台主入口
"""

from .config import DB_CONFIG, AGENT_REGISTRY

__version__ = "1.0.0"
__all__ = ["DB_CONFIG", "AGENT_REGISTRY"]


def execute(task="collect", agent_id=None, **kwargs):
    """
    运营监控入口
    
    Args:
        task: collect（采集）/ report（报表）/ alert（告警）
        agent_id: 指定 agent（默认全部）
        **kwargs: 额外参数
    
    Returns:
        dict: 执行结果
    """
    if task == "collect":
        from .tools.session_collector import collect_agent_sessions
        return collect_agent_sessions(agent_id=agent_id or "ai-order")
    
    elif task == "report":
        from .tools.report_generator import generate_daily_report
        return generate_daily_report(agent_id=agent_id)
    
    elif task == "alert":
        from .tools.alert_detector import check_all_agents
        return check_all_agents(agent_id=agent_id)
    
    else:
        return {"success": False, "message": f"Unknown task: {task}"}