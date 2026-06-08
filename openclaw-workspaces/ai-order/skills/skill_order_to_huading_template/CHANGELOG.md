# Changelog

All notable changes to this skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.9.0] - 2026-06-05

### Added
- **技术锁**：`OrderToHuadingTemplate` 类通过 `__getattribute__` 拦截内部函数调用
- 防止 AI 跳过 `execute()` 主入口直接调用 `_match_store()` / `_match_sku()` 等内部函数
- 公开接口白名单机制：`execute()` / `parse_only()` / `validate_db()` / `get_version()`

### Changed
- 所有内部方法（`_` 前缀）通过 `__内部初始化__` 字典存储，对外不可见
- AI 必须通过 `skill.execute()` 入口调用

### Notes
- 本次修改的对话背景：5.9.1 增量 patch（仅 bump VERSION）被 reset 撤销，但 5.9.0 主体（技术锁）保留
- SKILL.md 头 5.9 与 VERSION/CHANGELOG 此前未同步，本次补齐

---

## [5.8.0] - 2026-06-01

### Added
- 数据库合并：`product_sku` + `product_name_alias` 双表支持
- SKU 匹配 5 层逻辑（精确→模糊→别名→规格→兜底）
- 新增 `product_name_alias` 表（商品名别名表），支持 102+ 条别名记录

### Changed
- 订单解析流程优化，支持更多输入格式

### Fixed
- SKU 匹配兜底逻辑修复

---

## Template

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- 新增功能说明

### Changed
- 变更内容说明

### Fixed
- 修复的问题

### Notes
- 本次修改的对话背景 session: om_xxx
```