#!/bin/bash
# OpenClaw EC2 部署脚本
# 使用方法: bash deploy_openclaw.sh

set -e

EC2_HOST="47.129.210.34"
EC2_USER="ec2-user"
KEY_FILE="~/.ssh/id_rsa"  # 或你的 SSH 密钥路径

echo "===== 连接到 EC2 并安装 OpenClaw ====="

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$EC2_USER@$EC2_HOST" << 'EOF'
# 1. 安装 Node.js 20.x
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo yum install -y nodejs

# 2. 安装 OpenClaw
curl -s https://install.openclaw.ai | sh

# 3. 配置 WebChat 认证
openclaw config set gateway.auth.mode password
openclaw config set gateway.auth.password "AiOrder2026!"

# 4. 配置绑定到所有网络接口
openclaw config set gateway.bind "0.0.0.0"

# 5. 创建工作目录
mkdir -p /home/ec2-user/ai-order

echo "===== OpenClaw 安装完成 ====="
openclaw --version
EOF

echo ""
echo "===== 部署完成 ====="
echo "EC2 地址: $EC2_HOST"
echo "WebChat 访问: http://$EC2_HOST:18789/chat"
echo "Control UI: http://$EC2_HOST:18789/"
echo ""
echo "下一步: 运行 sync_to_ec2.sh 同步 Skill"