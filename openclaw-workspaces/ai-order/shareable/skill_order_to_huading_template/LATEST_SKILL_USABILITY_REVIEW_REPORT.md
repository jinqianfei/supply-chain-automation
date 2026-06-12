# 最新 Skill 可用性复审报告

审核日期：2026-06-11  
审核对象：`skill-order-to-huading-template` 当前工作区代码  
当前版本：`5.15.1`  
审核目的：复核最新代码状态下 skill 的可用性，确认上一轮风险是否已修复，并记录剩余问题。

## 1. 总体结论

当前 skill 相比上一轮又进一步稳定，已经可以作为“人工确认型订单转华鼎模板”使用。

本轮确认已改善：

1. SKU 手动修正新增记录已保留 `seq/spec/product_spec/remark/original_product_name`。
2. 手动补未匹配 SKU 后，会按 `seq` 重排 `sku_results`，降低模板错行风险。
3. `confirmed_sku["updates"]` 匹配不到时，不再静默跳过，会返回 `failed_updates`。
4. 字段标准化层已同时输出 `phone/store_phone`、`address/store_address`。
5. SKU 别名 YAML 已接入 `map_sku_batch()`，具备后续自学习别名扩展能力。

当前仍不建议完全自动放行。剩余风险主要集中在门店手机号冲突候选展示，以及复用手机号在联系人兜底分支的边界处理。

## 2. 本轮主要发现

### P1：手机号低相似度分支未合并手机号候选

位置：`tools/_store_matcher.py` 第 163 行附近。

当前逻辑：

1. 如果手机号命中门店，会计算输入门店名和手机号命中门店名的相似度。
2. 如果相似度高，返回手机号+门店名双重匹配。
3. 如果相似度中等，返回需确认结果。
4. 如果相似度低于 0.6，继续走名称/地址匹配。

问题：

当手机号命中但相似度低时，手机号命中的门店会被丢弃，不会合并到后续候选中。

影响：

- 手机号仍是重要业务线索。
- 如果手机号和门店名冲突，用户最好同时看到两类候选：
  - 手机号命中门店
  - 名称/地址命中门店
- 当前用户可能只看到名称/地址候选，不知道手机号指向另一个门店。

建议：

1. 手机号命中但相似度低时，将手机号命中结果暂存。
2. 后续名称/地址匹配返回时，合并手机号候选。
3. 候选增加来源字段，例如：

```json
{
  "candidate_source": "phone_exact",
  "match_method": "手机号命中但门店名相似度低"
}
```

### P1：contact_person 兜底中 `_find_by_phone()` 多门店结果可能被当作单门店处理

位置：`tools/_store_matcher.py` 第 313 行附近。

`_find_by_phone()` 当前支持手机号复用场景。如果同一个手机号对应多个门店，会返回：

```python
{
    "_multi": True,
    "stores": [...]
}
```

但 contact_person 兜底分支中直接执行：

```python
return _build_store_result(by_phone, "phone_exact", ...)
```

如果 `by_phone` 是 `_multi` 结构，`_build_store_result()` 会从顶层取 `store_code/store_name/owner_code`，这些字段不存在，最终可能返回空门店信息。

影响：

- 仅在 contact_person 兜底路径 + 复用手机号时触发。
- 会导致候选信息为空或错误。

建议：

1. 在 contact_person 兜底中检测 `by_phone.get("_multi")`。
2. 如果是多门店，复用主手机号分支的相似度排序逻辑。
3. 返回 `need_confirm=True` 和候选列表，而不是构造空门店。

### P2：SKU 自学习别名能力已接入，但当前别名表为空

位置：

- `tools/_sku_mapper.py` 第 762 行附近
- `field_mapping/rules/sku_aliases_auto.yaml`

当前代码会加载：

```text
field_mapping/rules/sku_aliases_auto.yaml
```

并将 YAML 中的别名合并进 `alias_groups`。

但当前文件内容为：

```yaml
aliases: []
```

影响：

- 自学习能力已具备接口，但目前还没有实际数据贡献。
- 例如此前未命中的 `鱼你幸福青花椒酱料（新款）—原椒麻酱料`，仍不会自动通过 YAML 别名修复，除非后续别名被写入。

建议：

1. 将已确认的 SKU 别名写入 `sku_aliases_auto.yaml` 或数据库别名表。
2. 针对别名加载增加回归测试。
3. 后续准确率报告中单独统计“别名命中率”。

## 3. 已改善项

| 项目 | 当前状态 |
| --- | --- |
| 字段标准化输出 `phone/address` 兼容字段 | 已修复 |
| 主流程读取 `phone/store_phone`、`address/store_address` | 已修复 |
| 未匹配 SKU 时 `confirmed_sku=True` 直接放行 | 已修复 |
| 商品总数统计漏算未匹配商品 | 已修复 |
| SKU 修正后不重算 `review_data` | 已修复 |
| 用户补未匹配 SKU 不带 `seq` | 已修复 |
| 用户补 SKU 后不按原订单顺序排序 | 已修复 |
| SKU update 匹配不到时静默跳过 | 已修复 |
| SKU YAML 别名加载能力 | 已接入 |

## 4. 当前可用性判断

### 可以使用

适合用于：

- 人工确认型订单处理。
- 门店/SKU 都需要用户确认后生成华鼎模板的流程。
- 有明确货主、门店、SKU 基础数据的订单。
- 多门店订单合并生成华鼎模板。

### 不建议完全自动放行

暂不建议用于：

- 无人工确认的全自动出库模板生成。
- 手机号复用严重、门店名不规范的订单。
- 大量同名/近名 SKU 且别名表未完善的货主。
- 未经过足够 GT 回归测试的新客户订单。

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
- `requests` 版本兼容警告不影响本轮验证。

## 6. 最终结论

当前 skill 的主流程可用性已经较好，可以继续投入人工确认型订单转换使用。

剩余需要优先补强的是门店候选展示逻辑：

1. 手机号低相似度时保留并展示手机号候选。
2. contact_person 兜底路径正确处理复用手机号。

SKU 侧当前主要依赖人工确认和别名积累；手动修正链路已基本可用，下一步应补别名数据和别名命中回归测试。
