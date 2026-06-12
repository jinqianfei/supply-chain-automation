#!/usr/bin/env python3
"""
startup_check.py — 记忆系统启动检查（2 项）

检查项：
1. memory_fresh  — MEMORY.md 距今 < 7 天
2. no_pending    — PENDING.md 无 🔴 紧急项超 24h

触发：每次 session 启动时（也支持手动跑）
   python3 memory_system/scripts/startup_check.py           # 检查 + 报告
   python3 memory_system/scripts/startup_check.py --strict  # 任何失败 → SystemExit
   python3 memory_system/scripts/startup_check.py --json    # JSON 输出

退出码：
   0 = 全部通过
   1 = 有警告（不阻断）
   2 = 有失败（--strict 模式下 SystemExit）
"""
import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path


def _detect_workspace() -> Path:
    """自动检测工作区根目录（无硬编码路径）"""
    env_ws = os.environ.get("AI_ORDER_WORKSPACE")
    if env_ws and os.path.isdir(env_ws):
        return Path(env_ws)
    script_dir = Path(__file__).resolve().parent
    for parent in script_dir.parents:
        if (parent / "skills" / "skill_order_to_huading_template").is_dir() and (parent / ".env").exists():
            return parent
    for parent in script_dir.parents:
        if (parent / "skills").is_dir():
            return parent
    return Path.cwd()


WORKSPACE = _detect_workspace()
MEMORY_MD = WORKSPACE / "MEMORY.md"
PENDING_MD = WORKSPACE / "memory" / "projects" / "ai-order" / "problems" / "PENDING.md"

STRICT = "--strict" in sys.argv
JSON_OUT = "--json" in sys.argv


def _ok(name, msg, detail=""):
    return {"name": name, "level": "ok", "msg": msg, "detail": detail}


def _warn(name, msg, detail=""):
    return {"name": name, "level": "warn", "msg": msg, "detail": detail}


def _fail(name, msg, detail=""):
    return {"name": name, "level": "fail", "msg": msg, "detail": detail}


def check_memory_fresh() -> dict:
    """检查: MEMORY.md 距今 < 7 天"""
    if not MEMORY_MD.exists():
        return _fail("memory_fresh", "MEMORY.md 不存在")
    try:
        mtime = datetime.fromtimestamp(MEMORY_MD.stat().st_mtime)
        age = datetime.now() - mtime
        days = age.days
        if days < 1:
            return _ok("memory_fresh", f"刚刚更新（{int(age.total_seconds() / 3600)}h）")
        elif days < 3:
            return _ok("memory_fresh", f"近 {days} 天内更新")
        elif days < 7:
            return _warn("memory_fresh", f"{days} 天未更新 MEMORY.md")
        else:
            return _fail("memory_fresh", f"{days} 天未更新（> 7 天）")
    except Exception as e:
        return _warn("memory_fresh", f"读取失败: {e}")


def check_no_pending() -> dict:
    """检查: PENDING.md 无 🔴 紧急项超 24h"""
    if not PENDING_MD.exists():
        return _warn("no_pending", "PENDING.md 不存在（首次运行正常）")
    try:
        text = PENDING_MD.read_text(encoding="utf-8")
        # 只检查表格行中包含 🔴 状态的项目（忽略标题里的 🔴）
        red_items = re.findall(r"^\|\s*P-\d+\s*\|.*🔴.*$", text, re.MULTILINE)
        if not red_items:
            return _ok("no_pending", "无紧急项")
        return _warn("no_pending", f"发现 {len(red_items)} 个紧急项", "; ".join(red_items[:3]))
    except Exception as e:
        return _warn("no_pending", f"读取失败: {e}")


def main() -> int:
    checks = [
        check_memory_fresh(),
        check_no_pending(),
    ]

    by_level = {"ok": 0, "warn": 0, "fail": 0}
    for c in checks:
        by_level[c["level"]] += 1

    if JSON_OUT:
        print(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "summary": by_level,
            "checks": checks,
        }, ensure_ascii=False, indent=2))
        return 2 if by_level["fail"] > 0 else (1 if by_level["warn"] > 0 else 0)

    print("═══════════════════════════════════════════════════════")
    print("  记忆系统 — 启动 2 项自检")
    print(f"  执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═══════════════════════════════════════════════════════")
    print()
    for c in checks:
        icon = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[c["level"]]
        print(f"  {icon} [{c['level'].upper():4s}] {c['name']}: {c['msg']}")
        if c.get("detail") and c["level"] != "ok":
            detail = c["detail"].splitlines()[0][:80]
            print(f"           └─ {detail}")
    print()
    print(f"  📊 汇总: {by_level['ok']} ✅ / {by_level['warn']} ⚠️ / {by_level['fail']} ❌")
    print()

    if by_level["fail"] > 0:
        print("  🚫 有失败项", "(strict 模式: 阻断)" if STRICT else "(非 strict 模式: 警告)", flush=True)
        return 2 if STRICT else 1
    if by_level["warn"] > 0:
        print("  ⚠️  有警告项（不阻断）", flush=True)
        return 1
    print("  🎉 全部 2 项通过", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
