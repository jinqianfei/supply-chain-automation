# 阿里云 OpenClaw 迁移操作手册

> 版本: v5.15.2 | 日期: 2026-06-12 | 作者: AI建单助手

## 迁移概览

| 项目 | 说明 |
|------|------|
| 迁移内容 | 订单映射 Skill + 自学习模块 + 记忆系统 |
| 源环境 | macOS (本地) + AWS RDS (新加坡) |
| 目标环境 | 阿里云 ECS + 阿里云 RDS |
| 预计耗时 | 30-60 分钟 |

---

## 📦 迁移包内容

**文件**: `ai-order-migration-v5.15.2-20260612.tar.gz` (859KB, 198个文件)

| 类别 | 路径 | 文件数 | 说明 |
|------|------|--------|------|
| Skill 核心 | `skills/skill_order_to_huading_template/` | ~80 | v5.15.2 主代码 + 工具 + 配置 |
| 自学习模块 | `skills/.../learn/` | ~15 | 反馈采集 + 适配器 + LLM层 |
| 事件总线 | `skills/.../events/` | 2 | EventBus |
| CI 测试 | `scripts/` | ~26 | 回归测试 + 准确率验证 |
| 记忆模块 | `memory/` | ~17 | 会话协议 + 项目记忆 + 日志 |
| 文档 | `docs/` | ~34 | 方法论 + 测评 + 方案 |
| 工作区配置 | 根目录 | 7 | AGENTS/SOUL/IDENTITY/USER/TOOLS/MEMORY/HEARTBEAT |
| 数据库导出 | `output/` | 2 | SQL + JSON 统计 |

---

## 🚀 迁移步骤

### Step 1: 传输迁移包到阿里云

```bash
# 方式 A: scp 直传
scp output/ai-order-migration-v5.15.2-20260612.tar.gz root@<阿里云ECS-IP>:/tmp/

# 方式 B: 通过 OSS 中转
# 1. 上传到 OSS bucket
# 2. 在 ECS 上 ossutil cp oss://bucket/path/file.tar.gz /tmp/
```

### Step 2: 在阿里云服务器上部署

```bash
# SSH 登录阿里云
ssh root@<阿里云ECS-IP>

# 进入 OpenClaw 工作区
cd /root/openclaw-workspaces/ai-order   # 或你的工作区路径

# 解压迁移包
tar xzf /tmp/ai-order-migration-v5.15.2-20260612.tar.gz

# 创建 .env 文件
cat > .env << 'EOF'
DB_HOST=<阿里云RDS地址>
DB_PORT=5432
DB_NAME=neo
DB_USER=agenthub
DB_PASSWORD=<数据库密码>
EOF
chmod 600 .env
```

### Step 3: 导入数据库

```bash
# 测试数据库连接
PGPASSWORD="<密码>" psql -h <RDS地址> -p 5432 -U agenthub -d neo -c "SELECT 1"

# 导入数据
PGPASSWORD="<密码>" psql -h <RDS地址> -p 5432 -U agenthub -d neo -f output/migration_export_20260612_131444.sql

# 验证导入结果
PGPASSWORD="<密码>" psql -h <RDS地址> -p 5432 -U agenthub -d neo -c "
SELECT table_name, 
       (xpath('/row/cnt/text()', xml_count))[1]::text::int as row_count
FROM (
    SELECT table_name, 
           query_to_xml(format('SELECT count(*) as cnt FROM %I', table_name), false, true, '') as xml_count
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name
) t;
"
```

**预期数据量**:

| 核心表 | 行数 |
|--------|------|
| product_sku | 1,832 |
| product_name_alias | 30 |
| store_list | 3,327 |
| warehouse_code_mapping | 113 |
| customer | 873 |
| product | 1,768 |
| order_feedback | 19 |
| layer_success_rate | 14 |
| **总计** | **7,976** |

### Step 4: 安装 Python 依赖

```bash
pip3 install psycopg2-binary openpyxl Pillow rapidfuzz PyYAML requests
```

### Step 5: 更新文档中的数据库配置

迁移包中的 `IDENTITY.md` / `TOOLS.md` / `AGENTS.md` 仍指向 AWS RDS。需要更新：

```bash
# 替换所有文档中的 AWS RDS 地址为阿里云 RDS 地址
find . -name "*.md" -exec sed -i 's/agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com/<阿里云RDS地址>/g' {} +
```

### Step 6: 重启 OpenClaw 并验证

```bash
# 重启 OpenClaw
openclaw gateway restart

# 或通过 systemd
systemctl restart openclaw
```

### Step 7: 运行验证测试

```bash
# 版本一致性检查
bash skills/skill_order_to_huading_template/scripts/version_check.sh

# CI 回归测试（需要 DB 连接正常）
cd skills/skill_order_to_huading_template
bash scripts/ci_regression.sh

# 准确率指标测试
python3 scripts/test_mapping_accuracy.py
```

---

## ⚠️ 注意事项

### 数据库密码
- `.env` 文件权限必须设为 600（仅所有者可读写）
- 不要在代码或文档中明文写入密码
- 建议阿里云 RDS 使用不同于 AWS 的密码

### Supermemory 云端记忆
- Supermemory 是 OpenClaw 内置的云端服务
- 只要阿里云 OpenClaw 实例配置了相同的账号，记忆会自动同步
- `containerTag` 配置（`ai_order` / `ai_kefu` / `supply_chain` / `openclaw_main`）需要保持一致
- 迁移后可用 `supermemory_search` 验证数据可访问

### 飞书通知
- 如果自学习模块的飞书通知需要发送到相同的群，webhook token 已在配置文件中
- 如果需要新的群，需要更新 `config/notification_config.yaml`

### 定时任务
- 本地使用 macOS launchd，阿里云需改为 cron 或 systemd timer
- 参考 `scripts/` 下的定时脚本，用 crontab 配置：

```bash
# 编辑 crontab
crontab -e

# 示例: 每天 10:00 跑日结
0 10 * * * cd /root/openclaw-workspaces/ai-order && bash scripts/daily_wrap.sh >> /var/log/ai-order-daily.log 2>&1

# 示例: 每 6 小时跑自学习分析
0 */6 * * * cd /root/openclaw-workspaces/ai-order && python3 scripts/analyze_learning_data.py >> /var/log/ai-order-learning.log 2>&1
```

---

## 🔧 故障排查

| 问题 | 排查 |
|------|------|
| 数据库连接失败 | 检查阿里云 RDS 安全组是否放通 ECS 的 IP |
| Python import 报错 | `pip3 install -r requirements.txt` 或逐个安装 |
| Skill 找不到 | 检查 `skills/skill_order_to_huading_template/__init__.py` 是否存在 |
| 门店匹配全部失败 | 检查 `store_list` 表是否有数据（3327条） |
| SKU 匹配全部失败 | 检查 `product_sku` 表是否有数据（1832条） |
| OpenClaw 无法启动 | `openclaw gateway status` 查看日志 |
| Supermemory 无数据 | 确认 OpenClaw 配置中的 Supermemory 凭证正确 |

---

## 📊 验证 Checklist

- [ ] `.env` 文件已创建且包含正确的阿里云 RDS 连接信息
- [ ] 数据库导入完成，核心表行数正确
- [ ] `version_check.sh` 通过
- [ ] CI 回归测试通过（53/53）
- [ ] 准确率指标测试通过（82/82 = 100%）
- [ ] OpenClaw 重启成功
- [ ] 对话中发送测试订单能正常处理
- [ ] Supermemory 记忆可访问
- [ ] 飞书通知正常（如果启用）
- [ ] 定时任务已配置（crontab）

---

## 📁 关键文件清单

| 文件 | 用途 |
|------|------|
| `.env` | 数据库连接配置 |
| `AGENTS.md` | Agent 角色定义 |
| `SOUL.md` | Agent 性格/风格 |
| `IDENTITY.md` | 身份配置（数据库/货主/SKU逻辑）|
| `TOOLS.md` | 工具配置说明 |
| `MEMORY.md` | 核心记忆上下文 |
| `skills/skill_order_to_huading_template/VERSION` | 当前版本号 |
| `scripts/ci_regression.sh` | CI 回归测试入口 |
| `scripts/deploy_to_aliyun.sh` | 一键部署脚本 |

---

*最后更新: 2026-06-12 13:15 GMT+8*
