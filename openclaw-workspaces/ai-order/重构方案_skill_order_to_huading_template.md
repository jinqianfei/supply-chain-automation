# 🏗️ skill_order_to_huading_template 重构方案

> 基于 2026-05-28 讨论，最终版

---

## 一、背景与目标

### 现状问题

| 问题 | 表现 |
|:----|:-----|
| **耦合度高** | 解析→门店匹配→SKU映射→生成模板都在一个大流程里，改一处牵全身 |
| **调试困难** | 出错了得从头跑，没法单独重试某一步 |
| **不可复用** | 门店匹配、SKU映射逻辑没法让其他skill调用 |
| **规则硬编码** | 字段映射写在Python代码里，新客户新格式就得改代码 |
| **SKILL.md不干净** | 混入了代码脚本，不适合做纯文档 |

### 设计原则

- **每个工具可独立调用、可调试**：输入→输出，职责单一
- **规则与代码分离**：新客户只写规则配置，不改代码
- **数据库独立**：各repo只做一件事，迁移或改ORM只需动db层
- **AI + 规则结合**：LLM做自由解析，规则库做标准化校正，两者互补
- **SKILL.md纯文档**：只保留流程、逻辑、注意事项、工具调用说明，不放代码

---

## 二、核心流程

```
┌─────────────────────────────────────────────┐
│ ① order_parser                              │
│   输入: 客户订单(Excel/图片/PDF/文字/Word)    │
│   处理: LLM解析内容（保持现有AI解析能力）      │
│   输出: 原始结构化JSON                       │
│   例: {"商品名称":"潮迹潮汕牛肉丸","数量":"2"} │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│ ② field_transformer                         │
│   输入: 原始结构化JSON + 客户识别结果          │
│   处理: 加载对应规则 → 校正字段名             │
│         → 校验必填项 → 校正值格式             │
│   输出: 统一结构化JSON ✅                    │
│   例: {"product_name":"潮迹潮汕牛肉丸",       │
│         "quantity":2, "unit":"箱"}           │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│ ③ store_matcher                             │
│   输入: 统一JSON中的门店名                    │
│   处理: 数据库模糊匹配 → 获取货主ID          │
│   输出: 门店信息 + 货主ID (待确认)            │
└──────────────────┬──────────────────────────┘
                   │
             ╔═════╧══════════╗
             ║ ④ 货主确认     ║  ← 人工环节，必须等待
             ║ (用户确认)     ║
             ╚═════╤══════════╝
                   │
┌──────────────────▼──────────────────────────┐
│ ⑤ sku_mapper                               │
│   输入: 统一JSON商品名 + 货主ID              │
│   处理: 数据库模糊匹配 → 获取SKU编码          │
│         → 匹配到的SKU的unit_conversion_rule   │
│         → 判断单位类型(大单位/小单位)        │
│   输出: SKU映射结果 + 置信度                 │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│ ⑥ template_generator                        │
│   输入: 门店信息 + SKU映射 + 统一JSON        │
│   处理: 按华鼎固定31字段模板填充              │
│   输出: .xlsx 出库单文件                      │
└──────────────────┬──────────────────────────┘
                   │
             ╔═════╧══════════╗
             ║ ⑦ 人工检查     ║  ← 展示映射对照表
             ║ (确认/修改)    ║     支持修改后重生成
             ╚════════════════╝
```

### 关键说明

- **单位类型不提前转换**：客户订单中的"箱/件/袋"是原始单位，SKU映射匹配后，根据 `unit_conversion_rule` 中的配置判断该SKU的大单位/小单位，再确定最终的单位类型字段
- **规则库只校正LLM解析结果**：不做单位转换、不做字段值衍生，只做"字段名标准化 + 值格式校验"
- **华鼎31字段模板固定不变**：不参与规则配置

---

## 三、目录结构

```
skill_order_to_huading_template/
│
├── SKILL.md                      ← 纯文档：流程、逻辑、注意事项、工具调用说明
│
├── tools/                        ← 独立可调用的工具模块
│   ├── __init__.py
│   ├── order_parser.py            LLM解析客户订单 → 原始结构化JSON
│   ├── field_transformer.py       规则库校正 → 统一结构化JSON
│   ├── store_matcher.py           门店匹配 → 获取货主ID
│   ├── sku_mapper.py              SKU映射 + 单位类型判断
│   └── template_generator.py      生成华鼎31字段出库单模板
│
├── db/                            ← 数据库层独立
│   ├── __init__.py
│   ├── connection.py              连接管理（读取config/db_config.yaml）
│   ├── store_repo.py              store_list 表查询
│   ├── sku_repo.py                shipper_sku_mapping 表查询
│   └── customer_repo.py           customer 表查询
│
├── field_mapping/                 ← 字段映射规则库
│   ├── rules/
│   │   ├── default.yaml           兜底规则
│   │   ├── 创宇.yaml              创宇订单格式的字段映射规则
│   │   └── ...                    其他客户按需添加
│   ├── schemas/
│   │   └── unified_order.json     统一结构化JSON的标准schema定义
│   ├── transformer.py             规则引擎：加载规则 → 校正 → 校验
│   └── __init__.py
│
└── config/                        ← 配置文件
    ├── db_config.yaml              数据库连接配置
    └── template_defaults.yaml      华鼎模板的默认值配置
```

---

## 四、各组件详细设计

### 1. order_parser.py — 订单解析

```python
"""
功能：解析任意格式的客户订单
输入：文件路径 或 文本内容
处理：调用LLM进行结构化理解
输出：原始结构化JSON

支持格式：
  - Excel (.xlsx, .xls)
  - 图片 (.jpg, .png, 截图等 → 含OCR预处理)
  - PDF (文字提取 + OCR)
  - Word (.docx)
  - 纯文本（直接粘贴）

输出示例：
{
    "fields": {
        "商品名称": "潮迹潮汕牛肉丸",
        "规格": "500g*20",
        "数量": "2",
        "销售单位": "箱",
        "往来单位名称": "天津滨海新区-塘沽万达店",
        "结算单位电话": "13389973152",
        "结算单位详细地址": "天津市..."
    },
    "raw_text": "原始文本/OCR全文",
    "file_info": {"name": "xxx.xlsx", "type": "excel"}
}
"""
```

### 2. field_mapping/rules/ — 字段映射规则库

规则库的作用：LLM解析虽然灵活，但同一个客户不同订单的字段名可能飘移。规则库将LLM输出的各种别名统一为标准字段。

```yaml
# field_mapping/rules/创宇.yaml
customer_name: "盐城市创宇食品有限公司"
description: "创宇订单字段映射规则"

field_aliases:
  # LLM可能输出的字段名 → 统一字段名
  "商品名称": product_name
  "商品名": product_name
  "品名": product_name
  "货品名称": product_name
  "产品名称": product_name

  "规格": product_spec
  "包装规格": product_spec
  "包装": product_spec

  "数量": quantity
  "订购量": quantity
  "件数": quantity
  "订货数量": quantity
  "出库数量": quantity

  "销售单位": unit
  "单位": unit
  "计量单位": unit

  "往来单位名称": store_name
  "门店名称": store_name
  "门店": store_name
  "收货门店": store_name

  "结算单位电话": store_phone
  "联系电话": store_phone
  "电话": store_phone
  "手机号": store_phone

  "结算单位详细地址": store_address
  "详细地址": store_address
  "地址": store_address
  "收货地址": store_address

validation:
  required:
    - product_name
    - quantity
    - store_name
  types:
    quantity: [int, float, str]   # 支持字符串"2"转数值
    store_name: str
  range:
    quantity: {min: 1}

correction:
  # 值标准化（可选，确保单位用标准名称）
  unit:
    "箱": 箱
    "件": 件
    "包": 包
    "袋": 袋
```

**统一JSON的schema（unified_order.json）：**

```json
{
  "order_date": "2026-05-28",
  "store_name": "天津滨海新区-塘沽万达店",
  "store_phone": "13389973152",
  "store_address": "天津市...",
  "warehouse": "",
  "items": [
    {
      "product_name": "潮迹潮汕牛肉丸",
      "product_spec": "500g*20",
      "unit": "箱",
      "quantity": 2,
      "remark": ""
    }
  ],
  "raw_order_no": "",
  "extra_notes": ""
}
```

### 3. field_transformer.py — 字段校正

```python
"""
功能：用规则库校正LLM解析结果
输入：原始结构化JSON + 客户标识
处理：
  1. 识别客户（通过订单中的客户名称或手动指定）
  2. 加载对应 rules/{客户}.yaml
  3. 遍历原始字段 → field_aliases 映射 → 填充统一JSON
  4. 校验必填项
  5. 值格式校正（数值转换、单位标准化）
输出：统一结构化JSON（符合unified_order.json schema）

异常：
  - 必填字段缺失 → 返回校验失败，提示人工补充
"""
```

### 4. store_matcher.py — 门店匹配

```python
"""
功能：将统一JSON中的门店名匹配到数据库中的门店
输入：store_name (str)
处理：
  1. 精确匹配 store_list.store_name
  2. 模糊匹配（LIKE、包含关系、同义词）
  3. 如匹配到多个 → 返回候选列表
  4. 如未匹配到 → 返回空，提示人工
输出：
{
    "matched": True/False,
    "candidates": [
        {
            "store_code": "KH2025072100075",
            "store_name": "创宇-天津滨海新区-塘沽万达店",
            "owner_code": "HZ2024061300001",
            "owner_name": "盐城市创宇食品有限公司",
            "warehouse": "天津仓",
            "contact": "孙冬冬",
            "phone": "13389973152",
            "address": "天津市..."
        }
    ]
}
"""
```

### 5. sku_mapper.py — SKU映射

```python
"""
功能：根据货主ID和商品名匹配SKU，并判断单位类型
输入：
  - owner_code: 货主ID
  - product_name: 商品名称（从统一JSON获取）
  - unit: 原始单位（从统一JSON获取，如"箱"）

处理：
  1. 按 shipper_id = owner_code 过滤 shipper_sku_mapping
  2. 模糊匹配 customer_sku_name
  3. 读取匹配结果的 unit_conversion_rule
  4. 判断单位类型：
     - 匹配到的大单位（ratio>1）→ "大单位"
     - 匹配到的小单位（ratio=1）→ "小单位"
  5. 计算置信度

输出：
{
    "matched": True/False,
    "confidence": 0.95,
    "sku_code": "SK241228000106",
    "sku_name": "潮迹潮汕牛肉丸",
    "unit_type": "大单位",
    "unit_conversion": {"unit": "件", "ratio": 20, "package_spec": "500g*20包/件"}
}

置信度规则：
  - 精确匹配名称 → 0.95
  - 包含匹配（子串） → 0.80-0.90
  - 模糊匹配（分词匹配） → 0.60-0.80
  - 未匹配 → 0.00
  - <0.80 需标记为告警，人工确认
"""
```

### 6. template_generator.py — 模板生成

```python
"""
功能：生成华鼎31字段出库单模板
输入：
  - store_info: 门店信息（含仓库编码、收货人信息）
  - items: SKU映射结果列表
  - order_info: 订单信息（统一JSON）
  - defaults: 默认值配置

华鼎31字段（固定，不做规则配置）：
  序号, 门店编号, 门店三方编码, 仓库编码, 加急程度(0普通/1加急),
  商品SKU编号, 商品三方SPEC编号, 单位类型, 出库数量, 指定库存状态,
  出库类型, 配送方式, 指定车型（专配）, 是否垫付, 付款方式,
  快递公司, 单价, 总金额, 是否制定批次, 批次号, 生产日期,
  备注, 生产厂家编号, 门店收货地址编码, 三方单号, 业务模式,
  业务类型, 收货人, 联系电话, 收货地址, C端快递公司

默认值配置（template_defaults.yaml）：
  - 出库类型: 201（销售出库）
  - 配送方式: 共配
  - 指定库存状态: 正常
  - 是否垫付: 否
  - 加急程度: 0

输出：.xlsx 文件路径
"""
```

### 7. db/ — 数据库层

```python
# connection.py
def get_connection() -> psycopg2.connection:
    """从config/db_config.yaml读取连接信息，返回数据库连接"""
    
# store_repo.py
def find_store(name: str) -> list[dict]: ...
def get_by_code(code: str) -> dict: ...
def get_by_owner(owner_code: str) -> list[dict]: ...

# sku_repo.py
def find_by_shipper(shipper_id: str, keyword: str) -> list[dict]: ...
def get_all_by_shipper(shipper_id: str) -> list[dict]: ...

# customer_repo.py
def get_by_id(customer_id: str) -> dict: ...
def search_by_name(name: str) -> list[dict]: ...
```

---

## 五、SKILL.md 文档大纲

```markdown
# skill_order_to_huading_template

## 概述
将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎31字段出库单模板。

## 流程

### 步骤1：解析订单
- 工具：`order_parser`
- 输入：客户订单文件或文本
- 处理：调用LLM解析内容
- 输出：原始结构化JSON

### 步骤2：字段校正
- 工具：`field_transformer`
- 输入：原始结构化JSON
- 处理：加载客户对应的字段映射规则 → 校正字段名 → 校验必填项
- 输出：统一结构化JSON
- 规则文件位置：`field_mapping/rules/{客户名}.yaml`

### 步骤3：门店匹配
- 工具：`store_matcher`
- 输入：统一JSON中的门店名
- 处理：数据库模糊匹配，获取门店信息和货主ID
- 输出：门店信息 + 货主

### 步骤4：货主确认（人工必停！）
- 展示匹配到的货主信息
- **必须等待用户确认后才能继续**
- 支持：正确 / 切换货主

### 步骤5：SKU映射
- 工具：`sku_mapper`
- 输入：货主ID + 商品名 + 原始单位
- 处理：按货主过滤SKU → 模糊匹配 → 判断单位类型（大单位/小单位）
- 输出：SKU映射结果 + 置信度
- 告警：置信度 < 80% 需人工确认

### 步骤6：生成模板
- 工具：`template_generator`
- 输入：门店信息 + SKU映射 + 订单信息
- 处理：按华鼎31字段固定模板填充
- 输出：.xlsx 文件

### 步骤7：人工检查
- 展示映射对照表（客户订单 ↔ 华鼎订单）
- 高亮告警项（置信度低、未匹配、必填为空）
- 支持：修改 → 重新生成 / 确认通过

## 注意事项
- 货主必须确认，不得默认
- 单位类型在SKU映射后确定，不在解析阶段预判
- 规则库只校正字段名和值格式，不做衍生计算
- 新客户对接 → 只需在 field_mapping/rules/ 下添加规则文件

## 工具调用示例
```python
from tools.order_parser import parse
from tools.field_transformer import transform
from tools.store_matcher import match_store
from tools.sku_mapper import map_sku
from tools.template_generator import generate
```

## 数据库依赖
| 表名 | 用途 | 查询方式 |
|------|------|---------|
| store_list | 门店匹配 | store_repo.find_store() |
| shipper_sku_mapping | SKU映射 | sku_repo.find_by_shipper() |
| customer | 货主信息 | customer_repo.get_by_id() |
| warehouse_code_mapping | 仓库编码 | 直接查询 |

## 字段映射规则文件格式
参见 field_mapping/rules/ 目录下的 YAML 文件。

规则结构：
- customer_name: 客户名称
- description: 规则描述
- field_aliases: LLM输出字段名 → 统一字段名的映射
- validation: 校验规则（必填、类型、范围）
- correction: 值标准化规则
```

---

## 六、默认值配置

```yaml
# config/template_defaults.yaml
huading_template:
  defaults:
    出库类型: "201"              # 销售出库
    配送方式: "共配"
    指定库存状态: "正常"
    是否垫付: "否"
    加急程度: 0                  # 0=普通
    业务类型: ""
    业务模式: ""
    门店三方编码: ""
    商品三方SPEC编号: ""
    指定车型（专配）: ""
    付款方式: ""
    快递公司: ""
    单价: ""
    总金额: ""
    是否制定批次: "否"
    批次号: ""
    生产日期: ""
    生产厂家编号: ""
    门店收货地址编码: ""
    C端快递公司: ""
```

---

## 七、迭代路线

| 阶段 | 内容 | 目标 |
|:---:|:-----|:-----|
| **Phase 1** | 拆分目录结构，把现有代码分到各tool中 | 功能不变，结构清晰 |
| **Phase 2** | 抽象数据库层，各repo独立 | 数据库独立可维护 |
| **Phase 3** | 搭建field_mapping规则库 + transformer | 字段校正从代码迁移到规则 |
| **Phase 4** | 提炼SKILL.md，去掉代码，纯文档 | SKILL.md干净 |
| **Phase 5** | 新客户对接→只写规则文件，不改代码 | 零代码接入新客户 |
