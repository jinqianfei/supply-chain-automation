#!/usr/bin/env python3
"""
check_memory_quality.py — 「好的记忆」质量 4W 检查（v5.9.0 Phase 3-3）

目标：每条记忆带 4W（When/What/Why/Witness）+ 质量分（0-1）

4W 缺失检查：
  - When:  日期（YYYY-MM-DD）
  - What:  客观事实描述
  - Why:   触发原因 / 决策理由
  - Witness: 证据（git sha / 文件路径 / 数据）

质量分计算：
  quality = (has_when + has_what + has_why + has_witness) / 4
         × (verified_recently ? 1.0 : 0.5)
         × (has_evidence ? 1.0 : 0.7)

  - quality >= 0.8: ✅ 高质量
  - 0.5 <= quality < 0.8: ⚠️ 一般
  - quality < 0.5: ❌ 需补全

使用：
  python3 scripts/check_memory_quality.py                # 检查所有 session 日志
  python3 scripts/check_memory_quality.py --file memory/2026-06-08.md  # 检查单个
  python3 scripts/check_memory_quality.py --strict       # quality<0.5 退出非零

启动：launchd 每周六 23:00
"""
import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List


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


def check_4w_in_text(text: str, file_path: Path) -> dict:
    """检查一段文本的 4W 完整度"""
    has_when = False
    has_what = False
    has_why = False
    has_witness = False

    # When: YYYY-MM-DD 日期
    date_matches = re.findall(r"202[56]-\d{2}-\d{2}", text)
    if date_matches:
        has_when = True

    # What: 事实描述（句子里有"完成/写/做/改/加"等动词）
    fact_verbs = ["完成", "写", "做", "改", "加", "添加", "创建", "修复", "发现", "加入", "实现", "生成", "测试"]
    if any(v in text for v in fact_verbs):
        has_what = True

    # Why: 触发原因 / 决策理由
    why_indicators = ["触发", "因为", "原因", "理由", "由于", "金姐", "老板", "用户", "指出", "要求", "指定", "问"]
    if any(w in text for w in why_indicators):
        has_why = True

    # Witness: 证据（git sha / 文件路径 / 数据）
    evidence_patterns = [
        r"[0-9a-f]{7,40}",          # git commit sha
        r"\b\w+\.(py|sh|md|sql|json|yaml|yml|pyc)\b",  # 文件扩展名
        r"`[/~][^`]+`",               # 路径
        r"https?://",                  # URL
        r"✅|❌|⚠️|🎉",              # 状态 emoji
        r"\d+%|\d+\.\d+",            # 数字（百分比、小数）
    ]
    if any(re.search(p, text) for p in evidence_patterns):
        has_witness = True

    return {
        "has_when": has_when,
        "has_what": has_what,
        "has_why": has_why,
        "has_witness": has_witness,
    }


def compute_quality(check_result: dict, text: str, file_path: Path) -> dict:
    """计算质量分"""
    base = sum([check_result["has_when"], check_result["has_what"],
                check_result["has_why"], check_result["has_witness"]]) / 4.0

    # 时间新鲜度（mtime < 7 天 → 1.0；30 天 → 0.5；> 30 天 → 0.3）
    try:
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        age_days = (datetime.now() - mtime).days
        if age_days < 7:
            freshness = 1.0
        elif age_days < 30:
            freshness = 0.7
        else:
            freshness = 0.5
    except Exception:
        freshness = 0.5

    # 证据强度（有 git sha / 数据 → 1.0；只有文件名 → 0.8；只有 emoji → 0.7）
    if re.search(r"[0-9a-f]{7,40}", text):
        evidence = 1.0
    elif re.search(r"\d+%|测试 \d+/\d+", text):
        evidence = 1.0
    elif re.search(r"`[^`]+\.(py|sh|md|sql|json|yaml|yml)`", text):
        evidence = 0.8
    else:
        evidence = 0.7

    quality = base * freshness * evidence
    quality = round(quality, 3)

    # 等级
    if quality >= 0.8:
        level = "✅ 高"
    elif quality >= 0.5:
        level = "⚠️  中"
    else:
        level = "❌ 低"

    return {
        "quality": quality,
        "level": level,
        "freshness": freshness,
        "evidence": evidence,
    }


def check_file(file_path: Path) -> dict:
    """检查单个文件"""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"file": str(file_path.relative_to(WORKSPACE)), "error": str(e)}

    check = check_4w_in_text(text, file_path)
    quality = compute_quality(check, text, file_path)

    # 缺哪些 W
    missing = []
    if not check["has_when"]:
        missing.append("When")
    if not check["has_what"]:
        missing.append("What")
    if not check["has_why"]:
        missing.append("Why")
    if not check["has_witness"]:
        missing.append("Witness")

    return {
        "file": str(file_path.relative_to(WORKSPACE)),
        "size_kb": file_path.stat().st_size / 1024,
        "4w": check,
        "quality": quality,
        "missing": missing,
    }


def check_all_files() -> List[dict]:
    """检查所有 session 日志 + MEMORY.md"""
    results = []
    for f in sorted(MEMORY_DIR.glob("2026-*.md")):
        results.append(check_file(f))
    md_file = WORKSPACE / "MEMORY.md"
    if md_file.exists():
        results.append(check_file(md_file))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="记忆质量 4W 检查")
    parser.add_argument("--file", type=str, help="检查单个文件")
    parser.add_argument("--strict", action="store_true", help="quality<0.5 退出非零")
    args = parser.parse_args()

    print("═══════════════════════════════════════════════════════")
    print("  AI建单助手 — 记忆质量 4W 检查 (Phase 3-3)")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═══════════════════════════════════════════════════════")
    print()

    if args.file:
        results = [check_file(WORKSPACE / args.file)]
    else:
        results = check_all_files()

    # 统计
    high = sum(1 for r in results if r.get("quality", {}).get("quality", 0) >= 0.8)
    mid = sum(1 for r in results if 0.5 <= r.get("quality", {}).get("quality", 0) < 0.8)
    low = sum(1 for r in results if r.get("quality", {}).get("quality", 0) < 0.5)

    for r in results:
        if "error" in r:
            print(f"  ❌ {r['file']}: {r['error']}")
            continue

        q = r["quality"]
        missing_str = f" | 缺: {', '.join(r['missing'])}" if r["missing"] else ""
        print(f"  {q['level']} {r['file']} ({r['size_kb']:.1f} KB) — quality={q['quality']}{missing_str}")

    print()
    print(f"  📊 统计: {high} ✅ 高 / {mid} ⚠️ 中 / {low} ❌ 低")
    print()

    if args.strict and low > 0:
        print(f"  🚫 {low} 个文件质量 < 0.5，需补全 (--strict 模式: 退出非零)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
