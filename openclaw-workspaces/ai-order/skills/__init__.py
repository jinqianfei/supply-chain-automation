"""
skills/ — Skill 包初始化

确保从工作区根目录 import 时，skill 内部模块的相对路径可用。
"""
import sys
import os

# 将每个 skill 子目录加入 sys.path，使其内部 `from db.xxx` 等可用
_skills_dir = os.path.dirname(os.path.abspath(__file__))
for _name in os.listdir(_skills_dir):
    _full = os.path.join(_skills_dir, _name)
    if os.path.isdir(_full) and os.path.exists(os.path.join(_full, "__init__.py")):
        if _full not in sys.path:
            sys.path.insert(0, _full)
