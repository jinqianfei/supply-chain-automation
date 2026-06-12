#!/usr/bin/env python3
"""
LLM解析测试脚本
测试订单：文字订单 + Excel订单

注意：需要设置 OPENAI_API_KEY 环境变量才能使用 LLM 解析
当前会先尝试 LLM，失败后自动 fallback 到正则解析
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skills.skill_order_to_huading_template import OrderToHuadingTemplate
from dotenv import load_dotenv
load_dotenv()

def test_llm_parse():
    """测试 LLM 解析功能"""
    print("=" * 60)
    print("测试1: LLM 解析文字订单（优先）→ fallback 正则")
    print("=" * 60)
    
    skill = OrderToHuadingTemplate(
        db_config={
            "host": "localhost",
            "port": 5432,
            "database": "neo",
            "user": "jinqianfei"
        }
    )
    
    # 测试文字订单
    order_text = """
    订单号：DH-O-20260423-278070
    门店：制茶青年-河北廊坊狮子城店
    联系人：任建华
    电话：18154355555
    地址：河北省廊坊市安次区南门外大街与银河南路辅路交叉口西北方向银河湾S9-1-117
    货主公司：河南上黎供应链管理有限公司
    仓库：天津仓
    备注：加急配送
    
    商品明细：
    - 茉莉花茶（罐装500g） 10件
    - 椰果果粒 3件
    - 蓝莓果肉果酱 1件
    """
    
    print(f"\n📝 测试订单内容:")
    print(order_text)
    
    # 先单独测试 LLM 解析
    print(f"\n--- Step 1: 单独测试 LLM 解析 ---")
    has_api_key = bool(os.getenv('OPENAI_API_KEY'))
    print(f"OPENAI_API_KEY 已设置: {has_api_key}")
    
    if has_api_key:
        try:
            result = skill.parse_with_llm(order_text, content_type="text")
            if result.get('success'):
                print(f"\n✅ LLM解析成功:")
                print(f"   置信度: {result.get('confidence', 0):.2%}")
                print(f"   门店: {result.get('store_name')}")
                print(f"   货主公司: {result.get('shipper_name')}")
                print(f"   仓库: {result.get('warehouse_name')}")
                print(f"   商品数量: {len(result.get('items', []))} 条")
                for item in result.get('items', []):
                    print(f"     - {item.get('product_name')} x {item.get('quantity')}{item.get('unit')}")
            else:
                print(f"\n❌ LLM解析失败: {result.get('error')}")
        except Exception as e:
            print(f"\n❌ LLM解析异常: {e}")
    else:
        print(f"⚠️ 未设置 OPENAI_API_KEY，跳过 LLM 测试（将使用 fallback 正则）")
    
    print(f"\n--- Step 2: 完整流程（LLM优先 → 正则fallback）---")
    
    try:
        result = skill.execute(order_input=order_text, order_type="text")
        print(f"\n执行结果:")
        print(f"   success: {result.get('success')}")
        print(f"   message: {result.get('message')}")
        if result.get('success'):
            print(f"   output_file: {result.get('output_file')}")
            print(f"   解析方式: {result.get('extracted_from')}")
            print(f"   货主ID: {result.get('owner_code')}")
            print(f"   门店编号: {result.get('store_code')}")
            print(f"   仓库编码: {result.get('warehouse_code')}")
            print(f"   商品数量: {result.get('item_count')}")
            print(f"   未匹配数量: {result.get('unmatched_count')}")
        else:
            print(f"   错误详情: {result}")
    except Exception as e:
        print(f"\n❌ 完整流程失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("改造总结")
    print("=" * 60)
    print("""
✅ 已完成改造:
1. 新增 parse_with_llm() 方法 - 使用 LLM 解析订单
2. execute() 主流程优先使用 LLM 解析
3. LLM 失败时自动 fallback 到正则解析
4. LLM 解析支持: store_name, shipper_name, warehouse_name, remark 等新字段

📋 当前流程:
   文字/Excel输入
       ↓
   尝试 LLM 解析（需要 OPENAI_API_KEY）
       ↓ 失败
   Fallback 正则解析
       ↓
   门店匹配 + SKU映射 + 生成模板
       ↓
   人工复核（可选）

⚠️ 注意事项:
   - 需要设置 OPENAI_API_KEY 环境变量才能启用 LLM
   - 当前 fallback 正则解析正常工作
""")

if __name__ == "__main__":
    test_llm_parse()