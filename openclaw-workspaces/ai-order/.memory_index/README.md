# Memory Index v1.0

构建时间: 2026-06-12T10:46:26.727865
文件数: 145
关键词数: 13804

## 搜索方法

```bash
# 用 reindex_memory.py 试搜
python3 scripts/reindex_memory.py --query "version_check"
python3 scripts/reindex_memory.py --query "断档"
```

## 索引范围

- `MEMORY.md`
- `memory/2026-*.md`
- `memory/MEMORY_SYSTEM_PLAN.md`
- `memory/projects/**/*.md`
- `memory/SESSION_*.md`
- `memory/PENDING_*.md`
- `skills/**/*.md`
- `skills/**/*.py`
- `database/**/*.sql`
- `docs/**/*.md`

## 排除

- `__pycache__`
- `.git`
- `.DS_Store`
- `node_modules`
- `*.pyc`
- `.bak`
- `*.bak`
