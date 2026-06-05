# tools package - 内部工具模块
#
# ⚠️ 重要：本目录下的工具函数为 Skill 内部实现，不应直接外部调用
# 
# 使用方式：
#   请通过 OrderToHuadingTemplate.execute() 方法调用 Skill
#   不要直接导入或调用本目录下的工具函数
#
# 示例（✅ 正确）：
#   from skills.skill_order_to_huading_template import OrderToHuadingTemplate
#   skill = OrderToHuadingTemplate(db_config=...)
#   result = skill.execute(order_input="/path/to/order.xlsx")
#
# 示例（❌ 错误）：
#   from tools.sku_mapper import map_sku  # 不要这样做！
#   from tools.store_matcher import match_store  # 不要这样做！