"""
learn/ — shim（向后兼容）

实际实现已移至工作区级 learning/。
此文件保持 skill 内部 `from learn.collector import ...` 不报错。
"""
import sys
import os

# 工作区根目录
_ws = os.environ.get(
    "AI_ORDER_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _ws not in sys.path:
    sys.path.insert(0, _ws)

from learning.collector import FeedbackCollector, init_feedback_collector, get_feedback_collector  # noqa

__all__ = ["FeedbackCollector", "init_feedback_collector", "get_feedback_collector"]
