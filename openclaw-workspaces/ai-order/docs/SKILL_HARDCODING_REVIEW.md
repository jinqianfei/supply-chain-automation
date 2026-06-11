# Skill 硬编码 & 绝对路径 Review 报告

**审查日期**：2026-06-09
**审查范围**：`skills/skill_order_to_huading_template/`（v5.11.1）
**审查目的**：评估 skill 在移植到其他机器/分享给他人时的"开箱即用"程度
**审查方式**：全量 grep + 人工分类

---

## 📊 审查汇总

| 类别 | 数量 | 严重度 | 移植影响 |
|------|------|--------|---------|
| A. 绝对路径写死（机器特定） | **5 处** | 🔴 P0 | 换机器直接报错 |
| B. `.env` / 配置文件相对路径假设 | **4 处** | 🟡 P1 | 路径变了找不到配置 |
| C. 数据库连接硬编码 | **11 处** | 🔴 P0 | 用户名/主机写死，跨环境必改 |
| D. LLM Provider 硬编码 | **9 处** | 🟡 P1 | 模型/URL 写死，不通用 |
| E. 业务字段硬编码（31字段） | **6 处** | 🟡 P1 | 两处重复定义 + 别名散落 |
| F. 货主/客户名硬编码（YAML 规则） | **3 个文件** | 🟢 P2 | 业务隔离，可接受 |
| G. SKU/仓库表名硬编码 | **10 处** | 🟡 P1 | 表名改了要全文替换 |
| H. 提示词 & 默认值硬编码 | **5 处** | 🟢 P2 | 业务常量，影响小 |
| **总计** | **53 处** | | |

---

## 🔴 P0 - 必须修复（机器特定，移植必崩）

### A. 绝对路径写死（5 处）

| 位置 | 内容 | 问题 |
|------|------|------|
| `__init__.py:158` | `AWS_PUBLIC_IP = "13.212.17.85"` | AWS EC2 公网 IP，**金姐的机器特有** |
| `__init__.py:159` | `AWS_FILE_PORT = 18790` | 文件下载端口硬编码 |
| `__init__.py:176` | `f"http://{AWS_PUBLIC_IP}:{AWS_FILE_PORT}/..."` | 用上面 IP 生成下载 URL |
| `scripts/sync_check.sh:89-91` | `/Users/jinqianfei/openclaw-workspaces`、`/Downloads`、`/.openclaw` | sync_check 的白名单，**金姐的家目录硬编码** |
| `scripts/test_event_pipeline.py:138-139` | `/tmp/test_order.txt`、`/tmp/test_output.xlsx` | 测试 fixture 路径硬编码 |

**修复方案**：
- `AWS_PUBLIC_IP/PORT` → 改读 `AWS_PUBLIC_IP` / `AWS_FILE_PORT` 环境变量，fallback 用空字符串（无 AWS 时禁用文件 URL 功能）
- `sync_check.sh` 的白名单 → 用 `$HOME` 变量替换 `/Users/jinqianfei`
- 测试 fixture → 用 `tempfile.NamedTemporaryFile` 或 `tmp_path` pytest fixture

### C. 数据库连接硬编码（11 处）

| 位置 | 内容 | 问题 |
|------|------|------|
| `__init__.py:396` | `os.getenv("DB_HOST", "agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com")` | **金姐的 RDS 主机写死在 fallback** ⚠️ |
| `__init__.py:399` | `os.getenv("DB_USER", "agenthub")` | 用户名 fallback 写死 |
| `__init__.py:298` | `os.getenv("DB_HOST", "localhost")` | 文档示例，OK |
| `__init__.py:322` | `os.getenv("DB_HOST", "localhost")` | 文档示例，OK |
| `__init__.py:334` | `os.getenv("DB_HOST", "localhost")` | 文档示例，OK |
| `__init__.py:339-342` | `"database": "neo", "user": "your_username"` | 配置模板，OK |
| `tools/_sku_mapper.py:233` | `"host": os.getenv("DB_HOST", "localhost"), ..., "database": "neo", "user": "your_username"` | **真实 fallback，端口 5432、库名 neo 写死** ⚠️ |
| `tools/_sku_mapper.py:538` | 同上 | **重复** ⚠️ |
| `db/connection.py:45-50` | `"localhost", port=5432, "neo", "your_username"` | 占位符 fallback |
| `scripts/test_event_pipeline.py:25` | `"host": os.getenv("DB_HOST", "localhost")` | 测试脚本 |

**修复方案**：
- **`__init__.py:396` 必须改**：把 `agenthub-db.cjys0msc4x8s.ap-southeast-1.rds.amazonaws.com` 改为 `localhost` 或删掉（让 env 必填）
- **`tools/_sku_mapper.py:233/538` 重复 fallback**：统一从 `db/connection.py:get_connection()` 拿，不要在每个工具里写 fallback
- **`db/connection.py`** 已经做了，应该让其他工具调用它

---

## 🟡 P1 - 应该修复（影响通用性，但当前能跑）

### B. `.env` / 配置文件相对路径假设（4 处）

| 位置 | 内容 | 问题 |
|------|------|------|
| `__init__.py:405` | `os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env")` | 假设 .env 在 skill 的祖父目录（`ai-order/.env`） |
| `__init__.py:440` | 同上 | 重复 |
| `__init__.py:1217` | 同上 | 第三次出现 |
| `db/connection.py:30-34` | `os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "db_config.yaml")` | 假设 yaml 在 skill 的父目录的 config/ |

**修复方案**：
- 抽出统一函数 `_find_dotenv()`，先查 `DOTENV_PATH` 环境变量，再查 skill 父目录，最后查 CWD
- 引入 `python-dotenv` 库用 `find_dotenv()`（已经缺它）

### D. LLM Provider 硬编码（9 处）

| 位置 | 内容 | 问题 |
|------|------|------|
| `config/llm.yaml:30` | `model: "gpt-4o"` | 模型写死 |
| `config/llm.yaml:37-38` | `base_url: "https://api.minimax.chat/v1"` + model `MiniMax-M2.7` | MiniMax 特定 |
| `config/llm.yaml:44-45` | `base_url: "https://api.deepseek.com/v1"` | DeepSeek 特定 |
| `config/llm.yaml:51-52` | `https://dashscope.aliyuncs.com` + `qwen-plus` | 阿里云特定 |
| `config/llm.yaml:58-59` | `https://api.moonshot.cn/v1` + `moonshot-v1-8k` | 月之暗面特定 |
| `__init__.py:1212` | `os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")` | 优先级写死 |
| `__init__.py:1252` | `base_url="https://api.minimax.chat/v1"` | **重复硬编码**（与 yaml 不一致风险）⚠️ |
| `__init__.py:1268` | `model="gpt-4o"` | **重复硬编码** |
| `__init__.py:1242` | `model="MiniMax-M2.7"` | **重复硬编码** |

**修复方案**：
- `__init__.py:1200-1280` 的 `_llm_parse_fallback()` 函数应该改成统一调用 `learn/llm/router.py`，不要在主入口写第二套 LLM 客户端
- yaml 里的 provider 配置是合理的（业务上就要这些 URL），不算硬编码 bug

### E. 业务字段硬编码（6 处）

| 位置 | 内容 | 问题 |
|------|------|------|
| `__init__.py:549-559` | `HUADING_FIELDS = [...]` 31 字段列表 | **华鼎模板列定义** |
| `tools/_template_generator.py:14-25` | **同一个 HUADING_FIELDS 重复定义** | ⚠️ **双重维护隐患** |
| `__init__.py:485-490` | `FIELD_ALIAS_MAPPING`（标准字段→中文别名） | 散落在主入口 |
| `__init__.py:527-530` | `_FIELD_ALIAS_PATTERNS`（订单字段名→标准字段） | 重复 |
| `__init__.py:1106, 1120, 1122` | `"quantity", "qty", "num", "数量"` 等 | 散落的字段名硬编码 |
| `tools/_field_transformer.py:210-224` | 同上 | 重复定义 |

**修复方案**：
- 把 `HUADING_FIELDS` 抽到 `config/template_defaults.yaml`（已经有部分默认值），让两边 `from config import HUADING_FIELDS`
- 把 `FIELD_ALIAS_MAPPING` 抽到 `field_mapping/rules/default.yaml`（已经有 customer 级别的 yaml）
- 同一份映射规则不应该在 `__init__.py` 和 `tools/_field_transformer.py` 各写一份

### G. SKU/仓库表名硬编码（10 处）

| 位置 | 内容 |
|------|------|
| `tools/_sku_mapper.py:262` | `JOIN product_sku p ON ...` |
| `tools/_sku_mapper.py:279` | `FROM product_sku WHERE ... status = 'ACTIVE'` |
| `tools/_sku_mapper.py:296` | 同上 |
| `tools/_sku_mapper.py:328` | 同上 |
| `tools/_sku_mapper.py:356` | `LIMIT 200` |
| `tools/_sku_mapper.py:400` | `LIMIT 20` |
| `tools/_sku_mapper.py:499` | `FROM product_sku WHERE ... status = 'ACTIVE'` |
| `tools/_sku_mapper.py:560` | `JOIN product_sku p ON ...` |
| `tools/_template_generator.py:48` | `FROM warehouse_code_mapping` |
| `tools/_sku_mapper.py:279` 等多处 | `status = 'ACTIVE'`（状态值写死） |

**修复方案**：
- 表名抽到 `db/table_names.py` 常量文件：`SKU_TABLE = "product_sku"`、`WAREHOUSE_TABLE = "warehouse_code_mapping"`、`ACTIVE_STATUS = "ACTIVE"`
- 集中一处修改，全局生效

---

## 🟢 P2 - 可以接受（业务常量，不影响移植）

### F. 货主/客户名硬编码（3 个 YAML 规则文件）

| 文件 | 内容 | 评估 |
|------|------|------|
| `field_mapping/rules/创宇.yaml` | `customer_name: "盐城市创宇食品有限公司"` | 业务配置，OK |
| `field_mapping/rules/王小五.yaml` | `customer_name: "王小五剁椒面"` | 业务配置，OK |
| `field_mapping/rules/小江溪.yaml` | `customer_name: "小江溪"` | 业务配置，OK |

> 业务规则本来就是按客户隔离的，不算"硬编码 bug"。

### H. 提示词 & 默认值硬编码（5 处）

| 位置 | 内容 |
|------|------|
| `config/template_defaults.yaml` | `"出库类型": "201"`、`"配送方式": "共配"` 等业务默认值 |
| `__init__.py:557-563` | `DEFAULT_VALUES = {"加急程度": 0, "指定库存状态": "正常", "出库类型": 201, ...}` |
| `__init__.py:485-490` | 字段中文名映射 |
| `__init__.py:435` | `os.environ.pop("no_proxy", None)` 等代理清理（应该是 `SOCKS_PROXY` 等固定名称） |
| `__init__.py:2221` | `["商品名称", "商品编码", "商品规格", "计量单位", "备注", ""]` 占位符列表 |

**修复方案**：
- `template_defaults.yaml` 已经有了，应该让 `__init__.py` 的 `DEFAULT_VALUES` 从 yaml 读取，而不是再写一遍

---

## 🎯 修复优先级建议

### 🔥 紧急（5 分钟搞定）
1. **`__init__.py:396` 改 fallback**：把 `agenthub-db.cjys0msc4x8s...` 改成 `localhost`
2. **`AWS_PUBLIC_IP` 改环境变量**：加 `os.getenv("AWS_PUBLIC_IP", "")` 包裹
3. **`tools/_sku_mapper.py:233/538` 统一调用 `db/connection.py:get_connection()`**

### 📋 中期（1 小时）
4. 抽 `HUADING_FIELDS` 到 `config/template_defaults.yaml`，消除双重定义
5. 抽 `FIELD_ALIAS_MAPPING` 到 `field_mapping/rules/default.yaml`
6. 抽表名常量到 `db/table_names.py`
7. `__init__.py:1200-1280` 的 LLM fallback 改为统一走 `learn/llm/router.py`

### 🛠️ 长期（可分享化前置）
8. `.env` 路径查找用 `python-dotenv.find_dotenv()`
9. `sync_check.sh` 的 `/Users/jinqianfei` 改 `$HOME`
10. 测试 fixture 改 `tempfile`

---

## 📈 移植成熟度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 数据库可移植性 | ⭐⭐☆☆☆ | `__init__.py:396` 写死金姐的 RDS，换环境直接连错库 |
| 路径可移植性 | ⭐⭐☆☆☆ | `.env` 路径假设 + AWS IP 写死，换机器 URL 全错 |
| LLM 可移植性 | ⭐⭐⭐☆☆ | yaml 配置合理，但 `__init__.py` 里有第二套硬编码 |
| 业务字段可移植性 | ⭐⭐⭐☆☆ | 31 字段两处重复 + 别名散落 |
| 测试可移植性 | ⭐⭐☆☆☆ | `/tmp/test_*.txt` 硬编码 |
| **综合** | **⭐⭐½** | **当前状态：只能在金姐机器上跑，移植前必须修 P0 5 处** |

---

## 🔗 相关文档

- `MEMORY.md` 2026-06-09 数据库全貌盘点
- `IDENTITY.md` 货主-品牌对照
- `TOOLS.md` Skill 调用规范
- `docs/云端部署迁移方案.md`（选方案 A：保留 AWS RDS）