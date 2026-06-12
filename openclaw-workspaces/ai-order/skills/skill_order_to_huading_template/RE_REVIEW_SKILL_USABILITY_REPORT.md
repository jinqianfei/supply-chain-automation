# skill-order-to-huading-template 重新 Review 报告

生成时间：2026-06-12  
审查对象：`skill_order_to_huading_template` 当前工作区  
版本状态：`VERSION=5.15.2`，但运行代码与文档仍存在 `5.15.1` 残留

## 结论

当前 skill 的主流程已经具备可用性：解析、字段标准化、门店确认、SKU 确认、模板生成的框架完整；门店/货主/仓库准确率在评估集上为 100%。但本次复核发现一个新的 P1 可用性回归：人工确认门店后，系统为判断 `store_corrected` 又强制重跑门店匹配，一旦数据库不可用或测试隔离 DB，就会直接返回 `E401 数据库连接失败`，导致本应进入 SKU 确认的流程被中断。

## 本次验证结果

### 自动化验证

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| `python3 -m compileall -q .` | 通过 | 语法层面无错误 |
| `python3 scripts/test_order_parser_text_fallback.py` | 通过 | 文本解析 fallback 正常 |
| `python3 scripts/test_execute_import_fallback.py` | 通过 | execute helper import fallback 正常 |
| `python3 scripts/test_execute_confirmation_flow.py` | 失败 | 单门店确认后被 DB 强依赖打断，未返回 `need_sku_confirm` |
| `bash scripts/version_check.sh` | 失败 | 版本号 4 处不一致 |
| `python3 scripts/accuracy_audit.py` | 通过 | 需联网只读 DB；准确率见下 |

### 准确率

| 维度 | 准确率 |
| --- | ---: |
| 门店 `store_code` | 10/10 = 100.0% |
| 货主 `owner_code` | 10/10 = 100.0% |
| 仓库 `warehouse_code` | 7/7 = 100.0% |
| SKU `sku_code` | 25/31 = 80.6% |
| 单位类型 `unit_type` | 29/31 = 93.5% |
| 需要人工确认 | 5/31 = 16.1% |
| 未匹配 | 1/31 = 3.2% |

SKU 失败样本：

| 商品 | 系统结果 | GT | 判断 |
| --- | --- | --- | --- |
| 鱼你幸福青花椒酱料（新款）—原椒麻酱料 | UNMATCHED | SK250214000074 | 真实未命中，需要别名/名称归一 |
| 免浆巴沙鱼片 | SK240803000119 | SK251101000101 | 同名/近名多 SKU，规格区分不足 |
| 免浆黑鱼片 | SK240803000117 | SK250612000056 | 同名/近名多 SKU，规格区分不足 |
| 免浆巴沙鱼片 | SK240803000119 | SK240803000107 | 同名/近名多 SKU，规格区分不足 |
| 调面汁 | SK250327000074 | SK250327000076 | 疑似 GT 问题；系统精确匹配更可信 |
| 深岩静腌西冷牛排 | SK250820000194 | SK241225000055 | 疑似 GT 问题；GT 指向商品名明显不一致 |

## Findings

### P1：人工确认门店后仍强制重跑门店匹配，DB 不可用时阻断 SKU 确认

位置：`__init__.py:2145-2156`

现象：`test_execute_confirmation_flow.py` 中，用户已传入 `confirmed_store`，且 SKU 有未匹配商品，预期返回 `need_sku_confirm=True`。当前代码却在确认门店后调用 `_call_match_store()` 去判断系统原始匹配和人工选择是否一致；该调用访问数据库，沙箱/离线/DB 抖动时抛出 `psycopg2.OperationalError`，最终返回 `E401`。

影响：
- 人工确认结果无法保证继续生效。
- DB 短暂不可用时，已经完成的门店确认也不能进入 SKU 确认。
- 单元测试无法隔离外部 DB，CI 稳定性下降。

建议：
- 将这次 `_call_match_store()` 包在容错逻辑中；失败时不要阻断主流程，只跳过 `store_corrected` 判定或记录 warning。
- 更优做法是在需要确认门店时把系统候选结果缓存进 `order_data_cache`，人工确认后直接与缓存候选比较，不再二次访问 DB。

### P1：版本号不一致，发布态不可信

位置：`VERSION`、`SKILL.md:27`、`README.md:7`、`__init__.py:397`、`../../AGENTS.md`、`../../TOOLS.md`

`VERSION` 和 `CHANGELOG.md` 是 `5.15.2`，但 `SKILL.md`、`README.md`、`__init__.py VERSION`、`AGENTS.md`、`TOOLS.md` 仍是 `5.15.1`。`scripts/version_check.sh` 已明确失败。

影响：
- `order_complete` 事件里的 `skill_version` 仍可能写入 `5.15.1`。
- 排查线上准确率或纠错事件时无法确认真实代码版本。
- 发布/回滚依据不可靠。

建议：以 `VERSION=5.15.2` 为准同步全部版本字段；如当前代码已包含未发布的 `v5.15.3` 修复注释，则先决定是否正式升版到 `5.15.3`。

### P2：手机号低相似度候选被直接丢弃，人工确认信息不足

位置：`tools/_store_matcher.py:163-217`

当前已修复“手机号精确命中直接错配门店”的主要问题：手机号命中后会结合门店名相似度判断，高相似度自动通过，中等相似度要求确认。但当手机号命中且门店名相似度低于 0.6 时，代码继续后续名称/地址匹配，没有把这个手机号命中对象作为低置信候选返回。

影响：
- 对“手机号确实来自订单，但门店名称写法差异很大”的场景，用户看不到手机号命中的候选门店。
- 审核门店错误原因时信息不完整。

建议：低相似度手机号命中不要自动确认，但应放入 `candidates`，标记 `low_similarity_phone_candidate`，供人工确认页展示。

### P2：`contact_person` 兜底路径未处理多门店共用手机号

位置：`tools/_store_matcher.py:313-317`、`tools/_store_matcher.py:568-604`

`_find_by_phone()` 在多门店共用手机号时会返回 `{"_multi": True, "stores": [...]}`。主手机号路径已经处理了这个结构，但 `contact_person` 兜底路径仍直接 `_build_store_result(by_phone, ...)`，可能构造出字段缺失或错误的门店结果。

建议：复用主手机号路径的多候选打分逻辑，或在兜底路径发现 `_multi` 时返回 `need_confirm=True + candidates`。

### P2：SKU 别名 YAML 支持已接入，但当前别名文件为空，无法改善未命中样本

位置：`tools/_sku_mapper.py:762-772`、`field_mapping/rules/sku_aliases_auto.yaml`

代码已经加载 YAML SKU 别名，但 `sku_aliases_auto.yaml` 当前 `aliases: []`。因此“鱼你幸福青花椒酱料（新款）—原椒麻酱料”这类报货名仍无法通过自学习别名命中。

建议：将人工确认后的 SKU 修正真正写入别名来源，至少覆盖高频未命中和多 SKU 歧义样本；同时记录规格、单位和货主，避免同名 SKU 误归一。

## 已修复/表现正常的点

- 字段标准化层已同时输出 `phone/store_phone` 与 `address/store_address`，下游读取兼容性改善。
- SKU 人工补未匹配项时已保留 `seq/spec/product_spec/remark/original_product_name`，并按 `seq` 排序，降低模板错行风险。
- `confirmed_sku=True` 不再允许带未匹配 SKU 直接生成模板。
- SKU update 失败会返回 `failed_updates`，不再静默忽略。
- 门店手机号匹配已加入门店名称相似度校验，原“手机号精确命中另一个门店”的核心风险已降低。

## 优化优先级

1. 修复 `confirmed_store` 后二次 DB 匹配导致 `E401` 的 P1 回归。
2. 同步版本号，保证 `version_check.sh` 通过。
3. 改造门店匹配候选返回：低相似手机号命中、多门店共用手机号都进入人工候选，而不是丢弃或错误构造。
4. 将人工 SKU 修正沉淀到可用别名表，优先覆盖未命中样本和高频多 SKU 歧义。
5. 增加一个无 DB 的确认流回归测试，确保用户已确认门店后，即使系统匹配对比失败，也能继续进入 SKU 确认。
