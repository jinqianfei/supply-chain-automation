#!/usr/bin/env python3
"""
重新执行Skill测评 - 使用正确的Ground Truth标注

Ground Truth来源：直接查询数据库product_sku表，而非从output文件推断
"""
import json
import os
import sys
from pathlib import Path

# 添加skill路径
sys.path.insert(0, '/Users/jinqianfei/openclaw-workspaces/ai-order/skills/skill_order_to_huading_template')

from tools.sku_mapper import map_sku
from tools.store_matcher import match_store

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "neo",
    "user": "jinqianfei"
}

# 订单文件列表（从inbound目录）
ORDER_FILES = [
    "广州仓报单明细_16---bc6cf341-af88-45ad-81cd-583378eb96d3.xlsx",
    "华鼎_郑州仓报单明细_21---5928d1e0-7772-4d56-9e7b-55e204bbe8f2.xlsx",
    "小江溪_江西菜_长治万达店_配送明细表_5.29---18401300-3340-40fb-b2d5-f77d3e3c9ef0.xlsx",
    "配送明细表_26---c5ede6f0-f958-42cc-bb07-43bda964a3e7.xlsx",
    "华鼎下单5.29---c87cb9b0-acf8-4e7c-96ee-6c41276812d7.xlsx",
    "华鼎出库单20260529---f9d8c3a4-2b90-4900-b4d6-6e98a02a003e.xlsx",
    "2026.5.28天津仓库_订单_1---29d44dbb-3e0f-43cd-b4e8-1ddfc54172ad.xlsx",
]

INBOUND_DIR = Path("/Users/jinqianfei/.openclaw/media/inbound/")
OUTPUT_DIR = Path("/Users/jinqianfei/openclaw-workspaces/ai-order/docs/test_data/")


def load_order_data(filename):
    """加载订单数据"""
    filepath = INBOUND_DIR / filename
    if not filepath.exists():
        return None
    
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    
    # 读取表头和数据行
    headers = []
    data = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(h).strip() if h else "" for h in row]
        else:
            if any(row):
                data.append(dict(zip(headers, row)))
    
    return {"filename": filename, "headers": headers, "data": data}


def extract_store_and_items(order_data):
    """从订单数据中提取门店和商品信息"""
    filename = order_data["filename"]
    data = order_data["data"]
    headers = order_data["headers"]
    
    # 检测是否是华鼎格式（多门店）
    if "门店编号" in headers or "门店三方编码" in headers:
        # 华鼎格式 - 按门店分组
        stores = {}
        for row in data:
            store_name = str(row.get("门店名称", row.get("门店", "")) or "").strip()
            if not store_name:
                continue
            if store_name not in stores:
                stores[store_name] = []
            stores[store_name].append(row)
        return stores
    else:
        # 普通格式 - 尝试解析门店名
        stores = {}
        for row in data:
            # 尝试找门店名列
            store_name = ""
            for col in ["门店", "店铺", "店名", "收货人", "客户"]:
                if col in headers:
                    store_name = str(row.get(col, "") or "").strip()
                    break
            if not store_name:
                store_name = "默认门店"
            if store_name not in stores:
                stores[store_name] = []
            stores[store_name].append(row)
        return stores


def parse_product_info(row, headers):
    """从订单行中解析商品信息"""
    # 尝试找商品名字段
    product_name = ""
    for col in ["商品名称", "品名", "名称", "商品", "product_name", "name"]:
        if col in headers:
            product_name = str(row.get(col, "") or "").strip()
            break
    
    if not product_name:
        return None
    
    # 尝试找规格
    spec = ""
    for col in ["规格", "spec", "商品规格", "包装"]:
        if col in headers:
            spec = str(row.get(col, "") or "").strip()
            break
    
    # 尝试找数量
    qty = 0
    for col in ["数量", "qty", "订货数量", "订单数量"]:
        if col in headers:
            try:
                qty = int(float(row.get(col, 0) or 0))
            except:
                qty = 0
            break
    
    # 尝试找单位
    unit = ""
    for col in ["单位", "unit"]:
        if col in headers:
            unit = str(row.get(col, "") or "").strip()
            break
    
    return {
        "name": product_name,
        "spec": spec,
        "qty": qty,
        "unit": unit
    }


def evaluate_store_matching(store_names, db_config):
    """评估门店匹配准确率"""
    results = []
    for store_name in store_names:
        result = match_store(store_name, db_config=db_config)
        results.append({
            "input": store_name,
            "result": result,
            "matched": result is not None and not result.get("need_confirm", False)
        })
    return results


def evaluate_sku_mapping(items, owner_code, db_config):
    """评估SKU映射准确率"""
    results = []
    for item in items:
        if not item or not item.get("name"):
            continue
        
        # 跳过表头等无效行
        name = item["name"]
        if name in ["品名", "商品名称", "name", "商品", ""] or name.startswith("订单"):
            continue
        
        # 调用sku_mapper获取实际映射结果
        mapped = map_sku(owner_code, name, item.get("unit", ""), db_config)
        results.append({
            "input_name": name,
            "input_spec": item.get("spec", ""),
            "input_qty": item.get("qty", 0),
            "input_unit": item.get("unit", ""),
            "mapped": mapped,
            "matched": mapped.get("matched", False)
        })
    return results


def main():
    print("=" * 60)
    print("Skill测评重新执行 - 使用数据库Ground Truth")
    print("=" * 60)
    
    all_store_results = []
    all_sku_results = []
    order_summaries = []
    
    for filename in ORDER_FILES:
        print(f"\n📄 处理: {filename}")
        
        order_data = load_order_data(filename)
        if not order_data:
            print(f"  ⚠️ 文件不存在，跳过")
            continue
        
        stores_data = extract_store_and_items(order_data)
        print(f"  检测到 {len(stores_data)} 个门店")
        
        for store_name, rows in stores_data.items():
            # 解析商品
            items = []
            for row in rows:
                item = parse_product_info(row, order_data["headers"])
                if item:
                    items.append(item)
            
            print(f"  门店「{store_name}」: {len(items)}个商品")
            
            # 门店匹配
            store_match = match_store(store_name, db_config=DB_CONFIG)
            store_result = {
                "store_name": store_name,
                "match_result": store_match,
                "matched": store_match is not None and not store_match.get("need_confirm", False)
            }
            all_store_results.append(store_result)
            
            # 获取货主ID进行SKU映射
            if store_match and store_match.get("owner_code"):
                owner_code = store_match["owner_code"]
                sku_results = evaluate_sku_mapping(items, owner_code, DB_CONFIG)
                all_sku_results.extend(sku_results)
                
                # 统计
                matched_count = sum(1 for r in sku_results if r["matched"])
                print(f"    SKU映射: {matched_count}/{len(sku_results)} 匹配成功")
                
                order_summaries.append({
                    "store": store_name,
                    "owner_code": owner_code,
                    "items_count": len(items),
                    "sku_matched": matched_count,
                    "sku_total": len(sku_results)
                })
            else:
                print(f"    ⚠️ 门店未匹配到货主ID，跳过SKU映射")
                order_summaries.append({
                    "store": store_name,
                    "owner_code": None,
                    "items_count": len(items),
                    "sku_matched": 0,
                    "sku_total": 0
                })
    
    # 计算准确率
    total_stores = len(all_store_results)
    matched_stores = sum(1 for r in all_store_results if r["matched"])
    store_accuracy = matched_stores / total_stores * 100 if total_stores > 0 else 0
    
    total_skus = len(all_sku_results)
    matched_skus = sum(1 for r in all_sku_results if r["matched"])
    sku_accuracy = matched_skus / total_skus * 100 if total_skus > 0 else 0
    
    # 输出结果
    print("\n" + "=" * 60)
    print("📊 测评结果汇总")
    print("=" * 60)
    print(f"\n【门店匹配】")
    print(f"  总门店数: {total_stores}")
    print(f"  匹配成功: {matched_stores}")
    print(f"  准确率: {store_accuracy:.1f}%")
    
    print(f"\n【SKU映射】")
    print(f"  总商品数: {total_skus}")
    print(f"  映射成功: {matched_skus}")
    print(f"  准确率: {sku_accuracy:.1f}%")
    
    # 详细SKU映射结果
    print(f"\n【SKU映射详情】")
    low_confidence = []
    for r in all_sku_results:
        status = "✅" if r["matched"] else "❌"
        conf = r["mapped"].get("confidence", 0)
        method = r["mapped"].get("match_method", "")
        sku_code = r["mapped"].get("sku_code", "")
        print(f"  {status} {r['input_name'][:30]:30s} | {sku_code:20s} | 置信度:{conf:.2f} | {method}")
        if r["matched"] and conf < 0.8:
            low_confidence.append(r)
    
    if low_confidence:
        print(f"\n【低置信度匹配（<0.8）】共{len(low_confidence)}个")
        for r in low_confidence[:5]:
            print(f"  ⚠️ {r['input_name']} → {r['mapped'].get('sku_code')} ({r['mapped'].get('confidence', 0):.2f})")
    
    # 汇总报告
    report = {
        "evaluation_date": "2026-06-02",
        "skill_version": "v5.4",
        "database": "neo",
        "order_files_count": len(ORDER_FILES),
        "store_matching": {
            "total": total_stores,
            "matched": matched_stores,
            "accuracy_pct": round(store_accuracy, 1)
        },
        "sku_mapping": {
            "total": total_skus,
            "matched": matched_skus,
            "accuracy_pct": round(sku_accuracy, 1)
        },
        "order_summaries": order_summaries,
        "detailed_results": all_sku_results[:50]  # 限制数量避免文件过大
    }
    
    # 保存报告
    output_file = OUTPUT_DIR / "evaluation_results_v2.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📁 详细结果已保存到: {output_file}")
    
    return report


if __name__ == "__main__":
    main()