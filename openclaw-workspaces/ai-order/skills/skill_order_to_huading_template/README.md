# skill-order-to-huading-template

将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎31字段出库单模板的完整流程。

## 版本

**当前版本**: v5.8

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
│   └── db_config.yaml    # 数据库配置（需手动填写）
├── db/
│   └── connection.py      # 数据库连接
├── tools/
│   ├── order_parser.py   # 订单解析
│   ├── field_transformer.py  # 字段标准化
│   ├── store_matcher.py  # 门店匹配
│   ├── sku_mapper.py     # SKU映射
│   └── template_generator.py  # 模板生成
└── docs/
    └── test_data/        # 测试数据
```

## 配置

1. 复制 `config/db_config.yaml.example` 为 `config/db_config.yaml`
2. 填写数据库连接信息

## 使用

通过 OpenClaw AI 建单助手使用。
