# AI Order 迁移方案 v3：Mac → 阿里云 ECS（最终版）

> **日期**：2026-06-11
> **状态**：已确认，待执行

---

## 环境确认

| 项 | 值 |
|---|-----|
| 服务器 OS | Ubuntu |
| 数据库 | 阿里云 RDS PostgreSQL |
| IM 渠道 | 钉钉机器人（已创建） |
| LLM | 通义千问 API（白名单可访问） |
| Git | 内网 git 私服（可用） |
| 服务器访问 | 内网登录（无 SSH 隧道） |
| Supermemory | 内网可能不通 → 本地化 |

---

## Step 1：Mac 上准备（打包 + 推 git）

```bash
# 1.1 推送到内网 git 私服
cd /Users/jinqianfei/openclaw-workspaces/ai-order

# 初始化 git（如果还没有独立仓库）
git init
git remote add origin http://内网git私服地址/ai-order.git

# 添加 .gitignore
cat > .gitignore << 'EOF'
.DS_Store
.env
.env.bak.*
.memory_index/
.openclaw/
backups/
output/
test_output*/
preview.jpg
excel
launchd/
shareable/
skills/skill_openclaw_deploy/
skills/skill_openclaw_test/
skills/skill_operation_monitor/
skills/skill_ops_monitor/
skills/skill_skill_monitor/
skills/docs/
skills/.DS_Store
__pycache__/
*.pyc
EOF

# 提交
git add .
git commit -m "init: ai-order workspace migration"
git push -u origin main

# 1.2 导出数据库（AWS RDS）
PGPASSWORD=*** pg_dump \
  -h agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com \
  -p 5432 -U agenthub -d neo \
  --no-owner --no-privileges > /tmp/neo_full_dump.sql
```

---

## Step 2：服务器上环境准备

```bash
# 2.1 系统依赖
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

# 2.2 Node.js（OpenClaw 需要）
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 2.3 OpenClaw
npm install -g openclaw

# 2.4 Python 依赖
pip3 install psycopg2-binary pandas openpyxl PyYAML requests

# 2.5 创建工作区
mkdir -p ~/openclaw-workspaces/ai-order
```

---

## Step 3：拉代码 + 恢复数据库

```bash
# 3.1 从内网 git 拉代码
cd ~/openclaw-workspaces/ai-order
git clone http://内网git私服地址/ai-order.git .

# 3.2 恢复数据库到阿里云 RDS
# 先从 Mac 传 dump 文件到服务器（内网文件服务器 / scp 跳板机）
psql -h 阿里云RDS内网地址 -p 5432 -U agenthub -d neo < /tmp/neo_full_dump.sql

# 3.3 验证 DB
python3 -c "
import psycopg2
conn = psycopg2.connect(host='阿里云RDS内网地址', port=5432, database='neo', user='agenthub', password=***
cur = conn.cursor()
cur.execute('SELECT count(*) FROM product_sku')
print(f'DB OK: {cur.fetchone()[0]} SKUs')
cur.execute('SELECT count(*) FROM store_list')
print(f'Stores: {cur.fetchone()[0]}')
conn.close()
"
```

---

## Step 4：配置环境变量

```bash
cd ~/openclaw-workspaces/ai-order
cat > .env << 'EOF'
# 阿里云 RDS PostgreSQL（内网地址）
DB_HOST=rm-xxx.pgsql.rds.aliyuncs.com
DB_PORT=5432
DB_NAME=neo
DB_USER=agenthub
DB_PASSWORD=***

# 通义千问 API（白名单已开）
QWEN_API_KEY=***

# 钉钉机器人（已创建）
DINGTALK_ROBOT_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=***
DINGTALK_ROBOT_SECRET=***

# 内网 git 私服（如果需要）
GIT_PRIVATE_REPO=http://内网git私服地址/ai-order.git
EOF
```

---

## Step 5：配置 OpenClaw + 钉钉

```bash
# 5.1 初始化 OpenClaw
openclaw init

# 5.2 创建 ai-order agent
openclaw agent create ai-order

# 5.3 配置钉钉 channel
# 在 OpenClaw 配置中添加钉钉机器人信息
# App Key / App Secret / Robot Code 从钉钉开放平台获取

# 5.4 配置模型
openclaw config set agents.defaults.primaryModel "qwen-portal/qwen3.7-max"

# 5.5 配置 workspace
openclaw agent config ai-order --workspace ~/openclaw-workspaces/ai-order
```

---

## Step 6：定时任务（cron）

```bash
crontab -e

# 添加：
# 每 3 分钟 auto git（如果有本地 git）
*/3 * * * * cd ~/openclaw-workspaces/ai-order && git add -A && git commit -m "auto" --quiet 2>/dev/null

# 每天 10:00 别名表汇总（独立推送）
0 10 * * * cd ~/openclaw-workspaces/ai-order && python3 scripts/daily_alias_summary.py >> /tmp/alias_summary.log 2>&1

# 每天 17:00 日报
0 17 * * * cd ~/openclaw-workspaces/ai-order && bash scripts/daily_wrap.sh >> /tmp/daily_wrap.log 2>&1

# 每天 09:00 断档检测
0 9 * * * cd ~/openclaw-workspaces/ai-order && bash scripts/check_continuity.sh >> /tmp/check_continuity.log 2>&1
```

---

## Step 7：验证

```bash
# 7.1 启动 OpenClaw
openclaw gateway start

# 7.2 检查状态
openclaw status

# 7.3 钉钉发消息测试
# 发 "你好" → 看 AI 是否回复

# 7.4 跑 CI 回归
cd ~/openclaw-workspaces/ai-order
bash skills/skill_order_to_huading_template/scripts/ci_regression.sh
# 期望：8/8 全过

# 7.5 跑端到端测试
# 用测试订单 Excel 发钉钉，看完整流程
```

---

## Checklist

```
━━━ Mac 准备 ━━━
□ .gitignore 配置
□ git push 到内网私服
□ pg_dump 导出 AWS RDS 数据
□ dump 文件传到服务器

━━━ 服务器环境 ━━━
□ apt install python3/nodejs/git
□ npm install -g openclaw
□ pip3 install 依赖
□ mkdir workspace

━━━ 代码 + 数据 ━━━
□ git clone 到服务器
□ psql 恢复数据库
□ 验证 DB 连通

━━━ 配置 ━━━
□ .env 文件（阿里云 RDS + 千问 API + 钉钉）
□ openclaw init + agent create
□ 钉钉 channel 配置
□ 模型配置

━━━ 定时任务 ━━━
□ crontab 配置

━━━ 验证 ━━━
□ openclaw gateway start
□ 钉钉发消息测试
□ CI 回归 8/8 通过
□ 端到端测试
```

---

*AI建单助手 | 2026-06-11 14:53 GMT+8*
