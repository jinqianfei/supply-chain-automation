# Phase 3.0 字段名采集 — 详细工单

**版本**: v1.0
**日期**: 2026-06-09
**目标**: 让 skill 按货主自动学习 Excel 字段名，提升订单解析准确率
**前置**: v5.9.0-baseline 备份完成 ✅（`backups/skill_v5.9.0-baseline_20260609_105800/`）
**对应分支**: v5.9.0 → v5.10.0

---

## 1. 核心思想

**沿用现有 `field_mapping/rules/*.yaml`（不建新表）**。

| 维度 | 现在 | Phase 3.0 后 |
|------|------|------------|
| YAML 库 | 人工配置的静态规则 | 人工 + 自动学习的动态规则 |
| 新增字段名 | 人工编辑 YAML | 解析时发现 → 询问用户 → 自动 append |
| 版本控制 | git（手动 commit）| git（**自动 commit**）|
| 历史轨迹 | git log | git log + `.history/` 快照 |

**关键决策**：YAML = 真相源，git = 学习轨迹，DB 只存"事件"（不存"学到的规则"）。

---

## 2. 数据流

```
LLM 解析订单文本
    ↓
输出字段: { "品名": "白桃乌龙", "出库数量": 10, "销售单位": "箱" }
    ↓
_field_transformer._find_std_field("品名", field_aliases)
    ↓
查 创宇.yaml → "品名" 在 product_name 别名里 → 映射成 product_name ✅
    ↓
（如果不在）→ 触发「field_mapping_needed」事件
    ↓
learn/collector 监听 → 写 order_corrections 表
    ↓
UI 询问（CLI 命令 / 飞书卡片）：
   "『品名』是 product_name（商品名称）吗？"
    ↓
用户确认 ✅
    ↓
learn/yaml_updater.append_alias(customer="创宇", std_field="product_name", new_alias="品名")
    ↓
安全 append 到 创宇.yaml（保留缩进/注释/顺序）
    ↓
field_mapping/rules/.history/创宇_20260609_105200.yaml  ← 备份
    ↓
git auto-commit:
   "learn: 创宇 add alias '品名' → product_name (hit_count: 1)"
```

---

## 3. 8 个子任务

### 3.0.1 — 触发「field_mapping_needed」事件

| 项 | 内容 |
|---|---|
| **输入** | LLM 解析出的原始字段名（YAML 里找不到）|
| **输出** | 事件 emit 到 EventBus |
| **修改文件** | `tools/_field_transformer.py` |
| **新增代码** | `_find_std_field` 返回 None 时，emit `field_mapping_needed` 事件（payload 含 shipper_id、raw_field、context）|
| **不变量** | 不阻塞主流程；事件是「待办」语义，不是「错误」|
| **验收** | 给一个不认识的字段，触发后 order_corrections 表多一条记录 |

### 3.0.2 — `learn/yaml_updater.py`（核心新增）

| 项 | 内容 |
|---|---|
| **输入** | (customer, std_field, new_alias) |
| **输出** | 改写后的 YAML 文件 + 备份文件 |
| **新增文件** | `learn/yaml_updater.py`（~150 行）|
| **依赖** | `ruamel.yaml`（保留缩进/注释/顺序，**不**用 PyYAML）|
| **关键方法** | `append_alias(customer, std_field, new_alias)` / `get_aliases(customer, std_field)` / `get_history(customer, limit=10)` |
| **安全机制** | 文件锁（`fcntl.flock`）+ 写前备份到 `.history/` + 异常回滚 |
| **验收** | 单元测试：append 3 次 → YAML 内容正确、`.history/` 有 3 个备份、git diff 显示 3 行新增 |

```python
# 接口示意（不写实现，只看形状）
class YamlUpdater:
    def append_alias(self, customer: str, std_field: str, new_alias: str) -> None: ...
    def remove_alias(self, customer: str, std_field: str, alias_to_remove: str) -> None: ...
    def get_aliases(self, customer: str, std_field: str) -> List[str]: ...
    def get_history(self, customer: str, limit: int = 10) -> List[Path]: ...
```

### 3.0.3 — git auto-commit

| 项 | 内容 |
|---|---|
| **输入** | YAML 文件被修改 |
| **输出** | 一次 git commit |
| **新增文件** | `scripts/post_yaml_update.sh`（~30 行）|
| **触发** | `yaml_updater.append_alias()` 成功后调 `subprocess.run(["bash", "post_yaml_update.sh", customer, std_field, new_alias])` |
| **commit message 模板** | `learn: {customer} add alias '{new_alias}' → {std_field} (hit_count: {n})` |
| **安全机制** | 失败仅日志告警，**不**回滚 YAML（学习数据不能丢）|
| **验收** | 触发 1 次 append，git log 多一条 commit，commit message 格式正确 |

### 3.0.4 — prompt 注入字段映射 hint

| 项 | 内容 |
|---|---|
| **输入** | 加载后的 YAML 别名表 |
| **输出** | LLM prompt 顶部 prepend 字段映射 hint |
| **修改文件** | `tools/_order_parser.py`（`_SINGLE_PROMPT_TEMPLATE` / `_MULTI_PROMPT_TEMPLATE`）|
| **注入位置** | system 消息前，prepend 一段：|

```text
【该货主已知字段映射（请优先使用）】
货主: 创宇
- product_name ← [商品名称, 商品名, 品名, 往来单位名称]
- quantity ← [数量, 出库数量]
- unit ← [销售单位, 单位]
- store_name ← [往来单位名称, 门店名称, 门店, 收货门店]
- store_phone ← [结算单位电话, 联系电话, 电话, 手机号]
- store_address ← [结算单位详细地址, 详细地址, 地址, 收货地址]
- raw_order_no ← [订单号, 单号, 订单编号, 送货单号]
- order_date ← [单据日期, 日期]
- product_spec ← [规格, 包装规格]
- remark ← [备注, 备注信息]
```

| **冷启动** | 0 单 → 不 prepend；1-5 单 → 弱 hint（仅 top5 字段）；≥5 单 → 强 hint（全字段）|
| **验收** | 给一份创宇的 Excel，prompt 里有完整字段映射；解析准确率比 v5.9.0 baseline 提升 |

### 3.0.5 — 「字段映射确认」UI（CLI 版，v1.0）

| 项 | 内容 |
|---|---|
| **输入** | 待确认的 raw_field + 候选 std_field 列表 |
| **输出** | 用户确认的 std_field |
| **新增文件** | `scripts/confirm_field_mapping.py`（~80 行）|
| **交互** | 命令行交互：`『品名』是 product_name 吗？[Y/n/选其他]` |
| **数据源** | 读 `order_corrections` 表 type=field_mapping_needed 的 pending 记录 |
| **回写** | 确认后调 `yaml_updater.append_alias()`，状态从 pending → confirmed |
| **飞书版** | v2.0 再做（依赖 G1 推送系统）|
| **验收** | 跑脚本，pending 记录变 confirmed，YAML 多一行 |

### 3.0.6 — 冷启动：fork 出独立 YAML

| 项 | 内容 |
|---|---|
| **输入** | 某 shipper_id 解析 ≥5 单 |
| **输出** | 自动从 `default.yaml` 复制出 `{shipper_name}.yaml`（如 `廖朵朵.yaml`）|
| **新增代码** | `learn/yaml_updater.py` 新增 `fork_customer_yaml(shipper_id, shipper_name)` |
| **触发** | `learn_daily.sh` 每日 10:00 跑，统计 `order_feedback` 表 |
| **告警** | fork 成功 → 飞书推金姐：「廖朵朵 已自动 fork YAML，请审」|
| **验收** | 模拟一个 shipper_id 累计 5 单，daily_wrap 后目录多一个 `廖朵朵.yaml` |

### 3.0.7 — YAML 历史快照

| 项 | 内容 |
|---|---|
| **输入** | 每次 `append_alias` 前的 YAML 内容 |
| **输出** | `field_mapping/rules/.history/{customer}_{timestamp}.yaml` |
| **实现** | 在 `yaml_updater.append_alias()` 开头加：复制当前 YAML 到 `.history/` |
| **保留策略** | 最近 50 个快照（超出自动删旧）|
| **.gitignore** | `.history/` 加入 `.gitignore`（**不**污染 git）|
| **验收** | append 5 次，`.history/` 目录有 5 个 YAML 文件，git status clean |

### 3.0.8 — 测试 + 文档

| 项 | 内容 |
|---|---|
| **单元测试** | `tests/test_yaml_updater.py`（append / remove / 并发 / 回滚）|
| **集成测试** | `tests/test_phase3_e2e.py`（解析 → 触发事件 → 确认 → YAML 变化 → git commit）|
| **真实订单回归** | 跑 5 份历史订单（创宇、小江溪、王小五 + 2 个未知），对比 v5.9.0 baseline |
| **文档更新** | `SKILL.md` 新增「Phase 3.0 自适应学习」章节 / `CHANGELOG.md` 补 [5.10.0] 条目 / `VERSION` 5.9.0 → 5.10.0 |
| **验收** | `bash scripts/test_phase3.sh` 全过；回归准确率 ≥ baseline + 10% |

---

## 4. 文件改动清单

```
修改：
  tools/_field_transformer.py        # 找不到字段时 emit 事件
  tools/_order_parser.py             # prompt prepend 字段 hint
  learn/collector.py                 # 新增 field_mapping_needed 订阅
  field_mapping/rules/*.yaml         # git 接收自动 commit

新增：
  learn/yaml_updater.py              # YAML 读写核心
  learn/yaml_forker.py               # 冷启动 fork
  scripts/confirm_field_mapping.py   # CLI UI
  scripts/post_yaml_update.sh        # git auto-commit hook
  tests/test_yaml_updater.py         # 单元测试
  tests/test_phase3_e2e.py           # 端到端测试
  scripts/test_phase3.sh             # 集成测试入口
  docs/PHASE_3_0_FIELD_ALIAS_LEARNING.md  # 本文档
```

**总工作量**：5-5.5 天

---

## 5. 风险点

| 风险 | 缓解 |
|------|------|
| YAML 并发修改冲突 | `fcntl.flock` 文件锁 + `.history/` 备份回滚 |
| ruamel.yaml 兼容性 | 仅在 `learn/yaml_updater.py` 用，**不**改 `_field_transformer._load_rules` |
| 自动 commit 污染 git | 限制每日 ≤ 50 commit，超出转批量 commit |
| 字段映射错误学习 | 用户必须**显式确认**才入库；不接 fuzzy 自动 accept |
| 冷启动 fork 时机不对 | 阈值要严格（≥5 单 + 解析成功率 ≥ 80%）|

---

## 6. 验收标准（Phase 3.0 完成定义）

- [ ] 8 个子任务全部完成
- [ ] `bash scripts/test_phase3.sh` 全过
- [ ] 真实订单回归：5 份订单解析准确率 ≥ baseline + 10%
- [ ] `VERSION` = 5.10.0 / `CHANGELOG.md` 补 [5.10.0] 条目 / `SKILL.md` 同步
- [ ] git tag `v5.10.0` 打在 release commit
- [ ] **完整工作流跑通一次**：Excel → 解析 → 字段映射触发 → CLI 确认 → YAML 更新 → git commit
- [ ] 从 v5.9.0-baseline 回滚可执行（用备份的 BACKUP_LOG.md 方法 A/B 验证一次）

---

**文档版本**: v1.0
**最后更新**: 2026-06-09
**下次更新**: 评审通过后冻结为 v1.0；如调整记 v1.1
