# skill-order-to-huading-template

将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎31字段出库单模板的完整流程。

## 版本

**当前版本**: v5.15.1

## 核心功能

- 多格式输入支持（Excel/图片/PDF/文字/Word）
- 门店智能匹配（6层匹配逻辑 + 2层兜底）
- SKU自动映射（5层匹配逻辑）
- 人工确认流程（门店确认 + SKU确认）
- 生成华鼎标准出库单模板（31字段）

## 目录结构

```
skill_order_to_huading_template/
├── SKILL.md              # Skill 定义文档
├── __init__.py           # 主入口
├── config/
│   ├── db_config.yaml    # 数据库配置（可选，优先使用环境变量）
│   ├── llm.yaml          # LLM provider 配置
│   └── template_defaults.yaml
├── db/
│   └── connection.py     # 数据库连接
├── tools/
│   ├── _order_parser.py       # 订单解析
│   ├── _field_transformer.py  # 字段标准化
│   ├── _store_matcher.py      # 门店匹配
│   ├── _sku_mapper.py         # SKU映射
│   └── _template_generator.py # 模板生成
└── scripts/
    └── test_*.py         # 回归测试
```

## 配置

推荐使用环境变量或项目父目录 `.env`：

```bash
DB_HOST=your_db_host
DB_PORT=5432
DB_NAME=neo
DB_USER=your_username
DB_PASSWORD=your_password
```

也可以直接维护 `config/db_config.yaml`。

## 使用

通过 OpenClaw AI 建单助手使用。正常入口只有 `OrderToHuadingTemplate.execute()`；门店确认和 SKU 确认都需要把上一步返回的 `order_data_cache` 传回去继续。
