"""
learning/ — 自学习模块（独立于 Skill）

提供：
- auto_init(db_config) — 由 Skill 软加载调用，初始化 FeedbackCollector
- collector — 事件订阅 + 数据库写入
- adapter — 事件 payload → DB record 转换
- feedback_parser — 解析用户反馈（从 __init__.py 提取）
- modifier — 应用修改到映射结果（从 __init__.py 提取）
"""

__version__ = "1.0.0"


def auto_init(db_config: dict):
    """
    由 Skill 软加载调用。

    初始化 FeedbackCollector，订阅 EventBus 事件。
    如果 events.bus 不可用，静默跳过。

    Args:
        db_config: 数据库连接配置
    """
    try:
        from .collector import init_feedback_collector
        init_feedback_collector(db_config)
    except ImportError as e:
        print(f"[learning] auto_init skipped: {e}", flush=True)
    except Exception as e:
        print(f"[learning] auto_init failed: {e}", flush=True)
