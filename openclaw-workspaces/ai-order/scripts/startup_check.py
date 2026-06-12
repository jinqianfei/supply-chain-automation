#!/usr/bin/env python3
"""
startup_check.py — AI 启动版本/代码检查（2 项）

检查项：
1. version_check — VERSION/SKILL.md/CHANGELOG 三处一致
2. git_clean     — 无未提交的重要文件

记忆相关检查（memory_fresh / no_pending）已移至：
   memory_system/scripts/startup_check.py

触发：每次 session 启动时（也支持手动跑）
   python3 scripts/startup_check.py           # 检查 + 报告
   python3 scripts/startup_check.py --strict  # 任何失败 → SystemExit
   python3 scripts/startup_check.py --json    # JSON 输出

退出码：
   0 = 全部通过
   1 = 有警告（不阻断）
   2 = 有失败（--strict 模式下 SystemExit）
"""
import os
import re
import subprocess
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
SKILL_DIR = WORKSPACE / "skills" / "skill_order_to_huading_template"

STRICT = "--strict" in sys.argv
JSON_OUT = "--json" in sys.argv


def _ok(name, msg, detail=""):
    return {"name": name, "level": "ok", "msg": msg, "detail": detail}


def _warn(name, msg, detail=""):
    return {"name": name, "level": "warn", "msg": msg, "detail": detail}


def _fail(name, msg, detail=""):
    return {"name": name, "level": "fail", "msg": msg, "detail": detail}


def check_version() -> dict:
    """检查1: version_check.sh 三处一致"""
    try:
        result = subprocess.run(
            ["bash", str(SKILL_DIR / "scripts" / "version_check.sh")],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            m = re.search(r"通过：(\d+\.\d+\.\d+)", result.stdout)
            ver = m.group(1) if m else "unknown"
            return _ok("version_check", f"三处一致 {ver}", result.stdout.strip())
        else:
            return _fail("version_check", "三处不一致", result.stdout + result.stderr)
    except Exception as e:
        return _fail("version_check", f"检查脚本失败: {e}")


def check_git_clean() -> dict:
    """检查2: 工作区无未提交修改（仅看 skills/ 和 memory/）"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "skills/", "memory/", "MEMORY.md"],
            capture_output=True, text=True, timeout=10,
            cwd=str(WORKSPACE)
        )
        if result.returncode != 0:
            return _warn("git_clean", f"git status 失败: {result.stderr.strip()}")
        changes = result.stdout.strip()
        if not changes:
            return _ok("git_clean", "无未提交修改")
        return _warn("git_clean", f"有 {len(changes.splitlines())} 项未提交", changes[:200])
    except FileNotFoundError:
        return _warn("git_clean", "git 未安装")
    except Exception as e:
        return _warn("git_clean", f"检查失败: {e}")


def main() -> int:
    checks = [
        check_version(),
        check_git_clean(),
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
    print("  AI建单助手 — 启动 2 项自检（版本/代码）")
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
