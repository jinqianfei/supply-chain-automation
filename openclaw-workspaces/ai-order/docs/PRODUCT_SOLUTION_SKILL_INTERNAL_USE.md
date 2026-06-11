# Skill 内部使用改造方案

**版本**: v1.0  
**日期**: 2026-06-08  
**Agent**: product-solution

---

## 1. 需求分析

### 1.1 背景

`skill_order_to_huading_template` 是将客户订单转换为华鼎出库单模板的技能（当前版本 v5.9.0）。数据库使用 **AWS RDS PostgreSQL**：

- **Host**: `agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com`
- **Port**: `5432`
- **Database**: `neo`
- **User**: `agenthub`

### 1.2 当前状态

| 项目 | 状态 |
|------|------|
| Skill 版本 | v5.9.0 |
| 数据库 | AWS RDS PostgreSQL |
| 多租户 | 不考虑（仅内部使用） |
| 权限控制 | 无（所有用户平等） |
| 部署方式 | 手动复制文件 |
| 数据初始化 | 手动导入 |

### 1.3 改造目标

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P0 | 权限控制 | 读/写权限分离 |
| P0 | 数据库配置化 | 用户自定义连接 |
| P1 | 部署包封装 | 一键安装 + 文档 |
| P1 | 数据初始化 | 预置基础数据 |

---

## 2. 功能详细设计

### 2.1 权限控制

#### 目标
- **读权限**：所有授权用户可读取基础数据（商品/门店）
- **写权限**：仅管理员可修改映射规则

#### 实现方案

**方案 A：应用层权限（推荐）**

```python
# 在 skill 内部实现权限检查
class Permission:
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

class PermissionChecker:
    def __init__(self, user_role: str = "user"):
        self.role = user_role
    
    def can_read(self) -> bool:
        return self.role in ["user", "admin"]
    
    def can_write(self) -> bool:
        return self.role == "admin"
```

**数据库表设计**

```sql
-- 用户权限表
CREATE TABLE skill_permissions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 权限操作日志
CREATE TABLE permission_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    target_table VARCHAR(50),
    target_id VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 用户角色

| 角色 | 读 | 写 | 管理 |
|------|----|----|------|
| user | ✅ | ❌ | ❌ |
| admin | ✅ | ✅ | ✅ |

---

### 2.2 数据库配置化

#### 目标
- 用户首次使用时可自定义配置数据库连接
- 支持环境变量、.env 文件、参数传入三种方式

#### 实现方案

```python
class OrderToHuadingTemplate:
    def __init__(self, db_config: Dict[str, Any] = None, ...):
        """
        数据库配置（支持3种方式，优先级从高到低）
        
        1. 显式传入 db_config 参数
        2. 环境变量：DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
        3. .env 文件：读取项目根目录的 .env
        """
        self.db_config = self._resolve_db_config(db_config)
    
    def _resolve_db_config(self, db_config: Dict = None) -> Dict:
        if db_config and db_config.get("host"):
            return db_config
        
        # 从环境变量读取
        env_config = {
            "host": os.getenv("DB_HOST"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME", "neo"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD")
        }
        if all([env_config.get("host"), env_config.get("user")]):
            return env_config
        
        # 从 .env 文件读取
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            return self._load_from_env_file(env_path)
        
        # 抛出异常
        raise ValueError("数据库配置未找到，请传入 db_config 参数或设置环境变量")
    
    def _load_from_env_file(self, env_path: str) -> Dict:
        config = {"host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT", "5432")), "database": os.getenv("DB_NAME", "neo")}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k in config:
                        config[k] = v.strip()
        return config
```

#### 配置引导

```python
# 用户首次使用时的引导
def init_guide():
    print("=== Skill 配置引导 ===")
    print("请选择数据库配置方式：")
    print("1. 使用默认配置（AWS RDS）")
    print("2. 自定义配置")
    
    choice = input("请输入选项: ")
    if choice == "2":
        host = input("Host: ")
        port = input("Port [5432]: ") or "5432"
        db = input("Database: ")
        user = input("User: ")
        password = input("Password: ")
        return {
            "host": host,
            "port": int(port),
            "database": db,
            "user": user,
            "password": password
        }
    return None  # 使用默认
```

---

### 2.3 部署包封装

#### 目标
- 一键安装脚本
- 完整部署文档
- 包含依赖和配置

#### 目录结构

```
skill_order_to_huading_template_v5.9.0/
├── __init__.py              # Skill 入口
├── SKILL.md                 # 技能文档
├── VERSION                  # 版本号
├── CHANGELOG.md             # 变更日志
├── docs/                    # 文档目录
│   ├── DEPLOY.md            # 部署文档
│   ├── CONFIG.md            # 配置说明
│   └── FAQ.md               # 常见问题
├── scripts/                 # 脚本目录
│   ├── deploy.sh            # 一键部署脚本
│   ├── install_deps.sh      # 安装依赖
│   └── test_connection.sh  # 测试连接
├── tests/                   # 测试目录
│   ├── test_skill.py
│   └── test_db.py
├── .env.example             # 环境变量示例
└── requirements.txt         # Python 依赖
```

#### deploy.sh 脚本

```bash
#!/bin/bash
set -e

echo "=== Skill 部署脚本 v5.9.0 ==="

# 1. 检查依赖
echo "[1/5] 检查依赖..."
if ! command -v python3 &> /dev/null; then
    echo "错误: Python3 未安装"
    exit 1
fi

# 2. 安装依赖
echo "[2/5] 安装依赖..."
pip3 install -r requirements.txt

# 3. 配置数据库
echo "[3/5] 配置数据库..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "请编辑 .env 文件配置数据库连接"
    read -p "按回车继续..."
fi

# 4. 测试连接
echo "[4/5] 测试数据库连接..."
bash scripts/test_connection.sh

# 5. 完成
echo "[5/5] 部署完成！"
echo "运行测试: python3 -m pytest tests/"
```

#### requirements.txt

```
psycopg2-binary>=2.9.9
pandas>=2.0.0
openpyxl>=3.1.0
python-dotenv>=1.0.0
```

---

### 2.4 数据初始化

#### 目标
- 预置基础数据（商品/门店）给新用户
- 提供数据导入模板
- 支持批量导入

#### 数据导入模板

```csv
# product_sku 导入模板
sku_code,customer_code,sku_name,product_spec,unit,unit_type,conversion_ratio,shipper_id,category,warehouse_code
SKU001,C001,商品名称,规格,件,大单位,10,HZ2023061500001,品类,W001
```

```csv
# store_list 导入模板
store_code,store_name,owner_code,province,city,district,address
S001,门店名称,货主ID,省份,城市,区,地址
```

#### 数据导入脚本

```python
import pandas as pd
from psycopg2 import connect

class DataImporter:
    def __init__(self, db_config: Dict):
        self.conn = connect(**db_config)
    
    def import_product_sku(self, csv_path: str):
        df = pd.read_csv(csv_path)
        cursor = self.conn.cursor()
        
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO product_sku (sku_code, customer_code, sku_name, ...)
                VALUES (%s, %s, %s, ...)
                ON CONFLICT (sku_code, shipper_id) DO UPDATE SET ...
            """, tuple(row))
        
        self.conn.commit()
        print(f"已导入 {len(df)} 条商品数据")
    
    def import_store_list(self, csv_path: str):
        df = pd.read_csv(csv_path)
        # 类似逻辑
        pass
```

#### 新用户初始化流程

```python
def init_new_user(db_config: Dict, user_data_path: str = None):
    """
    新用户初始化
    
    Args:
        db_config: 数据库连接配置
        user_data_path: 用户自定义数据路径（可选）
    """
    importer = DataImporter(db_config)
    
    # 1. 导入基础数据（可选）
    if user_data_path:
        importer.import_from_directory(user_data_path)
    
    # 2. 创建用户记录
    cursor = importer.conn.cursor()
    cursor.execute("""
        INSERT INTO skill_permissions (user_id, role)
        VALUES (%s, 'admin')
        ON CONFLICT DO NOTHING
    """, (get_current_user_id(),))
    importer.conn.commit()
    
    print("初始化完成！")
```

---

## 3. 技术实现方案

### 3.1 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 运行环境 |
| PostgreSQL | 14+ | 数据库（AWS RDS） |
| psycopg2 | 2.9+ | 数据库驱动 |
| pandas | 2.0+ | 数据处理 |
| openpyxl | 3.1+ | Excel 处理 |

### 3.2 目录结构

```
/Users/jinqianfei/openclaw-workspaces/ai-order/
└── skills/
    └── skill_order_to_huading_template/
        ├── __init__.py           # Skill 入口（含权限控制）
        ├── SKILL.md              # 技能文档
        ├── VERSION               # 版本号
        ├── CHANGELOG.md          # 变更日志
        ├── docs/
        │   ├── DEPLOY.md         # 部署文档
        │   ├── CONFIG.md         # 配置说明
        │   └── FAQ.md            # 常见问题
        ├── scripts/
        │   ├── deploy.sh         # 一键部署
        │   ├── install_deps.sh   # 安装依赖
        │   ├── test_connection.sh # 测试连接
        │   └── import_data.py    # 数据导入
        ├── tests/
        │   ├── test_skill.py
        │   └── test_db.py
        ├── .env.example          # 环境变量示例
        └── requirements.txt     # Python 依赖
```

### 3.3 权限检查流程

```
用户调用 skill.execute()
    ↓
检查用户角色（从 skill_permissions 表）
    ↓
根据角色判断操作权限
    ↓
允许/拒绝操作
    ↓
记录操作日志（permission_logs 表）
```

---

## 4. 部署文档

### 4.1 前置要求

- Python 3.10+
- PostgreSQL 14+（AWS RDS）
- 网络访问 AWS RDS 数据库（ap-southeast-1 区域）

### 4.2 快速部署

```bash
# 1. 克隆项目
git clone <repo_url>
cd skill_order_to_huading_template

# 2. 安装依赖
pip3 install -r requirements.txt

# 3. 配置环境
cp .env.example .env
vim .env  # 编辑数据库配置

# 4. 测试连接
bash scripts/test_connection.sh

# 5. 运行测试
python3 -m pytest tests/
```

### 4.3 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| DB_HOST | 数据库地址 | agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com |
| DB_PORT | 数据库端口 | 5432 |
| DB_NAME | 数据库名 | neo |
| DB_USER | 数据库用户 | agenthub |
| DB_PASSWORD | 数据库密码 | （必须设置，.env 文件） |

---

## 5. 后续迭代计划

### 5.1 Phase 1（本次）

- [x] 权限控制设计
- [x] 数据库配置化
- [ ] 部署包封装
- [ ] 数据导入工具

### 5.2 Phase 2

- [ ] 权限控制实现
- [ ] 部署脚本完善
- [ ] 单元测试补全

### 5.3 Phase 3

- [ ] CI/CD 流程
- [ ] Docker 镜像
- [ ] 监控告警

---

## 6. 附录

### 6.1 数据库连接信息

```
Host: agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com
Port: 5432
Database: neo
User: agenthub
Password: (环境变量 DB_PASSWORD / .env 文件)
```

### 6.2 相关文件

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 技能完整文档 |
| `VERSION` | 版本号（5.9.0） |
| `CHANGELOG.md` | 变更日志 |

---

**文档版本**: v1.0  
**最后更新**: 2026-06-08