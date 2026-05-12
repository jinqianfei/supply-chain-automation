# skill-order-to-huading-template

## Overview

**Skill Name**: 订单转华鼎出库单模板

**Description**: 将客户订单Excel转换为华鼎出库单模板（31字段）的完整流程。包括订单解析、门店匹配、SKU匹配、单位类型判断、字段映射等。

**Version**: 1.1

**Author**: AI客服

**Created**: 2026-05-12

**Updated**: 2026-05-12

---

## 1. 功能说明

将客户上传的订单Excel文件，经过订单映射流程，生成华鼎系统可导入的出库单模板（xlsx格式，31字段）。

### 输入
- 客户订单Excel文件路径
- 货主ID（shipper_id）

### 输出
- 华鼎出库单模板Excel文件路径

---

## 2. ⚙️ 用户需提前配置的数据（初始化参数）

使用此Skill前，用户需要配置以下数据：

### 2.1 必填配置

| 配置项 | 说明 | 示例 |
|--------|------|------|
| **货主ID (shipper_id)** | 标识客户的唯一ID，用于查询该货主的门店和SKU数据 | `HZ2023061500002` |
| **数据库连接** | PostgreSQL连接信息 | host: localhost, port: 5432, database: ai_cs_support, user: xxx |

### 2.2 可选配置（有默认值）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| **仓库编码映射** | 廊坊仓→5, 天津仓→8 | 如果仓库名称不同，需自定义映射 |
| **默认仓库编码** | 5 | 门店匹配失败时使用的默认仓库 |
| **输出目录** | `/output` | 生成的模板文件存放目录 |

### 2.3 数据依赖（需提前导入系统）

| 数据 | 说明 |
|------|------|
| **store_list** | 门店列表表，包含 store_code, store_name, warehouse, address, contact_person, phone |
| **shipper_sku_mapping** | SKU映射表，包含 customer_sku_name, system_sku_code, unit_conversion_rule |

---

## 3. 处理流程

```
Step 1: 订单解析
  ├── 读取客户订单Excel
  ├── 解析抬头信息（订单号、门店名、收货人等）
  └── 解析商品明细（商品名称、数量、单位、备注等）

Step 2: 门店匹配
  ├── 根据门店名查询store_list表
  └── 获取门店编号、仓库、收货人、联系电话、收货地址

Step 3: SKU匹配
  ├── 根据商品名称查询shipper_sku_mapping表
  ├── 获取系统SKU编号
  └── 判断单位类型（大/中/小单位）

Step 4: 生成华鼎模板
  ├── 按31字段模板填充数据
  └── 输出Excel文件
```

---

## 4. 字段映射规则

### ❌ 无默认值字段（必须通过匹配/提取获取）

| 字段 | 数据来源 | 说明 |
|------|----------|------|
| 门店编号 | match_store | 从门店数据获取 |
| 仓库编码 | match_store | 从门店的warehouse字段映射 |
| 商品SKU编号 | match_sku | 必须通过SKU匹配获取 |
| 单位类型 | match_sku | 根据ratio判断（最大=大单位） |
| 备注 | 订单提取 | 从客户订单的"备注"字段提取（不是规格字段） |
| 三方单号 | 订单提取 | 从订单编号字段获取 |
| 收货人 | match_store | 从门店数据获取 |
| 联系电话 | match_store | 从门店数据获取 |
| 收货地址 | match_store | 从门店数据获取 |
| 付款方式 | - | 空（无默认值） |

### ✅ 有默认值字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| 序号 | 1 | 同单一组商品序号相同 |
| 加急程度 | 0 | 0=普通，1=加急 |
| 指定库存状态 | "正常" | 必填 |
| 出库类型 | 201 | 201=销售订单 |
| 配送方式 | "共配" | 必填 |
| 是否垫付 | "否" | 必填 |
| 是否制定批次 | "否" | 0=否，1=是 |

### ❌ 固定为空字段

| 字段 |
|------|
| 门店三方编码、商品三方SPEC编号、指定车型、快递公司、单价、总金额、批次号、生产日期、生产厂家编号、门店收货地址编码、业务模式、业务类型、C端快递公司 |

---

## 5. 单位类型判断规则

```python
# SKU配置中有多个单位时，按ratio判断：
# ratio最大的 → 大单位
# ratio中等的 → 中单位
# ratio最小的 → 小单位
```

---

## 6. 仓库编码映射

| 仓库名称 | 仓库编码 |
|----------|----------|
| 廊坊仓 | 5 |
| 天津仓 | 8 |

---

## 7. 调用示例

### 7.1 完整初始化配置

```python
from skills.skill_order_to_huading_template import OrderToHuadingTemplate

# 方式1: 初始化时配置
skill = OrderToHuadingTemplate(
    db_config={
        "host": "localhost",
        "port": 5432,
        "database": "ai_cs_support",
        "user": "your_username",
        "password": "your_password"  # 可选
    },
    shipper_id="HZ2023061500002",  # 必填
    warehouse_map={"廊坊仓": 5, "天津仓": 8},  # 可选，有默认值
    default_warehouse_code=5  # 可选，有默认值
)

# 执行转换
result = skill.execute(
    order_file="/path/to/customer_order.xlsx",
    output_file="/path/to/output/huading_template.xlsx"  # 可选
)
```

### 7.2 快速调用（使用默认配置）

```python
from skills.skill_order_to_huading_template import convert_order_to_huading

# 需要先确保默认配置正确
result = convert_order_to_huading(
    order_file="/path/to/customer_order.xlsx",
    shipper_id="HZ2023061500002"  # 必填
)
```

### 7.3 返回结果

```python
{
    "success": True,
    "output_file": "/path/to/output/huading_template.xlsx",
    "order_no": "DH-O-20260423-294092",
    "store_code": "KH2024070300038",
    "item_count": 7,
    "message": "模板生成成功"
}
```

---

## 8. 错误处理

| 错误情况 | 处理方式 |
|----------|----------|
| 订单文件不存在 | 返回错误：文件不存在 |
| 门店匹配失败 | 使用订单中的门店信息，仓库编码默认5 |
| SKU匹配失败 | SKU编号为空，备注为空 |
| 备注字段为空 | 留空（不是用商品名称填充） |

---

## 9. 数据库依赖

- **表**: store_list, shipper_sku_mapping
- **连接**: PostgreSQL ai_cs_support

---

## 10. 使用场景

当客户上传订单Excel文件时，调用此skill生成华鼎出库单模板。

---

## 11. 配置检查清单

使用前请确认以下配置已就绪：

- [ ] **货主ID (shipper_id)** - 必填，从系统管理员获取
- [ ] **数据库连接** - 必填，确认host/port/database/user正确
- [ ] **store_list表** - 必填，该货主的门店数据已导入
- [ ] **shipper_sku_mapping表** - 必填，该货主的SKU映射已导入
- [ ] **仓库编码映射** - 可选，如有自定义仓库名称需配置