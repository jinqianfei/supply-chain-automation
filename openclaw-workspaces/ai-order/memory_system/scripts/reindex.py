#!/usr/bin/env python3
"""
reindex_memory.py — 重建 memory_search 索引（v5.9.0 Phase 3-1）

目标：把 skills/ + database/ + docs/ 也纳入 memory_search 可搜索范围

当前 memory_search 工具已索引：
  ✅ MEMORY.md
  ✅ memory/*.md

未索引（Phase 3-1 后补齐）：
  🆕 skills/**/*.md
  🆕 skills/**/*.py（关键代码）
  🆕 database/**/*.sql
  🆕 docs/**/*.md
  🆕 memory/projects/**/*.md

实施策略：
  1. 生成 .memory_index/ 目录（含 .txt 摘要 + .json 元数据）
  2. 写 .memory_index/README.md 描述索引结构
  3. 写 search_index.py 提供本地搜索 API

使用：
  python3 memory_system/scripts/reindex.py          # 重建索引
  python3 memory_system/scripts/reindex.py --check   # 检查索引健康
  python3 memory_system/scripts/reindex.py --query "version_check"  # 试搜

启动：launchd 每周日凌晨 03:00
"""
import os
import re
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime


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
INDEX_DIR = WORKSPACE / ".memory_index"

# 索引范围
INDEX_PATTERNS = [
    "MEMORY.md",
    "memory/2026-*.md",
    "memory/MEMORY_SYSTEM_PLAN.md",
    "memory/projects/**/*.md",
    "memory/SESSION_*.md",
    "memory/PENDING_*.md",
    "skills/**/*.md",
    "skills/**/*.py",       # 关键代码（限 100KB 以下）
    "database/**/*.sql",
    "docs/**/*.md",
]

# 排除
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".git",
    ".DS_Store",
    "node_modules",
    "*.pyc",
    ".bak",
    "*.bak",
]

# 单文件大小限制
MAX_FILE_SIZE = 100 * 1024  # 100KB


def should_index(path: Path) -> bool:
    """判断文件是否应该被索引"""
    # 排除
    for ex in EXCLUDE_PATTERNS:
        if ex in str(path):
            return False
    # 大小限制
    if path.stat().st_size > MAX_FILE_SIZE:
        return False
    return True


def extract_keywords(content: str) -> list:
    """从内容中提取关键词（中文+英文）"""
    # 简单实现：提取 长度≥2 的中文字符串 和 长度≥3 的英文单词
    zh = re.findall(r'[\u4e00-\u9fff]{2,}', content)
    en = re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}', content)
    # 合并去重
    keywords = list(set(zh + en))
    # 排除停用词
    STOP = {"the", "and", "for", "with", "this", "that", "from", "have", "are", "was", "were", "been", "will", "would", "could", "should", "def", "class", "import", "from", "return", "self", "True", "False", "None", "的", "是", "在", "了", "和", "也", "都", "就", "不", "要", "有", "没", "上", "下", "用", "对", "为", "而", "于", "到", "这", "那"}
    keywords = [k for k in keywords if k.lower() not in STOP and len(k) >= 2]
    return keywords


def build_index(force: bool = False) -> int:
    """构建索引，返回索引文件数"""
    INDEX_DIR.mkdir(exist_ok=True)
    index_data = {
        "version": "1.0",
        "built_at": datetime.now().isoformat(),
        "workspace": str(WORKSPACE),
        "files": [],
        "keywords": {},  # keyword -> [file_paths]
    }

    file_count = 0
    for pattern in INDEX_PATTERNS:
        for path in WORKSPACE.glob(pattern):
            if not path.is_file():
                continue
            if not should_index(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(path.relative_to(WORKSPACE))
            file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
            file_size = path.stat().st_size
            file_mtime = path.stat().st_mtime

            entry = {
                "path": rel,
                "size": file_size,
                "mtime": file_mtime,
                "hash": file_hash,
                "keywords": [],
            }

            # 提取关键词
            kws = extract_keywords(content)
            entry["keywords"] = kws[:50]  # 限制关键词数
            for kw in kws:
                index_data["keywords"].setdefault(kw, [])
                if rel not in index_data["keywords"][kw]:
                    index_data["keywords"][kw].append(rel)

            index_data["files"].append(entry)
            file_count += 1

    # 写索引文件
    index_file = INDEX_DIR / "index.json"
    index_file.write_text(json.dumps(index_data, ensure_ascii=False, indent=1))
    print(f"  ✅ 索引构建完成：{file_count} 个文件")
    print(f"  📦 索引文件: {index_file.relative_to(WORKSPACE)}")
    print(f"  🔑 关键词数: {len(index_data['keywords'])}")

    # 写 README
    readme = INDEX_DIR / "README.md"
    readme.write_text(f"""# Memory Index v{index_data['version']}

构建时间: {index_data['built_at']}
文件数: {len(index_data['files'])}
关键词数: {len(index_data['keywords'])}

## 搜索方法

```bash
# 用 reindex_memory.py 试搜
python3 memory_system/scripts/reindex.py --query "version_check"
python3 memory_system/scripts/reindex.py --query "断档"
```

## 索引范围

{chr(10).join('- `' + p + '`' for p in INDEX_PATTERNS)}

## 排除

{chr(10).join('- `' + p + '`' for p in EXCLUDE_PATTERNS)}
""")
    print(f"  📄 README: {readme.relative_to(WORKSPACE)}")
    return file_count


def check_index() -> int:
    """检查索引健康度"""
    index_file = INDEX_DIR / "index.json"
    if not index_file.exists():
        print("  ❌ 索引不存在，需要先 build")
        return 1

    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ❌ 索引 JSON 解析失败: {e}")
        return 1

    file_count = len(data["files"])
    keyword_count = len(data["keywords"])
    built_at = data.get("built_at", "unknown")

    print(f"  📋 索引健康检查")
    print(f"     版本:     {data.get('version', 'unknown')}")
    print(f"     构建时间: {built_at}")
    print(f"     文件数:   {file_count}")
    print(f"     关键词数: {keyword_count}")

    # 重新扫描，对比是否有新增/删除
    current_files = set()
    for pattern in INDEX_PATTERNS:
        for path in WORKSPACE.glob(pattern):
            if path.is_file() and should_index(path):
                current_files.add(str(path.relative_to(WORKSPACE)))

    indexed_files = {f["path"] for f in data["files"]}
    new = current_files - indexed_files
    removed = indexed_files - current_files
    if new:
        print(f"  ⚠️  有 {len(new)} 个新文件未索引")
    if removed:
        print(f"  ⚠️  索引中有 {len(removed)} 个文件已不存在")
    if not new and not removed:
        print(f"  ✅ 索引与文件系统一致")

    return 0


def query_index(query: str) -> int:
    """在索引中搜索关键词"""
    index_file = INDEX_DIR / "index.json"
    if not index_file.exists():
        print("  ❌ 索引不存在，请先 build")
        return 1

    data = json.loads(index_file.read_text(encoding="utf-8"))

    # 关键词查找
    matched_files = set()
    for kw, files in data["keywords"].items():
        if query.lower() in kw.lower():
            matched_files.update(files)

    if not matched_files:
        print(f"  ❌ 未找到匹配 '{query}' 的文件")
        return 1

    # 排序：按文件大小倒序（重要的文件通常更大）
    file_size_map = {f["path"]: f["size"] for f in data["files"]}
    sorted_files = sorted(matched_files, key=lambda p: file_size_map.get(p, 0), reverse=True)

    print(f"  🔍 '{query}' 匹配 {len(sorted_files)} 个文件（前 10）:")
    for f in sorted_files[:10]:
        size_kb = file_size_map.get(f, 0) / 1024
        print(f"     - {f} ({size_kb:.1f} KB)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="memory_search 索引管理")
    parser.add_argument("--check", action="store_true", help="检查索引健康")
    parser.add_argument("--query", type=str, help="搜索关键词")
    args = parser.parse_args()

    print("═══════════════════════════════════════════════════════")
    print("  AI建单助手 — Memory Index (Phase 3-1)")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═══════════════════════════════════════════════════════")
    print()

    if args.check:
        return check_index()
    if args.query:
        return query_index(args.query)

    # 默认 build
    build_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
