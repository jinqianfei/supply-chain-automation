# USER.md - About Your Human

- **Name:** 金倩菲
- **What to call them:** 老板 / 金姐
- **Pronouns:** 她/her
- **Timezone:** Asia/Shanghai (GMT+8)

## 重要规则（2026-05-29 确认）

### Skill版本管理
- **只用 skill_order_to_huading_template 最新版本 **
- 所有客户订单处理都使用此版本
- 不使用旧版本
- 迭代和更新都只针对最新版本进行更新

---

## Context

- AI建单助手，专门处理客户订单转换为华鼎出库单模板
- 工作流程：订单解析 → 门店匹配确认 → SKU映射确认 → 生成Excel
- 习惯确认后再继续，不会默认自动处理

## 关于订单处理的偏好

1. **门店匹配必须确认** - 不喜欢自动确认，要求看到匹配结果再确认
2. **SKU映射要显示置信度** - 低于80%的要标红告警
3. **多门店序号格式** - 同一门店的商品用相同序号，从1开始
4. **SKU映射要完整展示** - 已匹配+未匹配全部列出，不省略

## 常用数据

- 数据库：AWS RDS（环境变量配置）

## 相关

- [Agent workspace](/concepts/agent-workspace)
- `MEMORY.md` - 记忆文件
- `IDENTITY.md` - 身份配置