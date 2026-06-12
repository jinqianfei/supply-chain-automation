# 当前 Skill 可用性审核报告

审核日期：2026-06-11  
审核对象：`skill-order-to-huading-template` 当前工作区代码  
审核目的：复核当前 skill 是否可用于订单转华鼎模板，以及剩余影响生产可用性的风险点。

## 1. 总体结论

当前 skill 的可用性相比前一轮已有明显提升，已经适合作为“人工确认型订单转华鼎模板”使用。

本轮确认已改善的关键点：

1. 主流程读取门店手机号/地址时，已兼容 `phone/store_phone` 和 `address/store_address`。
2. `confirmed_sku=True` 不再允许在仍有未匹配 SKU 时直接生成模板。
3. 商品统计口径已改为 `sku_results + unmatched_items`，避免未匹配商品从总数中消失。
4. `confirmed_sku["updates"]` 后会重新生成 `review_data` 和统计。
5. 手机号匹配已增加门店名相似度校验，不再无条件直接采用手机号命中结果。

当前仍不建议完全自动放行。原因是 SKU 手动修正链路还有错行和静默失效风险，可能导致用户以为已修正，但最终模板仍不完全可信。

## 2. 当前可用范围

适合使用：

- 客户订单转华鼎模板。
- 需要人工确认门店和 SKU 的订单。
- 已知货主、已有门店和 SKU 基础数据的订单。
- 多门店订单批量确认后生成同一张华鼎模板。

暂不建议使用为完全自动化：

- 未匹配 SKU 较多的订单。
- 用户需要频繁手动补 SKU 的订单。
- 手机号复用、门店名不规范、门店简称较多的订单。
- 同名/近名/多规格 SKU 密集的货主。

## 3. 主要发现

### P1：用户补未匹配 SKU 后，新记录缺少 seq，且 append 到末尾

位置：`__init__.py` 第 2285 行附近。

当用户通过 `confirmed_sku["updates"]` 补齐未匹配 SKU 时，代码会把未匹配商品从 `unmatched_items` 移到 `sku_results`，但新增记录没有带上：

- `seq`
- `spec`
- `remark`
- `product_spec`

并且新增记录是 append 到 `sku_results` 末尾。

影响：

- 如果补的是订单中间某一行，审核表可能错行。
- 模板商品顺序可能与原订单顺序不一致。
- 后续 `_generate_mapping_comparison_multi()` 按 `enumerate(sku_results)` 对齐 `store_items`，容易产生映射展示错位。

建议：

1. 新增记录必须保留原始 `seq/spec/remark/product_spec`。
2. 应用 updates 后按 `seq` 重排 `sku_results`。
3. 审核表不要只按 `idx` 对齐，应优先用 `seq` 找订单原始行。

### P1：SKU 修正 update 可能静默失效

位置：`__init__.py` 第 2270 行附近。

当前 `confirmed_sku["updates"]` 里如果某条 update 的 `store_key` 或 `seq` 匹配不到任何商品，代码会直接跳过。

影响：

- 用户以为已经修正 SKU。
- 实际没有应用。
- 如果该项原本是已匹配 SKU，模板仍可能使用旧 SKU。
- 如果该项原本是未匹配 SKU，可能继续阻断，但用户不知道是哪条 update 没生效。

建议：

1. 记录 `applied_updates` 和 `failed_updates`。
2. 如果有 `failed_updates`，返回 `need_sku_confirm=True`。
3. 返回失败原因，例如：`store_key_not_found`、`seq_not_found`、`missing_sku_code`。

### P1：手机号与门店名差异大时，手机号命中的候选未合并返回

位置：`tools/_store_matcher.py` 第 163 行附近。

当前逻辑已经比旧版更安全：手机号命中后会计算门店名相似度；如果相似度低于阈值，会继续执行名称/地址匹配。

但手机号命中的那个门店没有被保留到最终候选列表。

影响：

- 手机号仍是重要业务线索。
- 当门店名和手机号冲突时，用户最好同时看到两类候选：手机号命中门店、名称命中门店。
- 当前用户可能只看到名称候选，而不知道手机号指向了另一个门店。

建议：

1. 手机号命中但相似度低时，将手机号命中结果暂存。
2. 后续名称/地址匹配结果返回时，把手机号候选合并进去。
3. 候选字段中增加 `candidate_source`，例如 `phone_exact`、`name_fuzzy`、`address_keyword`。

### P2：字段标准化层仍只输出 store_phone/store_address，没有回写 phone/address

位置：`tools/_field_transformer.py` 第 245 行附近。

主流程当前已经兼容读取：

```python
phone = store_data.get("phone") or store_data.get("store_phone")
address = store_data.get("address") or store_data.get("store_address")
```

所以主链路可用。

但 `tools_transform()` 的统一 JSON 仍只输出：

```python
store_phone
store_address
```

没有同步输出：

```python
phone
address
```

影响：

- 如果其他脚本或下游直接消费 `tools_transform()` 输出，仍可能漏掉手机号/地址。
- 统一 JSON schema 的可读性和兼容性不够好。

建议：

同时输出兼容字段：

```python
"phone": phone,
"store_phone": phone,
"address": address,
"store_address": address,
```

## 4. 已修复/已改善项

本轮复核确认以下问题已被当前代码改善：

| 问题 | 当前状态 |
| --- | --- |
| `_match_sku()` 不透传 `confidence/candidates` | 已透传 |
| 多门店模板缺仓库编码仍生成 | 已增加仓库编码阻断 |
| `generate_from_template()` 收货字段列号错位 | 已改为按 `HUADING_FIELDS` 动态定位 |
| `confirmed_sku=True` 可绕过未匹配阻断 | 已阻断 |
| 商品统计未计入未匹配商品 | 已修正 |
| 用户 SKU 修正后不重算 `review_data` | 已重算 |
| 手机号命中不校验门店名 | 已增加相似度校验 |

## 5. 验证结果

已执行：

```bash
python3 scripts/test_execute_confirmation_flow.py
python3 scripts/test_order_parser_text_fallback.py
python3 scripts/test_execute_import_fallback.py
python3 -m compileall -q .
```

结果：

- 全部通过。
- `test_execute_confirmation_flow.py` 中反馈采集器尝试连接本地 PostgreSQL，被沙箱拒绝，但不影响测试结果。
- `requests` 依赖版本警告不影响本轮验证。

## 6. 最终判断

当前 skill 可以继续投入人工确认型订单处理流程。

建议在生产使用前优先修复两个 P1：

1. 用户补未匹配 SKU 后保留 `seq` 并按原订单顺序重排。
2. 对未应用成功的 `confirmed_sku["updates"]` 做显式报错。

这两个修完后，skill 的模板生成可信度会明显提高；再补充手机号冲突候选合并和统一 JSON 兼容字段，整体可用性会更稳。
