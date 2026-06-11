#!/bin/bash
# EC2 上配置 OpenClaw Agent（SSH登录后运行此脚本）
# 在 EC2 上执行

AGENT_NAME="ai-order"
SKILL_DIR="/home/ec2-user/ai-order/skills/skill_order_to_huading_template"

echo "===== 配置 OpenClaw Agent ====="

# 1. 配置 agent
openclaw agents create --name "$AGENT_NAME" \
  --workspace "/home/ec2-user/ai-order" \
  --model "minimax-portal/MiniMax-M2.7" 2>/dev/null || \
  openclaw agents update --name "$AGENT_NAME" \
  --workspace "/home/ec2-user/ai-order"

# 2. 配置 Gateway
openclaw config set gateway.agent.default "$AGENT_NAME"

# 3. 配置 .env 文件
cat > /home/ec2-user/ai-order/.env << 'EOF'
DB_HOST=agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=neo
DB_USER=agenthub
DB_PASSWORD=Agenthub_RDS_2026!c9fce7060773
EOF

echo ""
echo "===== 启动 Gateway ====="
openclaw gateway start &
sleep 3

echo ""
echo "===== 验证 WebChat ====="
curl -s http://localhost:18789/chat | head -5 || echo "WebChat 可能需要一些时间启动"

echo ""
echo "===== 配置完成 ====="
echo "WebChat: http://47.129.210.34:18789/chat"
echo "密码: AiOrder2026!"