"""
events/bus.py — 极简进程内事件总线

设计原则（方案 B 事件驱动）：
- 单例（进程内唯一）
- 同步调用（顺序执行，不并发）
- 容错（handler 异常不阻断主流程）
- 无外部依赖（纯标准库）
- 无状态（只路由，不存储数据）

Skill 在 4 个「需要用户确认」的节点 emit 事件，FeedbackCollector 订阅后写入数据库。
"""
from typing import Callable, Dict, List, Any


class EventBus:
    """
    进程内事件总线。

    用法：
        # 订阅
        EventBus.on("store_confirmed", my_handler)

        # 发出
        EventBus.emit("store_confirmed", {"store_name": "...", ...})
    """
    _handlers: Dict[str, List[Callable]] = {}

    @classmethod
    def on(cls, event: str, handler: Callable[[Dict], None]) -> None:
        """订阅事件。同一事件可订阅多个 handler。"""
        if event not in cls._handlers:
            cls._handlers[event] = []
        if handler not in cls._handlers[event]:
            cls._handlers[event].append(handler)

    @classmethod
    def off(cls, event: str, handler: Callable[[Dict], None]) -> None:
        """取消订阅。"""
        if event in cls._handlers:
            cls._handlers[event] = [h for h in cls._handlers[event] if h != handler]

    @classmethod
    def emit(cls, event: str, data: Dict[str, Any]) -> None:
        """发出事件，同步调用所有 handler，任一 handler 异常不影响其他。"""
        for handler in cls._handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                # 容错：handler 报错只打印日志，不阻断 Skill 主流程
                print(f"[EventBus] handler error in '{event}': {e}", flush=True)

    @classmethod
    def clear(cls) -> None:
        """清除所有订阅（主要用于测试）。"""
        cls._handlers.clear()

    @classmethod
    def subscribers(cls, event: str) -> List[Callable]:
        """返回某事件的所有订阅 handler（主要用于测试/调试）。"""
        return list(cls._handlers.get(event, []))
