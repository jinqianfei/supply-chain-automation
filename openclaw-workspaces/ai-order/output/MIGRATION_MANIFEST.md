# AI建单助手 迁移清单

生成时间: 2026-06-11 16:40 GMT+8
版本: skill_order_to_huading_template v5.15.1

## 1. Skill 核心代码 (必须)

| 路径 | 说明 | 文件数 |
|------|------|--------|
| `skills/skill_order_to_huading_template/__init__.py` | 主入口 (v5.15.1) | 1 |
| `skills/skill_order_to_huading_template/tools/` | 5 个核心工具 | 6 |
| `skills/skill_order_to_huading_template/db/` | 数据库连接层 | 5 |
| `skills/skill_order_to_huading_template/config/` | 配置文件 | 4 |
| `skills/skill_order_to_huading_template/field_mapping/` | 字段映射规则 | 8 |
| `skills/skill_order_to_huading_template/events/` | 事件总线 (自学习) | 2 |
| `skills/skill_order_to_huading_template/learn/` | 自学习模块 | 12 |
| `skills/skill_order_to_huading_template/SKILL.md` | Skill 文档 | 1 |
| `skills/skill_order_to_huading_template/VERSION` | 版本号 | 1 |
| `skills/skill_order_to_huading_template/CHANGELOG.md` | 变更日志 | 1 |

## 2. 自学习系统

| 路径 | 说明 |
|------|------|
| `events/bus.py` | EventBus 事件总线 (40行) |
| `learn/collector.py` | 反馈采集器 (370行, 10 个事件订阅) |
| `learn/adapter.py` | 学习数据适配器 |
| `learn/schema.sql` | 自学习表结构 (order_feedback, order_corrections, layer_success_rate) |
| `learn/llm/` | LLM 提供者层 (OpenAI/兼容/OpenClaw) |
| `learn/ADAPTIVE_LEARNING_METHOD_B.md` | 自学习方法论文档 |

## 3. CI 回归测试脚本

| 路径 | 说明 |
|------|------|
| `scripts/ci_regression.sh` | CI 入口 |
| `scripts/test_sku_mapper_regression.py` | SKU 映射回归 (53 用例) |
| `scripts/test_mapping_accuracy.py` | 准确率指标 (5 维度, 82 用例) |
| `scripts/test_event_pipeline.py` | 事件管道测试 |
| `scripts/test_execute_confirmation_flow.py` | 门店确认流程测试 |
| `scripts/test_execute_import_fallback.py` | import fallback 测试 |
| `scripts/test_order_parser_excel_header_detail.py` | Excel 解析测试 |
| `scripts/test_order_parser_text_fallback.py` | 文本解析测试 |
| `scripts/version_check.sh` | 版本号一致性检查 |

## 4. 工作区配置文件 (必须)

| 文件 | 说明 |
|------|------|
| `AGENTS.md` | Agent 角色定义 |
| `SOUL.md` | Agent 性格/风格 |
| `IDENTITY.md` | 身份配置 (数据库/货主/SKU逻辑) |
| `USER.md` | 用户信息 |
| `TOOLS.md` | 工具配置说明 |
| `MEMORY.md` | 记忆文件 (核心上下文) |
| `HEARTBEAT.md` | 心跳配置 |

## 5. 记忆模块

| 路径 | 说明 |
|------|------|
| `memory/MEMORY_SYSTEM_PLAN.md` | 记忆系统方案 (5层架构) |
| `memory/SESSION_START_PROTOCOL.md` | 启动协议 |
| `memory/SESSION_END_PROTOCOL.md` | 结束协议 |
| `memory/PENDING_PROTOCOL.md` | 待办协议 |
| `memory/projects/` | 项目记忆 |
| `memory/2026-*.md` | 日志 (6-8 到 6-11) |

## 6. 文档

| 路径 | 说明 |
|------|------|
| `docs/阿里云迁移方案.md` | 迁移方案文档 |
| `docs/SELF_LEARNING_MODULE_PLAN.md` | 自学习模块方案 |
| `docs/Skill测评通用方法论.md` | 测评方法论 |
| `docs/test_data/` | 测试数据集 (A/B/C/D set) |

## 7. 运维脚本

| 路径 | 说明 |
|------|------|
| `scripts/daily_wrap.sh` | 每日日结 |
| `scripts/startup_check.py` | 启动自检 |
| `scripts/check_continuity.sh` | 断档检查 |
| `launchd/*.plist` | macOS 定时任务 (需改为阿里云 cron) |

## 8. 环境变量

| 变量 | 说明 | 备注 |
|------|------|------|
| `DB_HOST` | AWS RDS 地址 | 迁移后改为阿里云 RDS |
| `DB_PORT` | 5432 | |
| `DB_NAME` | neo | |
| `DB_USER` | agenthub | |
| `DB_PASSWORD` | 密码 | ⚠️ 通过密钥管理 |

## 9. 数据库

- 数据库: AWS RDS PostgreSQL (agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com)
- 8 张有数据的表, 共 ~8000 条
- 自学习表: order_feedback (19条), order_corrections (0), layer_success_rate (14)
- **已有导出**: `output/数据库全量导出_20260611.xlsx`

## 不迁移

- `backups/` — 历史备份
- `.git/` objects — git 内部
- `shareable/` — 分享版 (旧)
- `test_output*` — 旧测试输出
- `skills/skill_openclaw_test/` — 测试 skill (不需要)
- `skills/skill_openclaw_deploy/` — 部署 skill (不需要)
- `skills/skill_skill_monitor/` — 监控 skill (不需要)
- `skills/skill_operation_monitor/` / `skills/skill_ops_monitor/` — 运营监控 (不需要)

