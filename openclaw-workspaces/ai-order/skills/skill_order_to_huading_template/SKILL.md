---
name: skill-order-to-huading-template
description: 将客户订单转换为华鼎出库单模板（31字段），支持Excel/图片/PDF/文字多种输入格式。当用户说"处理订单"、"生成模板"、"订单转华鼎"时触发。
metadata:
  openclaw:
    triggers:
      - 处理订单
      - 生成模板
      - 订单转华鼎
      - 导出模板
      - 生成华鼎模板
      - 转换订单
      - 上传订单
      - 扫描订单
    requires:
      config:
        - db_config
---
# skill-order-to-huading-template

## Overview

**Skill Name**: 订单转华鼎出库单模板

**Description**: 将客户订单（Excel/图片/PDF/文字/Word）转换为华鼎31字段出库单模板的完整流程。

**Version**: 5.11.1 (2026-06-09 — 硬编码清理：消除所有 P0/P1 机器特定/环境依赖)


**架构**：工具层 + 数据库层 + 字段映射规则库 三层分离

---

## 1. 核心流程（完整思维链）

```
Step 1: tools_parse()
   输入: 客户订单文件/文本
   处理: LLM读取Excel内容 → 原始结构化JSON（多门店支持）
   输出: {success: True, stores: {多门店}, _parse_method: "llm"}

         ↓

Step 2: tools_transform()
   输入: 原始JSON
   处理: 规则库字段名标准化（LLM输出字段名 → 统一字段名）
   输出: {success: True, stores: {校正后}, items: [...], _multi_store: True}

         ↓

Step 3: _match_store()  ← ⚠️ 人工确认点（不再自动确认）
   输入: 门店名 + phone + address + contact_person
   处理: store_list 表多级模糊匹配（6层+2兜底）
   输出: need_store_confirm=True + matched_store + candidates（含相似度）

         ↓ 【用户确认门店匹配结果】

Step 4: _match_sku()  ← ⚠️ 人工确认点（SKU映射）
   输入: 商品列表 + owner_code（货主ID）
   处理: product_sku + product_name_alias，5层匹配
   输出: sku_results + unmatched_items（置信度<0.8告警）

         ↓ 【用户确认SKU映射结果】

Step 5: _generate_multi_store_template()
   输入: order_data + all_store_results
   处理: openpyxl 生成31字段Excel
   输出: ./output/华鼎出库单_*.xlsx

         ↓ 【用户检查Excel映射对照表】
```

---

## 2. 数据库设计（2026-06-01 更新）

### 2.1 表结构

#### product_sku（合并商品表）⭐ 主表

| 字段                 | 类型         | 说明                                        |
| -------------------- | ------------ | ------------------------------------------- |
| `id`               | SERIAL       | 主键                                        |
| `sku_code`         | VARCHAR(50)  | **华鼎标准SKU编码**（唯一约束 part1） |
| `customer_code`    | VARCHAR(50)  | 货主自编码（可为空）                        |
| `sku_name`         | VARCHAR(200) | 商品名称                                    |
| `product_spec`     | VARCHAR(100) | 包装规格（如"16盒/箱"）                     |
| `unit`             | VARCHAR(20)  | 基本单位（件/箱/盒/个）                     |
| `unit_type`        | VARCHAR(20)  | **大单位** / **小单位**         |
| `conversion_ratio` | NUMERIC      | 换算比（大单位>1，小单位=1）                |
| `shipper_id`       | VARCHAR(50)  | **货主ID**（唯一约束 part2，必填）    |
| `category`         | VARCHAR(50)  | 品类/存储方式                               |
| `warehouse_code`   | VARCHAR(20)  | 默认仓库编码                                |
| `status`           | VARCHAR(20)  | 状态（默认 ACTIVE）                         |

**唯一约束**: `(sku_code, shipper_id)` — 同一SKU可被多个货主使用

**数据量**: 1832条（覆盖12个货主）

#### product_name_alias（商品名别名表）⭐ 2026-06-01新增

| 字段                    | 类型         | 说明                                                |
| ----------------------- | ------------ | --------------------------------------------------- |
| `id`                  | SERIAL       | 主键                                                |
| `order_product_name`  | VARCHAR(200) | 订单报货名（含数量单位，如"云端小王子（20个/件）"） |
| `system_product_name` | VARCHAR(200) | 系统标准商品名（如"蓝云朵"）                        |
| `shipper_id`          | VARCHAR(50)  | 货主ID                                              |
| `created_at`          | TIMESTAMP    | 创建时间                                            |

**唯一约束**: `(order_product_name, shipper_id)`

**数据量**: 30条（廖朵朵专用的报货名→系统名映射）

#### store_list（门店表）

| 字段               | 类型    | 说明             |
| ------------------ | ------- | ---------------- |
| `store_code`     | VARCHAR | 门店编码（主键） |
| `store_name`     | VARCHAR | 门店名称         |
| `owner_code`     | VARCHAR | 货主编码         |
| `contact_person` | VARCHAR | 联系人           |
| `phone`          | VARCHAR | 手机号           |
| `address`        | VARCHAR | 地址             |

#### warehouse_code_mapping（仓库编码表）

#### customer（货主信息表）

### 2.2 货主数据分布（product_sku）

| 货主ID          | 商品数 | 品牌     |
| --------------- | ------ | -------- |
| HZ2024061300001 | 640条  | 创宇     |
| HZ2023061500002 | 226条  | 制茶青年 |
| HZ2025122000013 | 214条  | -        |
| HZ2024091100001 | 146条  | 廖朵朵   |
| HZ2025032700001 | 127条  | -        |
| HZ2026000001    | 102条  | -        |
| HZ2023101200002 | 100条  | -        |
| HZ2024080200002 | 94条   | -        |
| HZ2023061500003 | 59条   | -        |
| HZ2026020300004 | 54条   | -        |
| HZ2025032400001 | 47条   | -        |
| HZ2026012600005 | 23条   | -        |

### 2.3 已删除的表

- ❌ `system_sku`（已合并到 product_sku）
- ❌ `shipper_sku_mapping`（已合并到 product_sku）

---

## 3. SKU 匹配逻辑（5层）⭐ 2026-06-01 更新

```
订单商品名称（完整报货名）
         ↓
┌───────────────────────────────────────────┐
│ Layer 0：别名表查表（最高优先级）            │
│ 查 product_name_alias                      │
│ WHERE order_product_name = 输入完整报货名  │
│ → 得到 system_product_name                 │
│ → JOIN product_sku 找对应 SKU              │
│ 置信度：0.98                               │
└───────────────────────────────────────────┘
         ↓ 未命中
┌───────────────────────────────────────────┐
│ Layer 1：精确匹配                          │
│ 查 product_sku（WHERE shipper_id）         │
│ sku_name = 输入                            │
│ OR customer_code = 输入                    │
│ 置信度：0.95                               │
└───────────────────────────────────────────┘
         ↓ 未命中
┌───────────────────────────────────────────┐
│ Layer 2：模糊匹配（LIKE %name%）            │
│ 相似度 ≥ 0.8 → 直接返回                   │
│ 候选 ≥ 2 且 相似度 ≥ 0.7 → 取最佳          │
│ 置信度：min(1.0, 相似度值)                │
└───────────────────────────────────────────┘
         ↓ 未命中
┌───────────────────────────────────────────┐
│ Layer 3：分词关键词匹配                    │
│ 提取前5/4/3/2字 + 后5/4/3/2字             │
│ LIKE %keyword% 查询                        │
│ 相似度 ≥ 0.7 → 返回最佳                    │
│ 置信度：min(0.85, score)                  │
└───────────────────────────────────────────┘
         ↓ 全未命中
      → unmatched_items
```

**关键阈值**：

- Layer 2 直接返回：相似度 ≥ 0.8
- Layer 2 候选取最佳：候选 ≥ 2 且 相似度 ≥ 0.7
- Layer 3 命中：相似度 ≥ 0.7（**防误匹配：防止"慕斯蛋糕白天鹅"→"财字慕斯蛋糕"**）

---

## 4. 门店匹配逻辑（6层 + 2兜底）

```
输入门店名称
         ↓
┌───────────────────────────────────────────┐
│ Layer 0：手机号精确匹配（最高优先级）       │
│ store_list.phone = 输入手机号              │
│ 命中 → 直接返回                            │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 1：客户公司匹配                      │
│ owner_name LIKE %company%                  │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 2：精确匹配                          │
│ store_name = 输入                          │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 3：包含匹配                          │
│ store_name ILIKE %input%                   │
│ OR input ILIKE %store_name%               │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 3.5：关键词交叉匹配                  │
│ 提取输入前3字+后3字，交叉验证              │
│ 触发：Layer3 相似度 < 0.75                │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 4：货主提示兜底                      │
│ 用 owner_code 限制候选范围                 │
└───────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────┐
│ Layer 3.6：contact_person 联系人兜底       │
│ contact_person = 输入（当输入是"梁女士"    │
│ /"陈冰"等个人名时触发）                    │
└───────────────────────────────────────────┘
         ↓ 全未命中
    → need_store_confirm = True（返回候选）
```

---

## 5. 各步骤详细说明

### Step 1：订单解析 → tools/order_parser.parse()

**职责**：将任意格式订单解析为原始结构化JSON

| 输入格式           | 处理方式                  | 返回标记                                         |
| ------------------ | ------------------------- | ------------------------------------------------ |
| Excel (.xlsx/.xls) | LLM直接读取内容，输出JSON | `_parse_method: "llm"`                         |
| 图片 (.jpg/.png)   | 返回 `need_ocr=True`    | 等待 Agent 调用 image 工具                       |
| PDF (.pdf)         | 返回 `need_pdf=True`    | 等待 Agent 调用 pdf 工具                         |
| Word (.docx)       | python-docx 原生提取      | `need_docx=None`                               |
| 文字粘贴           | LLM解析优先，fallback正则 | `_parse_method: "llm"` 或 `"regex_fallback"` |

**输出示例**（多门店）：

```json
{
  "success": true,
  "_parse_method": "llm",
  "confidence": 0.95,
  "stores": {
    "沛县廖朵朵": {
      "store_name": "沛县廖朵朵",
      "contact_person": "沛县廖朵朵",
      "phone": "15052047353",
      "address": "江苏省徐州市沛县...",
      "items": [
        {"seq": 1, "product_name": "云端小王子", "spec": "20个/件", "quantity": 1, "unit": "件"},
        {"seq": 2, "product_name": "慕斯蛋糕一见倾心", "spec": "20个/件", "quantity": 3, "unit": "件"}
      ]
    }
  }
}
```

---

### Step 2：字段标准化 → tools/field_transformer.transform()

**职责**：将 LLM 输出的字段名映射为统一字段名

**规则文件**：`field_mapping/rules/{客户名}.yaml`

- `field_aliases`：LLM输出字段名 → 统一字段名
- `validation`：必填项、类型校验
- `correction`：值标准化

**统一字段**：`store_name`, `phone`, `address`, `items[].product_name`, `quantity`, `unit`, `remark`

**多门店检测**：`_multi_store: True`（当 `len(unified_stores) > 1` 时设置）

---

### Step 3：门店匹配 → _match_store() 【人工确认点】

**职责**：在 store_list 表中匹配门店，获取货主ID、仓库编码

**输出**：

```json
{
  "need_store_confirm": true,
  "store_name_submitted": "沛县廖朵朵",
  "matched_store": {
    "store_code": "KH2024100600109",
    "store_name": "廖朵朵-徐州沛县",
    "owner_code": "HZ2024091100001",
    "owner_name": "郑州市必德供应链管理有限公司",
    "warehouse_name": "",
    "warehouse_code": "",
    "address": "沛县九龙城廖朵朵千层蛋糕店",
    "contact_person": "沛县廖朵朵",
    "phone": "15052047322",
    "similarity": 1.29,
    "match_type": "fuzzy_contains",
    "match_method": "包含匹配"
  },
  "candidates": [...],
  "message": "门店「沛县廖朵朵」→ 廖朵朵-徐州沛县（相似度129%），请确认"
}
```

**⚠️ 关键规则**：

- ❌ 不再自动确认（75%/90% 阈值已移除）
- ✅ 所有匹配结果都必须用户确认

---

### Step 4：SKU映射 → _match_sku() 【人工确认点】

**职责**：在 product_sku 表中按货主ID过滤，匹配SKU

**数据源**：product_sku（1832条）+ product_name_alias（30条别名）

**⚠️ 重要原则**：向用户确认SKU映射时，必须展示完整数据

- 已匹配商品：全部展示（不能只展示部分）
- 未匹配商品：全部展示（不能省略）
- 让用户一次性看完所有映射结果再做确认

**确认展示格式（映射对照表9列）**：

| 字段         | 说明                       |
| ------------ | -------------------------- |
| 订单商品名称 | 订单原始商品名称           |
| 订单商品规格 | 订单原始规格               |
| 订单数量     | 订单原始数量               |
| 订单单位     | 订单原始单位               |
| 匹配SKU编码  | 数据库匹配到的SKU编码      |
| SKU名称      | 数据库SKU名称              |
| 数量         | 出库数量（与订单数量一致） |
| 单位类型     | 大单位/小单位              |
| 匹配单位     | 对应出库单位（箱/件等）    |

**输出**：

```json
{
  "sku_results": [
    {
      "seq": 1,
      "product_name": "云端小王子（20个/件）",
      "spec": "20个/件",
      "quantity": 1,
      "sku_code": "SK251118000084",
      "sku_name": "蓝云朵",
      "unit": "盒",
      "unit_type": "小单位",
      "product_spec": "20个/箱",
      "match_method": "Layer 0别名匹配(conf=0.98)"
    }
  ],
  "unmatched_items": [
    {
      "seq": 5,
      "product_name": "未知商品",
      "spec": "",
      "quantity": 1,
      "unit": "件"
    }
  ]
}
```

---

### Step 5：生成Excel模板 → _generate_multi_store_template()

**31字段**：序号、门店编号、门店三方编码、仓库编码、加急程度、商品SKU编号、商品三方SPEC编号、单位类型、出库数量、指定库存状态、出库类型、配送方式、指定车型（专配）、是否垫付、付款方式、快递公司、单价、总金额、是否制定批次、批次号、生产日期、备注、生产厂家编号、门店收货地址编码、三方单号、业务模式、业务类型、收货人、联系电话、收货地址、C端快递公司

**多门店格式**：

- ❌ 无门店名称分隔行
- ✅ 序号 = 门店序号（同一门店的商品序号相同，从1开始）
- ✅ 门店编号列区分不同门店

---

## 6. 完整工具链图

```
客户Excel/图片/PDF/Word/文字
    │
    ▼
┌─────────────────────────────────────┐
│  Step 1: tools/order_parser.parse() │
│  LLM读取内容 → 原始JSON            │
│  _parse_method: "llm"              │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 2: tools/field_transformer.  │
│  transform()                       │
│  规则库标准化 → 统一JSON           │
│  返回: _multi_store + stores       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 3: _match_store()            │
│  store_list → 门店→货主→仓库        │
│  ⚠️ need_store_confirm=True        │
└─────────────────────────────────────┘
    │  owner_code
    ▼
┌─────────────────────────────────────┐
│  Step 4: _match_sku()             │
│  product_sku + product_name_alias   │
│  5层匹配 → sku_results             │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 5: _generate_multi_store_    │
│  template()                        │
│  openpyxl → 31字段Excel            │
└─────────────────────────────────────┘
    │
    ▼
  华鼎出库单_*.xlsx
```

---

## 7. 数据库配置

通过环境变量配置（推荐）：

```bash
# .env 文件（**不要**提交到 git）
DB_HOST=your-db-host.amazonaws.com
DB_PORT=5432
DB_NAME=neo
DB_USER=your_user
DB_PASSWORD=your_password
DB_SSLMODE=prefer
```

或者代码里传 `db_config`：

```python
import os
db_config = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}
```

### 货主-品牌对照

| 货主公司全称                 | 品牌     | 货主ID          |
| ---------------------------- | -------- | --------------- |
| 河南上黎供应链管理有限公司   | 制茶青年 | HZ2023061500002 |
| 郑州市必德供应链管理有限公司 | 廖朵朵   | HZ2024091100001 |

---

## 8. 调用示例

```python
from skills.skill_order_to_huading_template import OrderToHuadingTemplate

# 推荐：使用环境变量
import os
db_config = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

skill = OrderToHuadingTemplate(db_config=db_config)

# Excel订单
result = skill.execute(
    order_input="/path/order.xlsx",
    order_type="excel"
)

# 图片订单（两步）
result = skill.execute(order_input="/path/order.jpg", order_type="image")
if result.get("need_ocr"):
    ocr_result = image_tool.analyze(...)
    result = skill.execute(order_input="/path/order.jpg", order_type="image", ocr_result=ocr_result)

# 确认门店后继续
if result.get("need_store_confirm"):
    result = skill.execute(
        order_input=order_input,
        order_type=order_type,
        confirmed_store=result["matched_store"]
    )
```

---

## 9. 返回结果说明

| 字段                   | 说明                     |
| ---------------------- | ------------------------ |
| `success`            | 是否成功处理             |
| `need_store_confirm` | 是否需要确认门店匹配     |
| `need_sku_confirm`   | 是否需要确认SKU映射      |
| `store_count`        | 门店数量                 |
| `item_count`         | 商品总数量               |
| `matched_store`      | 门店匹配结果（含相似度） |
| `candidates`         | 候选门店列表             |
| `sku_results`        | SKU映射结果              |
| `unmatched_items`    | 未匹配商品列表           |
| `output_file`        | 生成的Excel文件路径      |
| `all_store_results`  | 多门店完整结果           |

---

## 10. 安全守则

1. **Skill安装审核** - 安装任何 Skill 前，必须使用 clawhub-skill-vetting 进行安全审核
2. **不读取密码** - 不读取电脑上的任何密码/密钥信息
3. **不发布到网络** - 不将任何密钥或密码信息发送到网络
4. **货主必须确认** - 不默认货主，匹配后必须用户确认才能继续
5. **门店必须确认** - 不自动确认门店匹配（75%/90%阈值已移除）

---

## 11. 配置检查清单

- [X] **数据库连接** — 必填（db_config），使用环境变量 `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`
- [X] **product_sku 表** — SKU主表（当前1832条）
- [X] **product_name_alias 表** — 别名映射表（当前30条）
- [X] **store_list 表** — 门店数据（当前~714条）
- [X] **warehouse_code_mapping 表** — 仓库编码
- [X] **customer 表** — 货主信息
- [X] **field_mapping/rules/ 规则文件** — 客户字段映射

---

## ⚠️ AI调用规范（防止跳过主入口）

### 问题描述

AI 在处理订单时，可能直接调用底层工具函数（如 `tools_parse()`、`tools_transform()`、`_match_store()`、`_match_sku()` 等），而跳过了 Skill 的主入口 `execute()`。这会导致：
- 绕过 Skill 的参数校验和初始化逻辑
- 绕过数据库连接管理和配置
- 绕过错误处理和状态管理
- 无法正确使用 db_config 配置

### 解决方案

**方案1：修改 Skill 结构（技术层面）**

在 `__init__.py` 中，对所有内部工具函数添加 `@tool_lock` 装饰器或 `__tools__` 元组声明，禁止 AI 直接调用：

```python
class OrderToHuadingTemplate:
    # 声明 AI 可调用的公开接口
    __公开接口__ = ['execute']
    
    # 内部工具函数（AI 不得直接调用）
    def _tools_parse(self, ...):  # ← AI 不应直接调用
    def _tools_transform(self, ...):  # ← AI 不应直接调用
    def _match_store(self, ...):  # ← AI 不应直接调用
    def _match_sku(self, ...):  # ← AI 不应直接调用
```

**方案2：检查 TOOLS.md 配置（流程层面）**

AI 在执行任何 Skill 操作前，必须先读取并检查 `TOOLS.md` 配置：
1. **读取** `TOOLS.md` 确认数据库连接配置
2. **确认** Skill 的正确使用方式（`execute()` 主入口）
3. **禁止** 跳过主入口直接调用内部函数

---

### 版本历史表（快速查阅）

| 版本 | 日期 | 变更 |
|------|------|------|
| 5.8 | 2026-06-01 | 数据库合并：product_sku（1832条）+ product_name_alias（30条）；SKU匹配5层逻辑（Layer 0别名表）；删除system_sku + shipper_sku_mapping |
| 5.3 | 2026-05-29 | 映射对照表9列字段规范化；移除门店标题分隔行；序号改为门店序号 |
| 5.2 | 2026-05-29 | 门店匹配强制用户确认（移除auto_confirm），多门店序号格式 |
| 5.1 | 2026-05-28 | Word原生解析支持，PDF/图片工具回调 |
| 5.0 | 2026-05-28 | 架构重构：tools/层分离，LLM解析 |

---

## 12. 完整版本历史

| 版本 | 日期       | 变更                                                                                                                                           |
| ---- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 5.0  | 2026-05-28 | 架构重构：tools/层分离，LLM解析                                                                                                                |
| 5.1  | 2026-05-28 | Word原生解析支持，PDF/图片工具回调                                                                                                             |
| 5.2  | 2026-05-29 | 门店匹配强制用户确认（移除auto_confirm），多门店序号格式                                                                                       |
| 5.3  | 2026-05-29 | 映射对照表9列字段规范化；移除门店标题分隔行；序号改为门店序号                                                                                  |
| 5.4  | 2026-06-01 | **数据库合并**：product_sku（1832条）+ product_name_alias（30条）；SKU匹配5层逻辑（Layer 0别名表）；删除system_sku + shipper_sku_mapping |

| 版本 | 日期       | 变更                                                                                                                                           |
| ---- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 5.0  | 2026-05-28 | 架构重构：tools/层分离，LLM解析                                                                                                                |
| 5.1  | 2026-05-28 | Word原生解析支持，PDF/图片工具回调                                                                                                             |
| 5.2  | 2026-05-29 | 门店匹配强制用户确认（移除auto_confirm），多门店序号格式                                                                                       |
| 5.3  | 2026-05-29 | 映射对照表9列字段规范化；移除门店标题分隔行；序号改为门店序号                                                                                  |
| 5.4  | 2026-06-01 | **数据库合并**：product_sku（1832条）+ product_name_alias（30条）；SKU匹配5层逻辑（Layer 0别名表）；删除system_sku + shipper_sku_mapping |
