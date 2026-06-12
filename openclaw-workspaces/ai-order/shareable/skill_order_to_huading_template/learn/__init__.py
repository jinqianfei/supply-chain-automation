"""
learn/ — 自适应学习系统 Phase 1（Feedback Collector）

- collector.py — 订阅事件总线，写入数据库
- adapter.py   — 事件 payload → DB record 转换
- schema.sql   — 建表 SQL（已执行）
"""
from .collector import FeedbackCollector, init_feedback_collector, get_feedback_collector

__all__ = ["FeedbackCollector", "init_feedback_collector", "get_feedback_collector"]
