# TOOLS.md - 工具配置

本系统共包含 **43个** MCP 工具函数，全部通过 MCP Server 连接数据库获取真实数据。

> **重要**: 所有工具函数通过 MCP 协议直接调用，数据来源为 Neon PostgreSQL 数据库，无需本地文件。

---

## 数据源说明

- **数据库**: Neon PostgreSQL (ep-summer-lab-aoi59gs9.c-2.ap-southeast-1.aws.neon.tech)
- **连接方式**: MCP Server (supply-chain-tools)
- **数据表**: sales_history, bom, inventory, capacity, suppliers 等

---

## 1. 数据读取类 (5个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 1 | `read_sales_data` | 从数据库读取历史销售数据 |
| 2 | `read_capacity` | 从数据库读取产线产能数据 |
| 3 | `read_bom` | 从数据库读取物料清单(BOM) |
| 4 | `read_inventory` | 从数据库读取当前库存数据 |
| 5 | `read_suppliers` | 从数据库读取供应商信息 |

---

## 2. 计算分析类 (4个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 6 | `generate_forecast` | 生成需求预测 |
| 7 | `run_mrp` | 运行物料需求计划(MRP) |
| 8 | `calculate_safety_stock` | 计算安全库存、订货点、EOQ |
| 9 | `optimize_schedule` | 优化排产计划 |

### run_mrp 参数格式
```json
{
  "production_orders": "[\"{\\\"order_id\\\":\\\"ORD-001\\\",\\\"sku\\\":\\\"PROD-A001\\\",\\\"quantity\\\":1000,\\\"due_date\\\":\\\"2026-06-30\\\",\\\"priority\\\":\\\"P1\\\"}\"]",
  "bom_data": "[{\\\"parent_sku\\\":\\\"PROD-A001\\\",\\\"component_sku\\\":\\\"WIP-B011\\\",\\\"quantity_per\\\":3.35,\\\"scrap_rate\\\":0.015,\\\"min_batch\\\":100,\\\"level\\\":1}]",
  "inventory_data": "[{\\\"sku\\\":\\\"WIP-B011\\\",\\\"location\\\":\\\"WH-CENTRAL-01\\\",\\\"on_hand\\\":8157,\\\"in_transit\\\":0,\\\"allocated\\\":0,\\\"safety_stock\\\":1000}]",
  "lead_times": "{\\\"WIP-B011\\\":5}"
}
```

### optimize_schedule 参数格式
```json
{
  "factory_code": "F-01",
  "time_range": "2026-06-01~2026-06-30",
  "production_orders": "[{\\\"order_id\\\":\\\"ORD-001\\\",\\\"sku\\\":\\\"PROD-A001\\\",\\\"quantity\\\":1000,\\\"due_date\\\":\\\"2026-06-30\\\",\\\"priority\\\":\\\"P1\\\"}]",
  "capacity_data": "[{\\\"line_code\\\":\\\"LINE-3\\\",\\\"factory_code\\\":\\\"F-01\\\",\\\"workshop_code\\\":\\\"WS-02\\\",\\\"available_slots\\\":[{\\\"start\\\":\\\"2026-06-01 08:00\\\",\\\"end\\\":\\\"2026-06-30 18:00\\\",\\\"available_hours\\\":160}],\\\"supported_products\\\":[\\\"PROD-A001\\\"],\\\"uph\\\":41,\\\"daily_hours\\\":16}]",
  "optimization_goals": "[\\\"on_time_delivery\\\"]"
}
```

### generate_report 可用模板ID
- `monthly_plan_report` - 月度供应链计划报告
- `snop_report` - S&OP产销协同报告
- `analysis_report` - 分析报告
- `exception_report` - 异常预警报告
- `query_report` - 查询结果报告

---

## 3. 约束管理类 (3个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 10 | `check_constraints` | 检查产能/品种约束 |
| 11 | `validate_variety_strategy` | 验证品种策略 |
| 12 | `check_material_availability` | 检查物料齐套/缺料 |

### validate_variety_strategy 参数格式
```json
{
  "strategy_name": "balanced",
  "process": "热轧",
  "actual_ratios": "{\"HRB400\":0.32,\"HRB500\":0.24,\"Q235B\":0.26,\"Q345B\":0.18}"
}
```

**有效策略名称 (strategy_name)**:
- `balanced` - 平衡型策略
- `high_strength` - 高强度策略
- `cost_effective` - 成本优先策略

**有效工艺类型 (process)**:
- `热轧`
- `冷轧`

**品种配置参考**:
| 策略 | 工艺 | 品种配置 |
|------|------|----------|
| balanced | 热轧 | HRB400:30%, HRB500:25%, Q235B:25%, Q345B:20% |
| balanced | 冷轧 | DC01:35%, DC03:30%, DC04:20%, SPCC:15% |
| high_strength | 热轧 | HRB500:40%, HRB600:30%, HRB400:20%, Q345B:10% |
| high_strength | 冷轧 | DC04:40%, DC03:30%, DC06:20%, DC01:10% |
| cost_effective | 热轧 | Q235B:40%, Q345B:30%, HRB400:20%, HRB500:10% |
| cost_effective | 冷轧 | SPCC:40%, DC01:30%, DC03:20%, DC04:10% |

---

## 4. 替代管理类 (2个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 13 | `find_substitute_bom` | 查找替代BOM方案 |
| 14 | `find_substitute_material` | 查找替代物料 |

---

## 5. 异常监控类 (3个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 15 | `scan_all_plans` | 扫描计划健康状态 |
| 16 | `check_thresholds` | 检查阈值告警 |
| 17 | `generate_action_plan` | 生成应急方案 |

### generate_action_plan 参数格式 (alert JSON)
```json
{
  "alert": "{\"alert_id\":\"ALT-001\",\"level\":\"critical\",\"dimension\":\"capacity_utilization\",\"dimension_display_name\":\"产能利用率\",\"current_value\":97.5,\"unit\":\"%\",\"threshold_range\":\"正常: 70-90%\",\"deviation_description\":\"超出严重阈值\",\"entity_code\":\"F001\",\"entity_name\":\"华东一厂\",\"plan_type\":\"production\",\"alert_time\":\"2025-04-20T10:00:00Z\",\"details\":\"华东一厂产能利用率97.5%\"}"
}
```

**Alert 关键字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| alert_id | string | 告警唯一标识 |
| level | string | 告警级别: `normal`, `warning`, `critical` |
| dimension | string | 监控维度 |
| dimension_display_name | string | 维度显示名称 |
| current_value | number | 当前指标值 |
| unit | string | 单位 |
| entity_code | string | 实体编码 |
| entity_name | string | 实体名称 |
| plan_type | string | 计划类型: `production`, `inventory`, `procurement` |

**dimension 可选值**:
- `delivery_rate` - 交期满足率
- `capacity_utilization` - 产能利用率
- `inventory_coverage` - 库存覆盖率
- `supplier_on_time` - 供应商准时率

### check_thresholds 参数格式
```json
{
  "plan_data": "{\"scan_results\":[{\"plan_type\":\"production\",\"plan_name\":\"生产计划\",\"metrics\":[{\"dimension\":\"capacity_utilization\",\"name\":\"F001产能利用率\",\"value\":97.5,\"unit\":\"%\",\"plan_type\":\"production\",\"entity_code\":\"F001\",\"entity_name\":\"华东一厂\",\"period\":\"2025-04\"}]}],\"scan_date\":\"2025-04-20\",\"scan_duration_ms\":125}"
}
```

**注意**: 当 `scan_results` 为空数组时，返回空告警列表（正常行为）。

---

## 6. 通信协调类 (4个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 18 | `read_blackboard` | 读取共享黑板数据 |
| 19 | `write_blackboard` | 写入共享黑板 |
| 20 | `dispatch_task` | 分发任务到子Agent |
| 21 | `resolve_conflict` | 解决资源冲突 |

---

## 7. 数据校验类 (3个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 22 | `validate_data` | 校验数据完整性 |
| 23 | `import_data` | 导入数据到数据库 |
| 24 | `prepare_algorithm_input` | 准备算法输入 |

### validate_data 参数格式
```json
{
  "data": "[{\"sku\":\"A001\",\"qty\":100,\"price\":25.5}]",
  "rules": "[{\"field\":\"sku\",\"type\":\"string\",\"required\":true},{\"field\":\"qty\",\"type\":\"number\",\"required\":true},{\"field\":\"price\",\"type\":\"number\",\"required\":false}]"
}
```

**ValidationRule type 字段可选值**:
- `string` - 字符串类型
- `number` - 数值类型
- `boolean` - 布尔类型
- `date` - 日期类型
- `array` - 数组类型
- `object` - 对象类型

**支持的其他规则字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| required | boolean | 是否必填 |
| min | number | 最小值（数值类型） |
| max | number | 最大值（数值类型） |
| minLength | number | 最小长度（字符串类型） |
| maxLength | number | 最大长度（字符串类型） |
| pattern | string | 正则表达式（字符串类型） |
| enum | string[] | 枚举值列表 |

---

## 8. 意图理解类 (1个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 25 | `parse_intent` | 解析用户意图 |

---

## 9. 上下文与报告类 (2个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 26 | `manage_context` | 管理会话上下文 |
| 27 | `generate_report` | 生成结构化报告 |

---

## 10. 数据接入与信号处理类 (5个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 28 | `fetch_external_data` | 获取外部数据（天气/新闻/金融） |
| 29 | `extract_signals` | 从文本提取供应链信号 |
| 30 | `batch_parse` | 批量解析文本 |
| 31 | `fuse_signals` | 融合多源信号 |
| 32 | `search_knowledge_base` | 搜索知识库 |

---

## 11. 执行与反馈类 (8个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 33 | `submit_action_plan` | 提交行动方案 |
| 34 | `approve_action` | 审批行动 |
| 35 | `execute_action` | 执行行动方案 |
| 36 | `track_execution` | 跟踪执行结果 |
| 37 | `rollback_action` | 回滚行动方案 |
| 38 | `collect_feedback` | 收集执行反馈 |
| 39 | `analyze_deviations` | 分析偏差数据 |
| 40 | `auto_tune_model` | 自动调优模型 |

---

## 12. 巡检管理类 (3个)

| # | 工具名称 | 说明 |
|---|----------|------|
| 41 | `manage_monitors` | 管理定时巡检任务 |
| 42 | `manage_event_triggers` | 管理事件触发器 |
| 43 | `emit_event` | 发射系统事件 |

---

## 钉钉 CLI (DingTalk Workspace CLI)

**工具路径:** `/opt/homebrew/bin/dws`
**认证状态:** 已登录（全局有效，Token 有效期至当天17:35）

### 常用命令

```bash
# 文档操作
dws doc list                    # 列出文档
dws doc search <关键词>         # 搜索文档
dws doc create --title <标题>   # 创建文档
dws doc read <文档ID>           # 读取文档内容
dws doc update <文档ID>         # 更新文档
dws doc folder                  # 文件夹管理

# 其他产品域
dws aitable                     # AI表格
dws calendar                    # 日历日程
dws chat                        # 群聊消息
dws wiki                        # 知识库
dws mail                        # 邮箱
```

### 输出格式
```bash
dws doc list -f json            # JSON输出（默认）
dws doc list -f table           # 表格输出
dws doc list -f pretty          # 美化输出
dws doc list --dry-run          # 预览模式（不执行）
```

### 认证信息
- Corp ID: `ding5392f470b795a632f5bf40eda33b7ba0`
- Token 自动刷新，无需手动操作
