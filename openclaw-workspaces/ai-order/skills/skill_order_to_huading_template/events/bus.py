"""
events/bus.py — shim（向后兼容）

实际实现已移至工作区级 events/bus.py。
此文件仅为保持 skill 内部 import 不报错。
"""
import os
import importlib.util

# 工作区根目录 = skill 的祖父目录的祖父目录
_ws = os.environ.get(
    "AI_ORDER_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
_bus_path = os.path.join(_ws, "events", "bus.py")

# 直接用 importlib 加载工作区 events/bus.py，避免 sys.path 顺序导致的循环引用
_spec = importlib.util.spec_from_file_location("_workspace_events_bus", _bus_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# 导出所有内容
EventBus = _mod.EventBus
