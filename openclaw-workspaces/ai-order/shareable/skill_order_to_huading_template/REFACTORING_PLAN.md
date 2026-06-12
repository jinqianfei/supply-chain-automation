# Skill 重构记录 - skill_order_to_huading_template

## 当前版本：v5.2（2026-05-29）

---

## 一、重构目标达成情况

| 目标 | 状态 | 说明 |
|------|------|------|
| `execute()` 调用 `tools/` 层解析 | ✅ 完成 | 不再自己实现解析逻辑 |
| 门店匹配后用户确认 | ✅ 完成 | 移除 auto_confirm，所有匹配需确认 |
| SKU映射后用户确认 | ✅ 保留 | 置信度<80%告警，已在流程中 |
| 多门店序号格式 | ✅ 完成 | 序号=门店序号，同门店相同，从1开始 |
| Word 原生解析 | ✅ 完成 | python-docx 提取段落+表格 |
| 图片/PDF 工具回调 | ✅ 完成 | `need_ocr=True` / `need_pdf=True` |

---

## 二、已完成的重构

### 1. `tools/order_parser.py` 增强 ✅
- `parse()` 主函数：支持 Excel/图片/PDF/Word/文字
- `parse_with_ocr_result()`：接收 image 工具回传的 OCR 结果
- `parse_with_pdf_text_result()`：接收 pdf 工具回传的文本
- `parse_with_docx_text_result()`：接收 Word 提取的文本
- `_parse_word()`：python-docx 原生提取段落+表格
- 空 OCR 结果处理：`{"text": ""}` 返回 `success=False`

### 2. `tools/field_transformer.py` ✅
- `transform()` 主函数：规则库字段名标准化
- `load_field_mapping_rules()`：加载 YAML 规则库
- 多门店输出格式支持

### 3. `tools/__init__.py` ✅
- 导出 `parse` / `transform` / `load_field_mapping_rules`

### 4. `__init__.py` 重构 ✅
- `execute()` 改为调用 `tools_parse()` + `tools_transform()`
- 移除重复的 `parse_with_llm()` / `_normalize_llm_result()` 等方法
- 保留：门店匹配 `_match_store()` / SKU映射 `_match_sku()` / 模板生成

### 5. 门店匹配强制确认 ✅（v5.2 重点）
- 移除 `sim >= 0.75` / `top_sim >= 90%` 自动确认逻辑
- 所有匹配结果返回 `need_store_confirm=True`
- 返回 `matched_store`（含相似度）供用户核对
- 返回 `candidates` 候选列表

### 6. 多门店模板格式 ✅
- 移除门店名称分隔行
- 序号 = 门店序号（同一门店商品序号相同，从1开始）
- 门店编号 列区分不同门店

---

## 三、当前完整流程

```
Step 1: tools_parse() → LLM解析订单 → 原始JSON
Step 2: tools_transform() → 规则库标准化 → 统一JSON
Step 3: _match_store() → store_list表匹配 → ⚠️ need_store_confirm
        ↓ 用户确认
Step 4: _match_sku() → shipper_sku_mapping表 → SKU映射
        ↓
Step 5: _generate_multi_store_template() → 31字段Excel
```

---

## 四、数据库配置

| 配置项 | 值 |
|--------|-----|
| Host | `your_db_host` (环境变量) |
| Port | 5432 |
| Database | `${DB_NAME}` (环境变量) |
| User | `${DB_USER}` (环境变量) |

---

## 五、测试验证

### 测试1：Excel订单解析
```
输入: 2026.5.28天津仓库（订单）(1).xlsx
门店: 天津滨海新区-塘沽万达店、北京大兴区-天宫院店
商品: 11条
结果: need_store_confirm=True（相似度129%）
```

### 测试2：语法检查
```bash
python3 -c "import ast; ast.parse(open('__init__.py').read())"
# ✅ 语法正确
```

---

## 六、待用户确认后的下一步

当用户确认门店匹配后，`execute()` 需要接收 `confirmed_store` 参数继续：

```python
result = skill.execute(
    order_input=order_input,
    order_type=order_type,
    confirmed_store={...}  # 用户确认的门店信息
)
```

确认后进入 SKU映射 → 返回 need_sku_confirm → 用户确认 → 生成 Excel

---

## 七、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 5.0 | 2026-05-28 | 架构重构：tools/ 层分离 |
| 5.1 | 2026-05-28 | Word原生解析、PDF/图片工具回调 |
| 5.2 | 2026-05-29 | 门店匹配强制确认（移除auto_confirm）、多门店序号格式 |