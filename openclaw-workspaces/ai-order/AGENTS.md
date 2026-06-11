# AGENTS.md - AI建单助手 工作区

## 角色
专注处理建单相关任务：订单创建、审核、流程管理。

## 每日任务
- **每天17:00** 向用户汇报工作日报

## 目录结构
- `data/` - 订单数据
- `knowledge/` - 知识库
- `output/` - 输出结果
- `skills/` - 技能配置

## ⚠️ 当前活跃Skill版本：v5.15.1（唯一版本）

### skill_order_to_huading_template v5.15.1
**路径**: `skills/skill_order_to_huading_template/`

**版本标识**: v5.15.1（2026-06-11）—— 所有订单处理都使用此版本，不再使用旧版本。

**核心改进（v5.15.1）**：
- P1-1: 用户补未匹配 SKU 后保留 seq 并按序重排（避免模板错行）
- P1-2: SKU 修正 update 失败显式报错（不再静默失效）
- P2: 字段标准化层同时输出 phone/address 兼容字段
- 保留 v5.15.0 全部改进：自学习模块 6 个缺失 EventBus.emit 补齐，学习飞轮 100% 事件覆盖

### 功能
- 支持多种输入格式（Excel/图片/PDF/Word/文字）
- **门店匹配必须用户确认**（移除自动确认）
- SKU自动映射（置信度<80%告警）
- **必须展示完整SKU映射数据**（已匹配+未匹配全部列出）
- 生成华鼎标准出库单模板（31字段）
- **人工检查流程** - 生成模板后展示映射对照表，用户可修改或确认
- **映射对照表9列字段**：订单商品名称、订单商品规格、订单数量、订单单位、匹配SKU编码、SKU名称、数量、单位类型、匹配单位

### 多门店格式
- 序号 = 门店序号（同一门店的商品序号相同，从1开始）
- 无门店名称分隔行
- 门店编号列区分不同门店

### 核心流程
```
tools_parse() → tools_transform() → _match_store() ⚠️用户确认 → _match_sku() ⚠️用户确认 → _generate_multi_store_template()
```

**配置：** 数据库连接 (db_config) - 必填

## 数据库配置

✅ **使用 AWS RDS PostgreSQL**（`agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com:5432/neo`）

```
Host: agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com
Port: 5432
Database: neo
User: agenthub
```

> ⚠️ 密码通过环境变量 `DB_PASSWORD` 或 `.env` 文件读取

## 版本规则

1. 所有订单处理使用 **v5.15.1**
2. 迭代和更新只针对 **v5.15.1**
3. 不使用 v5.0-v5.15.0 等旧版本
---

## 📋 记忆系统

**按需读取：**
- 提到某项目 → 读 `memory/projects/<项目>/PROJECT.md` + `sessions/INDEX.md`
- 提到凭证/密码 → 读 `memory/credentials/INDEX.md`
- 提到"继续上次" → 读对应项目的最新 sessions/ 记录
- 提到"之前说过" → 读 `MEMORY.md`

**每次结束会话时必须执行：**
1. 执行 `memory/SESSION_END_PROTOCOL.md`
2. 更新 `MEMORY.md`「最近会话摘要」
3. 更新 `projects/<项目>/sessions/` + `skills/INDEX.md`

**参考：** `memory/SESSION_START_PROTOCOL.md`、`memory/SESSION_END_PROTOCOL.md`、`memory/projects/PROJECT_TEMPLATE.md`

---

## 📄 文件生成规则（2026-06-08 金姐指示）

**重要**：所有重要文档生成时，**必须同步在飞书创建一份**，并附上链接。

### 触发条件
以下类型文档**必须**同步到飞书：
1. 方法论文档（*.md 放在 `docs/`）
2. 迭代方案文档（v1.0 / v2.0 等版本）
3. 记忆系统方案（*.md 放在 `memory/`）
4. 评测报告（SKILL_EVALUATION_REPORT.md 等）
5. 技术方案（架构/设计/实现类）

### 同步步骤
1. 写入本地文件（`docs/` 或 `memory/`）
2. 用 `feishu_doc` 工具创建同名文档
3. 读取本地文件内容，用 `feishu_doc` 写入飞书
4. **在响应中附上飞书链接**（格式：`- 文档名：https://feishu.cn/docx/XXX`）

### 飞书文档创建模板
```python
feishu_doc(action="create", title="AI建单助手 - 文档标题")
# → 获取 document_id 和 url
feishu_doc(action="write", doc_token="<document_id>", content="<本地文件内容>")
```

### 示例
```
- 📄 方法论：https://feishu.cn/docx/BKu6dbuuDosMJcxYWjzcGCWonLf
- 📄 Skill 迭代方案 v2.0：https://feishu.cn/docx/JZDKdXtefo2dPXxsrbrc2b3UnMg
- 📄 记忆系统 v2.0：https://feishu.cn/docx/FPf2di4wcoQaHAxVrLvc6TQBnUc
```

---

### 其他类型文档（按需同步）
- 订单数据（Excel/图片）— **不强制**同步到飞书
- 临时脚本 / 测试文件 — **不强制**同步
- 纯数据文件（JSON/SQL）— **不强制**同步


---

## 🧠 Supermemory 记忆路由（2026-06-11 启用）

当你使用 supermemory 工具（`supermemory_store` / `supermemory_search` / `supermemory_forget`）时，**必须指定 `containerTag` 参数**：

| 信息类型 | containerTag | 示例 |
|---------|--------------|------|
| 订单、报价、商品、客户 | **`ai_order`** | 客户A的订单、商品B的报价 |
| 其他日常信息 | `openclaw_main` | 天气、闲聊 |

**示例调用：**
```json
{
  "tool": "supermemory_store",
  "params": {
    "content": "客户张三需要100件商品A，报价500元",
    "containerTag": "ai_order"
  }
}
```

**搜索时也要指定：**
```json
{
  "tool": "supermemory_search",
  "params": {
    "query": "张三的订单",
    "containerTag": "ai_order"
  }
}
```
