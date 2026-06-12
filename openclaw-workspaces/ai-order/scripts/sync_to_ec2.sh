#!/bin/bash
# 同步 Skill 到 EC2 (AI-Order)
# 使用方法: bash sync_to_ec2.sh [sku_mapper_only]
#   不带参数：全量同步 skills 目录
#   带 sku_mapper_only：只同步 sku_mapper.py

EC2_HOST="13.212.17.85"
EC2_USER="ec2-user"
EC2_KEY="~/.ssh/openclaw-ec2.pem"
LOCAL_DIR="${AI_ORDER_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REMOTE_DIR="/home/ec2-user/ai-order"

SSH_CMD="ssh -o StrictHostKeyChecking=no -i $EC2_KEY"

echo "===== 同步 Skill 到 EC2 (AI-Order) ====="
echo "Host: $EC2_HOST"
echo ""

if [ "$1" = "sku_mapper_only" ]; then
    echo ">>> 只同步 sku_mapper.py"
    rsync -avz \
      -e "$SSH_CMD" \
      "$LOCAL_DIR/skills/skill_order_to_huading_template/tools/sku_mapper.py" \
      "$EC2_USER@$EC2_HOST:$REMOTE_DIR/skills/skill_order_to_huading_template/tools/sku_mapper.py"
    echo "Done."
else
    echo ">>> 全量同步 skills 目录"
    rsync -avz \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude '.DS_Store' \
      --exclude 'node_modules' \
      --exclude 'skills/skill_order_to_huading_template/__pycache__' \
      --exclude 'skills/skill_order_to_huading_template/output/*' \
      --exclude 'output/*' \
      -e "$SSH_CMD" \
      "$LOCAL_DIR/skills/" \
      "$EC2_USER@$EC2_HOST:$REMOTE_DIR/skills/"

    echo ""
    echo "===== 同步完成 ====="
    echo "测试连接: $SSH_CMD $EC2_USER@$EC2_HOST"
fi