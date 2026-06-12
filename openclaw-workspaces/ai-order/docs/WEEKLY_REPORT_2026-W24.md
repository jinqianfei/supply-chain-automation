# AI建单助手 周报（2026年第24周：6/8 ~ 6/12）

> **汇报人**：AI建单助手
> **汇报对象**：金姐（金倩菲）
> **Skill 版本**：v5.8.0 → **v5.15.2**（本周 8 个版本迭代）

---

## 一、本周核心成果

### 1. 订单映射 Skill 升级（v5.8 → v5.15.2）

| 版本 | 日期 | 核心变更 |
|------|------|---------|
| v5.9.0 | 6-08 | 事件总线 + 反馈采集器（自学习 Phase 1） |
| v5.10.0 | 6-08 | `__getattribute__` 技术锁（防止 AI 绕过主入口） |
| v5.11.0 | 6-10 | LLM Provider 配置化重构（4 种 provider + 故障回退） |
| v5.11.1 | 6-10 | 硬编码清理 + quantity 透传 bug 修复 |
| v5.11.2 | 6-10 | 31 字段 + 表名常量统一到 yaml |
| v5.12.0 | 6-10 | P1 bug 修复：多门店 + 单 confirmed_store 正确处理 |
| v5.13.3 | 6-11 | 果糖末尾孤立分隔符修复 |
| v5.14.0 | 6-11 | 单位匹配逻辑（_compute_match_score + _select_unique_best） |
| v5.15.0~1 | 6-11 | 自学习 6 个缺失 emit 补齐 + 手机号匹配增强 |
| **v5.15.2** | **6-12** | **store_corrected 误触发修复 + 硬编码全修** |

**端到端准确率**：85/85 = **100%**（CI 53 + D set 20 + 洪洪通 1 + 天津仓 11）

### 2. 自学习模块建设（从 0 到闭环）

| 层级 | 状态 | 本周完成 |
|------|------|---------|
| L1 采集层 | ✅ | EventBus 10 事件全覆盖、3 张 DB 表、submitted_by/corrected_by 列 |
| L2 分析层 | ✅ | analyze_learning_data.py、daily_alias_summary.py、阈值配置化（analysis_config.yaml） |
| L3 改进层 | ✅ 核心 | yaml 别名表 + 字段别名表 + 加载逻辑（内容等数据积累） |
| L4 验证层 | ✅ | CI 回归测试、history_replay.py、accuracy_comparison.py |
| L5 通知机制 | ✅ | notification_sender.py、launchd 定时任务 × 3 |

**关键修复**：
- 发现 collector 只 emit 4/10 事件（覆盖率 40%），补齐至 100%
- 发现 store_corrected 多门店误触发 bug，修复为对比逻辑

### 3. 记忆系统建设（5 层架构 + 全部修复）

| 层级 | 状态 | 本周完成 |
|------|------|---------|
| L1 触发层 | ✅ | version_check.sh、daily_wrap.sh、check_continuity.sh、startup_check.py |
| L2 协议层 | ✅ | SESSION_START/END/PENDING_PROTOCOL、补 6-11/6-12 session 日志 |
| L3 索引层 | ✅ | reindex_memory.py 重建索引（145 文件 / 13,804 关键词） |
| L4 真相源 | ✅ | 统一根目录 MEMORY.md 为唯一手账、PROJECT.md/PENDING.md 更新 |
| L5 决策层 | ✅ | weekly_archive.sh + monthly_review.sh（新写）、memory/archive/ |

### 4. 代码质量治理

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| Python 硬编码路径 | 12 处 `/Users/jinqianfei/...` | **0 处**（全部 `_detect_workspace()`） |
| Shell 硬编码路径 | 5 处 | **0 处**（`$AI_ORDER_WORKSPACE` 环境变量） |
| 版本号不一致 | 4 处（SKILL.md/AGENTS.md/TOOLS.md/__init__.py 写 5.15.1） | **8/8 一致**（version_check 通过） |
| shareable/ 镜像 | 停在 v5.11.1（差 4 个版本） | **同步到 v5.15.2** |
| SQL 类型错误 | `ROUND(double precision, int)` 报错 | **FLOAT → NUMERIC + 类型转换** |
| 方案文档标记 | 多处"待开发"但实际已完成 | **章节标题与 Phase 列表一致** |

---

## 二、数据库变更

| 变更 | 类型 | 说明 |
|------|------|------|
| `order_feedback` 新增 `submitted_by TEXT` | ALTER | 追踪订单提交人 |
| `order_corrections` 新增 `corrected_by TEXT` | ALTER | 追踪纠正人 |
| `layer_success_rate.success_rate` FLOAT → NUMERIC(6,4) | ALTER | 修复 ROUND 类型错误 |
| `layer_success_rate.avg_match_score` FLOAT → NUMERIC(10,4) | ALTER | 同上 |
| `v_layer_success_rate` 视图重建 | VIEW | 配合列类型变更 |

---

## 三、新增文件清单

| 文件 | 用途 |
|------|------|
| `config/analysis_config.yaml` | 自学习分析阈值配置（8 项参数） |
| `config/notification_config.yaml` | 通知推送配置（环境变量化） |
| `scripts/analyze_learning_data.py` | 自学习分析脚本 |
| `scripts/daily_alias_summary.py` | 每日别名汇总 |
| `scripts/notification_sender.py` | 通知发送（飞书/钉钉） |
| `scripts/weekly_archive.sh` | 周归档（14+ 天日志） |
| `scripts/monthly_review.sh` | 月度复盘报告 |
| `skills/.../scripts/history_replay.py` | 历史订单回放 |
| `skills/.../scripts/accuracy_comparison.py` | 准确率版本对比 |
| `skills/.../field_mapping/rules/sku_aliases_auto.yaml` | SKU 别名表（自学习） |
| `skills/.../field_mapping/rules/field_aliases_auto.yaml` | 字段别名表（自学习） |
| `memory/archive/` | 日志归档目录 |
| `docs/SELF_LEARNING_MODULE_PLAN.md` | 自学习完整方案 |
| `memory/MEMORY_SYSTEM_PLAN.md` | 记忆系统方案 v2.0 |

---

## 四、Git 提交统计

| 仓库 | 本周 commit 数 | 最新版本 |
|------|--------------|---------|
| 工作区（supply-chain-automation） | 30+ | `a47e6ed` |
| Skill（skill-order-to-huading-template） | 11 | `e4cafb5` |
| **总计** | **41+** | — |

两个仓库均已推送到 GitHub（HTTPS）。

---

## 五、产出物

| 产出 | 格式 | 说明 |
|------|------|------|
| 自学习模块打包 | zip（77KB，31 文件） | 全部文件零硬编码 |
| 记忆模块打包 | zip（318KB，37 文件） | 含方案+脚本+数据+索引 |
| 完整工作区打包 | zip（1.4MB，388 文件） | 三模块统一迁移包 |
| 飞书文档 | 在线 | 自学习方案、记忆方案、迭代方案 |

---

## 六、遗留事项

| 优先级 | 事项 | 状态 |
|--------|------|------|
| 🟡 P2 | 自学习闭环需要数据积累才能触发分析→改进 | 等待真实订单纠正数据 |
| 🟡 P2 | 记忆模块 Phase 4（自治：飞轮自动推进） | 计划中 |
| 🟡 P2 | `mapping_table` 字段返回为空 | 已记录，待修复 |
| 🟡 P2 | 数据库 MySQL 兼容性改造 | 方案已定，待触发 |
| ✅ 已完成 | AWS → 阿里云迁移 | 6-12 已完成迁移 |

---

## 七、下周计划

1. **继续订单处理**：积累真实纠正数据，推动自学习闭环转起来
2. **自学习阈值调优**：等 order_corrections 积累 ≥ 10 条后跑分析
3. **CI 自动化**：考虑把回归测试集成到 git hook 或定时任务

---

*AI建单助手 | 2026-06-12 11:50 GMT+8*
