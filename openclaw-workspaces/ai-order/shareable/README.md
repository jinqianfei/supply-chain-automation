# skill_order_to_huading_template

> 客户订单（Excel / 图片 / PDF / Word / 文字）→ 华鼎标准出库单（31 字段 xlsx）
> **当前版本**: v5.11.1（2026-06-09）

## 这是什么？

一个 OpenClaw Skill，把客户订单（任意格式）自动转成华鼎 ERP 系统的标准出库单模板。

**核心能力**：
- 🧠 **多格式解析**：Excel / 图片 / PDF / Word / 文字
- 🏪 **门店匹配**：自动从门店名称找货主 ID + 仓库编码
- 📦 **SKU 映射**：5 层模糊匹配（精确 / 别名 / 关键词 / Layer 2-3 模糊）
- 📊 **生成 31 字段 xlsx**：完全符合华鼎出库单规范
- 🔄 **自适应学习**：订单处理反馈 + 5 层匹配成功率统计

**端到端准确率（v5.11.1 测试）**：12/12 = 100% GT 准确率（2 个真实订单共 12 个商品）。

## 安装

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
psql -h <your-db-host> -U <user> -d <database> -f schema.sql
```

会创建 5 张核心表：
- `product_sku`（SKU 主表）
- `product_name_alias`（商品名别名）
- `store_list`（门店数据）
- `warehouse_code_mapping`（仓库编码）
- `customer`（货主信息）

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的真实 DB / LLM 配置
```

### 4. 导入数据

把 `product_sku` / `product_name_alias` / `store_list` / `warehouse_code_mapping` / `customer` 数据导入数据库。
（数据来源由你方提供，本 skill 不包含示例数据）

## 使用

### Python 调用

```python
from skill_order_to_huading_template import OrderToHuadingTemplate

skill = OrderToHuadingTemplate(
    db_config={
        "host": "your-db-host.amazonaws.com",
        "port": 5432,
        "database": "neo",
        "user": "your_user",
        "password": "your_password",
    }
)

# 处理 Excel 订单
result = skill.execute(order_input="订单.xlsx", order_type="excel")

print(f"匹配 {result['matched_count']}/{result['item_count']}")
print(f"输出文件: {result['output_file']}")
```

### 支持的 order_type

| 类型 | 说明 | 备注 |
|------|------|------|
| `"auto"` | 自动检测（默认）| 推荐 |
| `"excel"` | Excel 文件 | .xlsx / .xls |
| `"image"` | 图片 | 需先 OCR |
| `"pdf"` | PDF | 需先文本提取 |
| `"word"` | Word 文档 | .docx |
| `"text"` | 纯文字 | 直接传字符串 |

## 配置项

通过环境变量（`.env`）或 `db_config` 参数：

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DB_HOST` | ✅ | — | PostgreSQL 主机 |
| `DB_PORT` | ❌ | 5432 | 端口 |
| `DB_NAME` | ✅ | — | 数据库名 |
| `DB_USER` | ✅ | — | 用户名 |
| `DB_PASSWORD` | ✅ | — | 密码（**不要**提交到 git）|
| `DB_SSLMODE` | ❌ | prefer | SSL 模式 |
| `OPENAI_API_KEY` | ❌ | — | OpenAI API key（可选）|
| `MINIMAX_API_KEY` | ❌ | — | MiniMax API key（可选）|

**LLM 提供商** 在 `config/llm.yaml` 配置。默认使用 OpenClaw 平台内嵌模型（无需 API key）。

## 系统要求

- Python ≥ 3.10
- PostgreSQL ≥ 12（建议 14+，需要 `pg_trgm` 扩展以支持 GIN trgm 索引）
- 磁盘 ≥ 100 MB

## 安全

- ⚠️ **不要**提交 `.env` 到 git
- ⚠️ **不要**在代码里硬编码密码
- ⚠️ 公开分发前跑 `clawhub-skill-vetting` 安全审核

## License

Apache 2.0（详见 [LICENSE](./LICENSE)）

## 联系

提交 Issue 或联系 skill 维护者。
