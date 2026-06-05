# TOOLS.md - AI建单助手工具配置

## Skill: skill_order_to_huading_template

**版本**: v5.8（2026-06-01）

### 使用方式

```python
from skills.skill_order_to_huading_template import OrderToHuadingTemplate

skill = OrderToHuadingTemplate(
    db_config={
        "host": "localhost",
        "port": 5432,
        "database": "neo",
        "user": "jinqianfei"
    }
)

# 处理Excel订单
result = skill.execute(order_input="/path/to/order.xlsx")

# 处理图片/PDF（两步流程）
result = skill.execute(order_input="/path/to/order.jpg", order_type="image")
# 如果返回 need_ocr=True，用 image 工具识别后回传
if result.get("need_ocr"):
    ocr_result = image_tool.analyze(...)
    result = skill.execute(order_input=result["image_path"], order_type="image", ocr_result=ocr_result)
```

### 返回结果

```python
{
    "success": True,
    "output_file": "/path/to/huading_template.xlsx",
    "owner_code": "HZ2023061500002",  # 货主ID，需用户确认
    "item_count": 7,
    "unmatched_count": 0,
    "message": "模板生成成功"
}
```

### 图片/PDF处理流程

```
用户上传图片/PDF
    ↓
skill.execute() 返回 need_ocr=True
    ↓
使用 image 工具识别（对于图片）
    ↓
将识别结果回传给 skill
    ↓
继续门店匹配、货主确认、SKU映射
```

### 数据库配置

| 配置项 | 值 |
|--------|-----|
| Host | localhost |
| Port | 5432 |
| Database | **neo**（不是 neondb） |
| User | jinqianfei |

### 数据库表（v5.8）

| 表名 | 货主ID字段 | 用途 |
|------|-----------|------|
| product_sku | shipper_id | SKU主表（合并后，1832条） |
| product_name_alias | shipper_id | 商品名别名映射（30条） |
| store_list | owner_code | 门店列表（~714条） |
| warehouse_code_mapping | — | 仓库编码 |
| customer | — | 货主信息 |

**注意**: `system_sku` 和 `shipper_sku_mapping` 已于 v5.4 合并到 `product_sku` 表中。

### 货主-品牌对照

| 货主公司全称 | 品牌 | 货主ID |
|-------------|------|--------|
| 河南上黎供应链管理有限公司 | 制茶青年 | HZ2023061500002 |
| 郑州市必德供应链管理有限公司 | 廖朵朵 | HZ2024091100001 |
| 天津王口镇店 | — | CUSTOMER-WANGKOU |
| 长沙广承供应链有限公司 | — | CUSTOMER-GUANGCHENG |
| 创宇 | — | HZ2024061300001 |

### 重要原则

- **货主必须确认**：匹配后必须用户确认货主正确，才能继续
- **多货主支持**：不默认货主，通过门店名匹配获取
- **映射置信度**：SKU匹配<80%需人工确认
- **版本管理**：修改 skill 时需更新 VERSION + CHANGELOG，并通过 git 保留证据

---

## 钉钉 CLI (DingTalk Workspace CLI)

**工具路径:** `/opt/homebrew/bin/dws`
**认证状态:** 已登录（全局有效，Token 有效期至当天17:35）

### 常用命令

```bash
# 文档操作
dws doc list                    # 列出文档
dws doc search <关键词>         # 搜索文档
dws doc create --title <标题>   # 创建文档
dws doc read <文档ID>           # 读取文档内容
dws doc update <文档ID>         # 更新文档
dws doc folder                  # 文件夹管理

# 其他产品域
dws aitable                     # AI表格
dws calendar                    # 日历日程
dws chat                        # 群聊消息
dws wiki                        # 知识库
dws mail                        # 邮箱
```

### 输出格式
```bash
dws doc list -f json            # JSON输出（默认）
dws doc list -f table           # 表格输出
dws doc list -f pretty          # 美化输出
dws doc list --dry-run          # 预览模式（不执行）
```

### 认证信息
- Corp ID: `ding5392f470b795a632f5bf40eda33b7ba0`
- Token 自动刷新，无需手动操作