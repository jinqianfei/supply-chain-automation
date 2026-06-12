#!/bin/bash
# ============================================================
# AI建单助手 - 阿里云 OpenClaw 一键部署脚本
# 版本: v5.15.2
# 日期: 2026-06-12
#
# 使用方法:
#   1. 将迁移包和此脚本上传到阿里云服务器
#   2. chmod +x deploy_to_aliyun.sh
#   3. 编辑下方配置区（阿里云 RDS 连接信息）
#   4. bash deploy_to_aliyun.sh
# ============================================================

set -e

# ==================== 配置区（必须修改） ====================

# 阿里云 RDS 数据库配置
export DB_HOST="你的阿里云RDS地址"
export DB_PORT="5432"
export DB_NAME="neo"
export DB_USER="agenthub"
export DB_PASSWORD="你的数据库密码"

# OpenClaw 工作区路径
OPENCLAW_WORKSPACE="/root/openclaw-workspaces/ai-order"
# 如果 OpenClaw 用户不是 root，改为对应用户的家目录
# OPENCLAW_WORKSPACE="/home/username/openclaw-workspaces/ai-order"

# 迁移包路径（默认当前目录）
MIGRATION_PACKAGE="./ai-order-migration-v5.15.2-20260612.tar.gz"
SQL_FILE="./output/migration_export_20260612_131444.sql"

# ==================== 部署开始 ====================

echo "================================================"
echo "🚀 AI建单助手 阿里云部署 (v5.15.2)"
echo "================================================"
echo ""

# Step 1: 创建工作区
echo "📁 Step 1/6: 创建工作区..."
mkdir -p "$OPENCLAW_WORKSPACE"
cd "$OPENCLAW_WORKSPACE"
echo "  ✅ 工作区: $OPENCLAW_WORKSPACE"

# Step 2: 解压迁移包
echo ""
echo "📦 Step 2/6: 解压迁移包..."
if [ -f "$MIGRATION_PACKAGE" ]; then
    tar xzf "$MIGRATION_PACKAGE" --strip-components=0
    echo "  ✅ 解压完成"
elif [ -f "$(dirname $0)/../output/ai-order-migration-v5.15.2-20260612.tar.gz" ]; then
    tar xzf "$(dirname $0)/../output/ai-order-migration-v5.15.2-20260612.tar.gz" --strip-components=0
    echo "  ✅ 解压完成（从 output/ 找到）"
else
    echo "  ❌ 找不到迁移包，请确认路径: $MIGRATION_PACKAGE"
    exit 1
fi

# Step 3: 创建 .env 文件
echo ""
echo "🔐 Step 3/6: 创建 .env 配置..."
cat > "$OPENCLAW_WORKSPACE/.env" << EOF
# AI建单助手 数据库配置 (阿里云 RDS)
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
EOF
chmod 600 "$OPENCLAW_WORKSPACE/.env"
echo "  ✅ .env 已创建（权限 600）"

# Step 4: 导入数据库
echo ""
echo "🗄️  Step 4/6: 导入数据库到阿里云 RDS..."

# 查找 SQL 文件
if [ -f "$SQL_FILE" ]; then
    ACTUAL_SQL="$SQL_FILE"
elif [ -f "output/migration_export_20260612_131444.sql" ]; then
    ACTUAL_SQL="output/migration_export_20260612_131444.sql"
else
    # 查找最新的 migration_export SQL
    ACTUAL_SQL=$(ls -t output/migration_export_*.sql 2>/dev/null | head -1)
fi

if [ -n "$ACTUAL_SQL" ] && [ -f "$ACTUAL_SQL" ]; then
    echo "  SQL 文件: $ACTUAL_SQL"
    echo "  目标: $DB_HOST:$DB_PORT/$DB_NAME"
    
    # 测试连接
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" &>/dev/null; then
        echo "  ✅ 数据库连接成功"
        
        # 导入
        echo "  📥 导入中..."
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$ACTUAL_SQL" 2>&1 | tail -5
        
        # 验证
        TABLE_COUNT=$(PGPASSWORD="$DB_HOST" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'" 2>/dev/null | tr -d ' ')
        echo "  ✅ 导入完成（$TABLE_COUNT 张表）"
    else
        echo "  ⚠️  数据库连接失败，请检查配置"
        echo "  手动导入命令:"
        echo "    PGPASSWORD=\"$DB_PASSWORD\" psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $ACTUAL_SQL"
    fi
else
    echo "  ⚠️  找不到 SQL 文件，跳过数据库导入"
    echo "  请手动导入: psql -h <RDS地址> -U <用户> -d <数据库> -f <SQL文件>"
fi

# Step 5: 安装 Python 依赖
echo ""
echo "🐍 Step 5/6: 检查 Python 依赖..."
if command -v python3 &>/dev/null; then
    echo "  Python: $(python3 --version)"
    
    # 检查关键依赖
    MISSING_DEPS=""
    for pkg in psycopg2-binary openpyxl Pillow rapidfuzz pyyaml; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            # 特殊处理包名
            case $pkg in
                psycopg2-binary) pip_pkg="psycopg2-binary" ;;
                openpyxl) pip_pkg="openpyxl" ;;
                Pillow) pip_pkg="Pillow" ;;
                rapidfuzz) pip_pkg="rapidfuzz" ;;
                pyyaml) pip_pkg="PyYAML" ;;
            esac
            MISSING_DEPS="$MISSING_DEPS $pip_pkg"
        fi
    done
    
    if [ -n "$MISSING_DEPS" ]; then
        echo "  安装缺失依赖: $MISSING_DEPS"
        pip3 install $MISSING_DEPS 2>/dev/null || pip install $MISSING_DEPS
    else
        echo "  ✅ 所有依赖已就绪"
    fi
else
    echo "  ⚠️  未找到 Python3，请先安装"
fi

# Step 6: 验证部署
echo ""
echo "🔍 Step 6/6: 验证部署..."

# 检查核心文件
CHECK_FILES=(
    "skills/skill_order_to_huading_template/__init__.py"
    "skills/skill_order_to_huading_template/VERSION"
    "skills/skill_order_to_huading_template/tools/_sku_mapper.py"
    "skills/skill_order_to_huading_template/tools/_store_matcher.py"
    "AGENTS.md"
    "SOUL.md"
    "IDENTITY.md"
    "TOOLS.md"
    "MEMORY.md"
    ".env"
)

ALL_OK=true
for f in "${CHECK_FILES[@]}"; do
    if [ -f "$f" ]; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f 缺失"
        ALL_OK=false
    fi
done

# 显示版本号
if [ -f "skills/skill_order_to_huading_template/VERSION" ]; then
    VERSION=$(cat skills/skill_order_to_huading_template/VERSION)
    echo ""
    echo "  📌 Skill 版本: $VERSION"
fi

# ==================== 部署结果 ====================

echo ""
echo "================================================"
if $ALL_OK; then
    echo "✅ 部署完成！"
else
    echo "⚠️  部署完成（有文件缺失，请检查上方列表）"
fi
echo "================================================"
echo ""
echo "📋 后续步骤："
echo "  1. 重启 OpenClaw: openclaw gateway restart"
echo "  2. 在对话中测试: 发送一个测试订单"
echo "  3. 运行 CI 回归: bash scripts/ci_regression.sh"
echo ""
echo "🔧 如需修改数据库配置:"
echo "  编辑 $OPENCLAW_WORKSPACE/.env"
echo ""
echo "📁 工作区: $OPENCLAW_WORKSPACE"
echo "================================================"
