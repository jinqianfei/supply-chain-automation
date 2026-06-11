# 订单映射可用性审核报告

审核日期：2026-06-11  
审核对象：`skill-order-to-huading-template` 工作区与技能说明  
结论级别：基本可用，但 SKU 审核信息透传存在高优先级缺口，建议修复后再作为稳定自动化链路使用。

## 1. 总体结论

当前 skill 已具备完整订单转换闭环：

1. 订单解析：支持 Excel、图片、PDF、Word、文本入口。
2. 字段标准化：通过 `tools/_field_transformer.py` 和 `field_mapping/rules/*.yaml` 统一门店、商品、数量、单位等字段。
3. 门店匹配：通过 `tools/_store_matcher.py` 按手机号、名称、地址、联系人、货主等多层策略匹配。
4. SKU 映射：通过 `tools/_sku_mapper.py` 按货主过滤 SKU，并引入别名、精确、模糊、相似度、关键词等多层匹配。
5. 人工确认：`execute()` 已设计门店确认和 SKU 确认两道关口。
6. 模板输出：可生成华鼎 31 字段 Excel。

从架构上看，这个 skill 的方向是对的：解析、字段规则、门店匹配、SKU 匹配、模板生成被拆开了，方便后续按客户/货主继续补规则。

但从“订单映射可用性”角度看，目前还不能认为完全稳态可用。最主要问题是：底层 SKU 匹配已经产出低置信、多候选、候选列表等审核信息，但主入口 `_match_sku()` 格式化返回时没有完整透传，导致 `review_data` 可能把需要人工确认的 SKU 显示成普通成功匹配。

## 2. 高优先级问题

### P0：SKU 匹配的审核信号在主入口丢失

位置：`__init__.py` 第 2987-2999 行。

`tools/_sku_mapper.py` 的 `map_sku_batch()` 会返回：

- `confidence`
- `need_confirm`
- `candidates`
- `original_product_name`
- `order_unit`
- `unit_original`
- `customer_code`

但 `OrderToHuadingTemplate._match_sku()` 只保留了：

- `seq`
- `product_name`
- `spec`
- `quantity`
- `remark`
- `sku_code`
- `sku_name`
- `unit`
- `unit_type`
- `product_spec`
- `match_method`

影响：

- 低置信度 SKU 在 `_generate_mapping_comparison_multi()` 中会默认 `confidence = 1.0`，不会触发告警。
- 多候选 SKU 的 `candidates` 和 `need_confirm` 丢失，用户看不到“这个 SKU 其实有多个可能”。
- `original_product_name` 丢失后，审核表中的“订单商品名称”可能回退到按索引找的原始 item，遇到排序/过滤变化时容易对错行。

建议：

- `_match_sku()` 透传 `confidence`、`need_confirm`、`candidates`、`original_product_name`、`order_unit`、`unit_original`、`customer_code`。
- `need_sku_confirm` 的返回逻辑不仅看 `confirmed_sku`，还应在 `review_data.summary` 中明确统计 `low_confidence_count`、`candidate_count`、`unmatched_count`。
- 增加一个无 DB 的单元测试：mock `map_sku_batch()` 返回 `need_confirm=True` 和 `confidence=0.62`，断言 `review_data.mappings[0].is_alert == True` 且候选列表仍存在。

### P0：SKU 确认参数没有真正应用用户修正

位置：`__init__.py` 第 2210 行附近。

当前逻辑是：

- `confirmed_sku` 为假：返回 `need_sku_confirm=True`。
- `confirmed_sku` 为真：直接生成模板。

但没有看到把用户确认/修正后的 SKU 选择应用回 `all_store_results` 的逻辑。也就是说，如果用户在确认阶段选择了候选 SKU 或修正未匹配 SKU，目前主流程缺少明确的“应用 SKU 确认结果”步骤。

影响：

- `confirmed_sku=True` 更像“放行开关”，不是“确认后的映射数据”。
- 如果前一步有多候选或未匹配项，用户修正无法可靠进入模板。

建议：

- 将 `confirmed_sku` 从布尔值升级为结构化确认数据，例如：
  - `confirmed_sku={"updates": [{"store_key": "...", "seq": 3, "sku_code": "...", "unit_type": "...", "quantity": 2}]}`
- 在生成模板前应用这些 updates。
- 对未匹配项，如果没有用户补 SKU，不允许生成模板。

## 3. 中优先级问题

### P1：多门店模板生成没有强校验仓库编码

位置：`__init__.py` 第 3705-3710 行。

单门店 `_generate_template()` 会在仓库编码为空时报错；但多门店 `_generate_multi_store_template()` 直接写 `si.get("warehouse_code", "")`。

影响：

- 多门店场景可能生成仓库编码为空的 Excel。
- 这类错误通常到华鼎导入时才暴露，排查成本高。

建议：

- 多门店模板生成前逐门店校验 `store_code`、`owner_code`、`warehouse_code`。
- 如果 `warehouse_code` 为空但有 `warehouse_name`，尝试走 `_get_warehouse_code()` 补齐。
- 仍为空则返回用户可读错误，不生成模板。

### P1：`tools/_store_matcher.py` 静默吞掉仓库编码查询异常

位置：`tools/_store_matcher.py` 第 382-397 行。

`_build_store_result()` 查询 `warehouse_code_mapping` 失败时直接 `pass`，最终返回空仓库编码。

影响：

- 数据库连通、表结构、仓库配置问题会被隐藏。
- 后续模板生成阶段才暴露，且错误上下文丢失。

建议：

- 至少把异常写入返回结构，如 `warehouse_code_error`。
- 对 `warehouse_name` 存在但无法解析编码的情况，标记为 `need_store_confirm` 或 `need_config_fix`。

### P1：`generate_from_template()` 列号与 31 字段定义不一致

位置：`tools/_template_generator.py` 第 210-215 行。

31 字段中：

- 第 26 列是“业务模式”
- 第 27 列是“业务类型”
- 第 28 列是“收货人”
- 第 29 列是“联系电话”
- 第 30 列是“收货地址”

但 `generate_from_template()` 把收货人写到 26，电话写到 27，地址写到 28。

影响：

- 如果后续启用“基于已有模板生成”，会把收货字段写错列。
- 当前主流程主要使用 `_generate_multi_store_template()`，所以这是潜在风险，不一定已在线触发。

建议：

- 改为按 `HUADING_FIELDS.index("收货人") + 1` 动态定位列，而不是写死列号。
- 对 `generate()`、`_generate_template()`、`_generate_multi_store_template()`、`generate_from_template()` 做同一份列位快照测试。

## 4. 可用性亮点

1. 门店确认流比旧版本更稳：主入口只允许 `match_type == "exact"` 自动确认，其余手机号、地址、联系人、模糊、包含匹配都会进入确认。
2. 多门店确认流已有批量返回：`all_store_matches`、`pending_store_keys`、`confirmed_stores`、`order_data_cache` 这些字段能支撑分批确认。
3. SKU 匹配算法在底层已经考虑了单位、规格、中文括号、尾部分隔符、别名表、多候选，方向正确。
4. 31 字段已统一放入 `config/template_defaults.yaml`，减少双重定义。
5. 有一定回归测试基础，尤其是确认流和 SKU 映射回归测试文件已经存在。

## 5. 建议优化清单

### 第一优先级

1. 修复 `_match_sku()` 字段透传，保留 `confidence`、`need_confirm`、`candidates`。
2. 让 `confirmed_sku` 支持结构化修正，并在模板生成前真正应用用户选择。
3. 多门店模板生成前强校验 `warehouse_code`，缺失则阻断。
4. 增加 SKU 审核信号单元测试，避免“低置信/多候选被洗白”回归。

### 第二优先级

1. 修复 `generate_from_template()` 写错列问题。
2. 将模板写入统一成一个字段名到列号的工具函数。
3. 门店匹配结果返回 `similarity`，现在文档和部分事件逻辑会读这个字段，但 `_build_store_result()` 没统一填。
4. 对 `store_address` / `address`、`store_phone` / `phone` 在多门店与单门店分支中统一命名，减少字段漏传。

### 第三优先级

1. 给 `field_mapping/rules/*.yaml` 增加 schema 校验，避免规则名写错后静默失效。
2. 增加“真实订单样例 -> 标准 JSON -> SKU 审核表 -> Excel”的 golden file 测试。
3. 版本号统一检查：`SKILL.md`、`VERSION`、`OrderToHuadingTemplate.VERSION` 应在 CI 中一致。
4. 将真实 DB 回归测试和无 DB 单元测试拆开，CI 默认跑无 DB 测试，人工或定时任务跑 DB 准确率测试。

## 6. 本次验证

已执行并通过：

```bash
python3 scripts/test_execute_confirmation_flow.py
python3 scripts/test_order_parser_text_fallback.py
python3 scripts/test_execute_import_fallback.py
python3 -m compileall -q .
```

说明：

- `test_execute_confirmation_flow.py` 运行时反馈采集器尝试连接本地 PostgreSQL，被沙箱拒绝，但测试自身通过。
- 本次未跑真实 DB 的 SKU 准确率测试，因为该类测试依赖实际数据库配置和数据状态。

## 7. 最终判断

这个 skill 已经可以作为“人工确认型订单转换工具”继续迭代使用，尤其适合先由 Agent 解析和推荐映射，再由用户确认后出模板。

但如果目标是“可放心导入华鼎”的稳定生产链路，建议先修复 P0 项。当前最大风险不是完全跑不通，而是某些低置信或多候选 SKU 会在主入口被格式化掉风险信号，从而让用户在审核表里看不到真正需要确认的地方。
