# Skill 可用性完整代码 Review 报告

审核日期：2026-06-11  
审核对象：`skill-order-to-huading-template` 当前工作区代码  
审核方式：静态代码 review + 现有回归测试 + 前序准确率测试结果复核

## 1. 总体结论

当前 skill 已经具备订单转华鼎模板的完整闭环，整体架构可继续迭代使用：

1. 解析层：`tools/_order_parser.py`
2. 字段标准化层：`tools/_field_transformer.py`
3. 门店匹配层：`tools/_store_matcher.py`
4. SKU 匹配层：`tools/_sku_mapper.py`
5. 主流程编排：`__init__.py::OrderToHuadingTemplate.execute`
6. 模板生成：`__init__.py::_generate_multi_store_template` / `tools/_template_generator.py`

相比前一次审核，当前代码已经修复/改善了几项关键问题：

- `_match_sku()` 已透传 `confidence`、`need_confirm`、`candidates`、`original_product_name`。
- 多门店模板生成前已增加仓库编码缺失阻断。
- `generate_from_template()` 收货人/电话/地址列号已改成按 `HUADING_FIELDS` 动态定位。
- `confirmed_sku` 已开始支持结构化 `updates`。

但从“稳定可用于生产导入华鼎”的标准看，仍有 3 个高优先级问题需要先处理，否则会出现门店匹配信号丢失、未匹配商品被漏出模板、统计数据误导用户等风险。

## 2. 关键发现

### P0：字段标准化后手机号/地址字段名与主流程读取字段不一致

位置：

- `tools/_field_transformer.py` 第 245-254 行
- `__init__.py` 第 1935-1941 行
- `__init__.py` 第 2082-2089 行

字段标准化输出的是：

```python
{
    "store_phone": ...,
    "store_address": ...,
}
```

但主流程多门店分支读取：

```python
phone=store_data.get("phone")
address=store_data.get("store_address")
```

单门店分支读取：

```python
phone_val = store_data.get("phone")
address_val = store_data.get("address")
```

影响：

- 经过 `tools_transform()` 后，手机号常常只存在于 `store_phone`，主流程却读 `phone`，导致手机号匹配失效。
- 单门店分支连 `store_address` 也没有读取，地址辅助匹配也会失效。
- 这会降低门店匹配准确率，尤其影响“门店名不规范但电话/地址可靠”的订单。

建议：

统一读取兼容字段：

```python
phone = store_data.get("phone") or store_data.get("store_phone")
address = store_data.get("address") or store_data.get("store_address")
```

并建议 `_field_transformer.py` 同时输出兼容别名：

```python
"phone": phone,
"address": address,
"store_phone": phone,
"store_address": address,
```

### P0：`confirmed_sku=True` 会在仍有未匹配 SKU 时生成不完整模板

位置：`__init__.py` 第 2210-2287 行。

当前逻辑：

1. `confirmed_sku` 为假时，返回 `need_sku_confirm=True`。
2. `confirmed_sku` 是 dict 且有 `updates` 时，应用用户修正，并检查是否仍有未匹配。
3. 但如果调用方传 `confirmed_sku=True`，代码会跳过确认阻断，直接生成模板。

风险：

- 未匹配商品不在 `sku_results` 中。
- 模板生成只遍历 `sku_results`。
- 因此 `confirmed_sku=True` 会把未匹配商品静默漏掉，生成少行 Excel。

这对生产导入是高风险：用户可能以为整单已生成，实际有商品缺失。

建议：

生成模板前无论 `confirmed_sku` 是 bool 还是 dict，都必须阻断未匹配：

```python
if total_unmatched > 0:
    return need_sku_confirm
```

只有两种情况允许继续：

- `total_unmatched == 0`
- 或 `confirmed_sku["updates"]` 已补齐所有未匹配项

### P1：商品统计口径错误，未匹配商品会从总商品数里消失

位置：`__init__.py` 第 2192-2219 行。

当前统计：

```python
total_items = sum(len(r["sku_results"]) for r in all_store_results)
total_unmatched = sum(len(r["unmatched_items"]) for r in all_store_results)
matched_count = total_items - total_unmatched
```

问题：

- `sku_results` 只包含已匹配商品。
- 未匹配商品在 `unmatched_items`。
- 因此 `total_items` 实际是“已匹配商品数”，不是订单总商品数。

如果 10 个商品中 2 个未匹配：

- 当前 `total_items = 8`
- `total_unmatched = 2`
- `matched_count = 6`

正确应该是：

- `total_items = 10`
- `matched_count = 8`
- `unmatched_count = 2`

影响：

- 返回给用户的 `item_count`、`matched_count` 会错误。
- 成功/失败摘要会误导用户。
- 后续准确率统计或人工审核会被污染。

建议：

```python
matched_count = sum(len(r["sku_results"]) for r in all_store_results)
unmatched_count = sum(len(r["unmatched_items"]) for r in all_store_results)
total_items = matched_count + unmatched_count
```

### P1：SKU 用户修正后没有重新生成 `review_data`

位置：`__init__.py` 第 2201-2284 行。

当前 `review_data` 在应用 `confirmed_sku["updates"]` 之前生成。用户修正后，只重新计算了 `all_unmatched` 和 `total_unmatched`，但没有重新生成 `review_data`。

影响：

- 如果仍需返回给用户，`review_data` 可能显示旧的未修正 SKU。
- 成功响应中的 `review_data` 也可能和最终生成模板不一致。

建议：

应用 `confirmed_sku["updates"]` 后重新执行：

```python
review_data = self._generate_mapping_comparison_multi(order_data, all_store_results)
```

并重新计算 `has_issues`、`matched_count`、`unmatched_count`。

### P1：手机号命中后仍直接返回，没有做门店名二次校验

位置：`tools/_store_matcher.py` 第 144-149 行。

当前逻辑只要手机号命中就返回 `phone_exact`。虽然主流程不会自动确认 `phone_exact`，但候选仍会偏向手机号命中的门店，且不会继续把名称匹配结果合并为候选。

前序准确率测试已暴露该问题：

- 输入门店：`廖朵朵蛋糕-开封尉氏张英杰`
- 手机号命中：另一个同货主门店
- 货主正确，门店错误

建议：

手机号命中后继续做门店名相似度校验：

- 名称相似度高：手机号命中作为首选候选。
- 名称相似度低：继续执行名称/地址匹配，合并候选，要求用户确认。

### P2：字段清洗会去掉商品名中间信息，可能影响 SKU 唯一性

位置：`tools/_field_transformer.py` 第 22-30 行。

`clean_text()` 会删除 Unicode 范围 `\u200b-\u200f`，这是合理的；但它也会去掉所有普通空格。对多数中文商品没问题，但对某些规格/英文品名可能会让原始商品名和规格边界更难保留。

当前更大的问题不是这个函数本身，而是字段标准化层没有保留足够多原始字段，导致后续审计时需要依赖 `original_product_name` 补救。

建议：

- 标准字段用于匹配。
- 原始字段另存，例如 `raw_product_name`、`raw_spec`，用于审核展示和追溯。

## 3. 可用性判断

### 当前可用场景

适合：

- 人工确认型订单转换。
- 门店和 SKU 都经过用户确认后生成模板。
- 小批量/中批量订单处理。
- 已知货主、已知 SKU 别名较完整的订单。

不建议直接自动放行：

- 有未匹配 SKU 的订单。
- 多门店且门店字段不规范的订单。
- 手机号可能复用或变更的门店。
- 鱼片、酱料、牛排等同名/近名/多规格 SKU 密集的货主。

### 生产可用门槛

建议至少修复以下 3 项后再作为稳定生产链路：

1. 修复 `phone/store_phone`、`address/store_address` 字段读取不一致。
2. 禁止 `confirmed_sku=True` 在仍有未匹配 SKU 时生成模板。
3. 修正 `item_count/matched_count/unmatched_count` 统计口径。

## 4. 已验证内容

已执行：

```bash
python3 scripts/test_execute_confirmation_flow.py
python3 scripts/test_order_parser_text_fallback.py
python3 scripts/test_execute_import_fallback.py
python3 -m compileall -q .
```

结果：

- 全部通过。
- `test_execute_confirmation_flow.py` 运行时反馈采集器尝试连接本地 PostgreSQL，被沙箱拒绝，但测试本身通过。
- `requests` 版本兼容警告不影响本次测试结果。

前序准确率结果：

| 指标 | 命中/可评估 | 准确率 |
| --- | ---: | ---: |
| 门店 | 9 / 10 | 90.0% |
| 货主 | 10 / 10 | 100.0% |
| 仓库 | 7 / 7 | 100.0% |
| SKU | 25 / 31 | 80.6% |
| 单位类型 | 29 / 31 | 93.5% |

## 5. 最终结论

这个 skill 目前可以继续作为“带人工确认的订单映射工具”使用，但还不应被视为“自动准确生成华鼎导入模板”的稳定版本。

当前最大风险不是解析失败，而是：

- 匹配辅助字段在标准化后没有被主流程正确读取。
- 未匹配 SKU 在某些确认路径下可能被静默漏出模板。
- 用户看到的商品统计可能不可信。

修复上述问题后，再补充针对门店手机号复用、SKU 多候选、未匹配 SKU 阻断的回归测试，整体可用性会明显提升。
