#!/usr/bin/env python3
"""
extract_memory.py — MEMORY.md 自动提取（v5.9.0 Phase 3-2）

目标：从 session 日志 + git log + PENDING.md 自动生成 MEMORY.md 摘要

输入：
  - memory/2026-XX-XX.md（最近 7 天的 session 日志）
  - memory/projects/ai-order/problems/PENDING.md
  - git log -10（最近 10 个 commit）
  - 数据库（order_feedback 统计）

输出：
  - MEMORY.md 的"## 最近会话摘要"段（替换更新）
  - 其余段保持原样

使用：
  python3 scripts/extract_memory.py          # 生成摘要到 stdout
  python3 scripts/extract_memory.py --apply  # 替换 MEMORY.md 的会话摘要段
  python3 scripts/extract_memory.py --days 14  # 改窗口（默认 7）

启动：launchd 每日 11:00（daily_wrap 后）
"""
import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


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
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_MD = WORKSPACE / "MEMORY.md"
PENDING_MD = WORKSPACE / "memory" / "projects" / "ai-order" / "problems" / "PENDING.md"


def get_recent_session_files(days: int = 7) -> list:
    """获取最近 N 天的 session 日志"""
    cutoff = datetime.now() - timedelta(days=days)
    files = []
    for f in MEMORY_DIR.glob("2026-*.md"):
        # 文件名格式: 2026-06-08.md 或 2026-06-04-to-07.md
        m = re.match(r"2026-(\d{2})-(\d{2})", f.name)
        if m:
            try:
                file_date = datetime(2026, int(m.group(1)), int(m.group(2)))
                if file_date >= cutoff:
                    files.append((file_date, f))
            except ValueError:
                pass
    return sorted(files, key=lambda x: x[0], reverse=True)


def extract_session_summary(session_file: Path) -> dict:
    """从一个 session 日志提取关键信息"""
    try:
        text = session_file.read_text(encoding="utf-8")
    except Exception:
        return {"file": session_file.name, "title": "（无法读取）", "bullets": []}

    # 提取标题（第一个 # 标题）
    title_match = re.search(r"^#\s+(.+?)$", text, re.MULTILINE)
    title = title_match.group(1) if title_match else session_file.stem

    # 提取关键 bullet（## / ### 下）
    bullets = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 完成项
        if line.startswith("- [x]") or line.startswith("✅"):
            bullets.append(f"- ✅ {re.sub(r'^- \[x\] |^✅ ?', '', line)[:80]}")
        # 关键决策
        elif line.startswith("**") and "决定" in line:
            bullets.append(f"- 📌 {line[:80]}")
        # 学习
        elif "学到的教训" in line or "关键学习" in line:
            bullets.append(f"- 💡 {line[:80]}")
        # bug
        elif "bug" in line.lower() and "修复" in line:
            bullets.append(f"- 🐛 {line[:80]}")

    return {
        "file": session_file.name,
        "title": title,
        "bullets": bullets[:10],  # 限制每文件最多 10 条
    }


def get_git_recent(n: int = 10) -> list:
    """获取最近 N 个 git commit"""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline"],
            capture_output=True, text=True, timeout=10,
            cwd=str(WORKSPACE)
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except Exception:
        return []


def get_pending_summary() -> str:
    """从 PENDING.md 提取紧急+进行中项"""
    if not PENDING_MD.exists():
        return ""
    text = PENDING_MD.read_text(encoding="utf-8")

    urgent = []
    in_progress = []
    current = None
    for line in text.split("\n"):
        if "🔴 紧急" in line:
            current = "urgent"
        elif "🟡 进行中" in line:
            current = "progress"
        elif "✅ 已完成" in line:
            current = "done"
        elif current in ("urgent", "progress") and line.startswith("| P-"):
            m = re.match(r"\|\s*(P-\d+)\s*\|\s*(\S+)\s*\|\s*([^|]+?)\s*\|", line)
            if m:
                pid, date, todo = m.groups()
                target = urgent if current == "urgent" else in_progress
                target.append(f"  - `{pid}` ({date}): {todo.strip()[:60]}")

    out = []
    if urgent:
        out.append("**🔴 紧急**：")
        out.extend(urgent)
    if in_progress:
        out.append("**🟡 进行中**：")
        out.extend(in_progress)
    return "\n".join(out)


def build_summary(days: int = 7) -> str:
    """构建 MEMORY.md 摘要段"""
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    # 1. session 摘要
    sessions = []
    for fdate, f in get_recent_session_files(days):
        s = extract_session_summary(f)
        sessions.append(s)

    # 2. git 最近
    git_lines = get_git_recent(5)

    # 3. PENDING 摘要
    pending = get_pending_summary()

    # 组装
    out = []
    out.append(f"### {sessions[0]['file'][:-3] if sessions else '今天'} — 自动提取摘要")
    out.append("")
    out.append(f"**生成时间**：{now.strftime('%Y-%m-%d %H:%M GMT+8')}")
    out.append(f"**窗口**：最近 {days} 天")
    out.append("")

    if sessions:
        out.append("**📅 Session 摘要**：")
        for s in sessions:
            out.append(f"- **{s['file']}** — {s['title'][:60]}")
            for b in s["bullets"][:5]:  # 每 session 最多 5 条 bullet
                out.append(f"  {b}")
        out.append("")

    if git_lines:
        out.append("**🔧 最近代码变更**（git log）：")
        for line in git_lines:
            out.append(f"- `{line}`")
        out.append("")

    if pending:
        out.append("**📋 待办追踪**（PENDING.md）：")
        out.append(pending)
        out.append("")

    return "\n".join(out)


def apply_to_memory_md(summary: str) -> None:
    """把摘要替换到 MEMORY.md 的"## 最近会话摘要"段"""
    if not MEMORY_MD.exists():
        print("  ❌ MEMORY.md 不存在")
        return

    text = MEMORY_MD.read_text(encoding="utf-8")

    # 找到 "## 最近会话摘要" 段
    start_match = re.search(r"^## 最近会话摘要\s*$", text, re.MULTILINE)
    if not start_match:
        print("  ❌ MEMORY.md 找不到 '## 最近会话摘要' 段")
        return

    # 找到下一个 ## 段（"## 数据库架构" 之类）
    start_pos = start_match.end()
    next_section = re.search(r"^##\s+\S+", text[start_pos:], re.MULTILINE)
    end_pos = start_pos + (next_section.start() if next_section else len(text) - start_pos)

    # 替换
    new_text = text[:start_pos] + "\n" + summary + "\n" + text[end_pos:]

    # 备份 + 写
    backup = MEMORY_MD.with_suffix(".md.bak")
    backup.write_text(text, encoding="utf-8")
    MEMORY_MD.write_text(new_text, encoding="utf-8")
    print(f"  ✅ MEMORY.md 已更新（备份: {backup.name}）")


def main() -> int:
    parser = argparse.ArgumentParser(description="MEMORY.md 自动提取")
    parser.add_argument("--apply", action="store_true", help="替换 MEMORY.md")
    parser.add_argument("--days", type=int, default=7, help="窗口天数（默认 7）")
    args = parser.parse_args()

    print("═══════════════════════════════════════════════════════")
    print("  AI建单助手 — MEMORY.md 自动提取 (Phase 3-2)")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═══════════════════════════════════════════════════════")
    print()

    summary = build_summary(args.days)
    print(summary)

    if args.apply:
        print("▶ 应用到 MEMORY.md...")
        apply_to_memory_md(summary)
    else:
        print("  (用 --apply 才会修改 MEMORY.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
