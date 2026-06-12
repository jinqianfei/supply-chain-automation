"""
learn/adapter.py — shim（向后兼容）
实际实现已移至 learning/adapter.py
"""
import sys, os
_ws = os.environ.get("AI_ORDER_WORKSPACE",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _ws not in sys.path:
    sys.path.insert(0, _ws)
from learning.adapter import *  # noqa
