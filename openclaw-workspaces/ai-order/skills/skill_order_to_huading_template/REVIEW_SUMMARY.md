# Code Review Summary - 2026-06-11

## Review Scope

本次 review 针对当前工作区未提交改动，重点检查：

- 多门店确认流程改动
- SKU 匹配与候选选择逻辑
- 版本号与文档一致性
- 本地可运行回归测试结果

## Overall Conclusion

当前改动方向基本清晰：v5.14.0 希望在 SKU 选择时引入订单单位、规格和多候选确认机制，减少大小单位选错的问题。

但目前仍有几个发布前必须处理的问题，其中最关键的是多门店确认返回体破坏了既有调用契约，已经导致现有无 DB 回归测试失败。SKU 候选并列逻辑也存在低置信度候选被当成匹配返回的风险。

## Findings

### P1 - 多门店确认返回体破坏现有调用契约

位置：

- `__init__.py:2034`
- `scripts/test_execute_confirmation_flow.py:104`
- `SKILL.md:524`
- `scripts/e2e_v5140.py:84`

问题：

新的批量门店确认返回体只返回：

- `all_store_matches`
- `pending_store_keys`
- `pending_count`
- `confirmed_count`
- `failed_count`

但旧调用方、文档和测试仍依赖顶层字段：

- `store_name_submitted`
- `matched_store`
- `candidates`

本地运行 `python3 scripts/test_execute_confirmation_flow.py` 已复现失败：

```text
KeyError: 'store_name_submitted'
```

影响：

- 旧客户端无法继续确认下一个门店
- 新增 e2e 脚本会拿不到 `candidates` / `matched_store`
- 文档示例与真实返回不一致

建议：

- 保留 batch 字段的同时，为兼容旧流程补回首个 pending 门店的顶层 `store_name_submitted`、`matched_store`、`candidates`
- 或同步修改所有调用方、文档和测试，明确只支持 batch confirmation

### P1 - SKU 并列候选绕过最低置信度阈值

位置：

- `tools/_sku_mapper.py:844`
- `tools/_sku_mapper.py:884`
- `tools/_sku_mapper.py:930`

问题：

Layer 2 / 2.5 / 3 在检测到多个并列候选时，会直接返回 `_build_with_candidates(...)`，但没有先判断最高分是否达到该层最低阈值。

这意味着多个低分候选只要分数接近，就可能被返回为：

```python
matched = True
need_confirm = True
```

影响：

- 弱相关商品可能进入确认流程
- 用户看到“多个候选”时会误以为系统已找到可信匹配范围
- 全量相似度层和分词层更容易放大误报

建议：

- Layer 2 并列候选仍需 `ts >= 0.6`
- Layer 2.5 并列候选仍需 `ts >= 0.7`
- Layer 3 并列候选仍需 `ts >= 0.6`
- 未达阈值时继续进入下一层或返回未匹配

### P2 - 中文括号规格提取回归

位置：

- `tools/_sku_mapper.py:87`

问题：

`_extract_spec_from_name()` 当前括号规格正则只匹配 ASCII 括号，中文括号无法提取规格。

验证结果：

```text
浩然奥尔良翅中(10袋) => 10袋
浩然奥尔良翅中（10袋） =>
```

影响：

- 中文括号商品名无法参与规格匹配
- 和 changelog 中“中文括号修复”的描述不一致
- 可能影响 Layer 1b / Layer 2 的规格判定准确率

建议：

将规格提取正则恢复为同时支持中英文括号，例如：

```python
re.search(r'[\uff08(]([^\uff09)]+)[\uff09)]', name)
```

### P2 - 版本号不一致

位置：

- `VERSION:1`
- `__init__.py:397`
- `README.md:7`
- `SKILL.md:27`

问题：

当前版本信息不一致：

- `VERSION` 为 `5.14.0`
- `SKILL.md` 为 `5.14.0`
- `OrderToHuadingTemplate.VERSION` 仍为 `5.13.2`
- `README.md` 仍为 `v5.13.2`

影响：

- 运行时事件、日志、反馈数据记录错误版本
- 用户和维护者无法确认实际运行版本
- 回归测试中的版本断言可能继续落后

建议：

- 统一更新到 `5.14.0`
- 同步调整事件测试中 `skill_version` 的期望值

## Verification

已运行：

```bash
python3 scripts/test_execute_confirmation_flow.py
```

结果：

- 测试失败
- 失败点为多门店确认响应缺少 `store_name_submitted`
- import 过程中还出现本地 PG socket 权限报错，但不影响此次关键失败判断

未完整运行：

- 真实 DB SKU 回归测试
- 59 个 JSON GT 准确率测试
- Excel e2e 测试

原因：

- 当前环境存在数据库连接限制
- 现有无 DB 回归测试已经复现核心兼容性问题

## Recommended Fix Order

1. 修复多门店确认返回体兼容性，并更新对应测试。
2. 为 SKU 并列候选增加最低分阈值保护。
3. 修复中文括号规格提取，并补一个纯单元测试。
4. 统一版本号到 `5.14.0`。
5. 重新运行本地回归测试。
6. 有 DB 环境时再运行 `scripts/ci_regression.sh` 或 v5.14.0 GT/e2e 脚本。

