"""
events/ — shim（向后兼容）

实际实现已移至工作区级 events/。
"""
from .bus import EventBus

__all__ = ["EventBus"]
