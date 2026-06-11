#!/usr/bin/env python3
"""
修正测评脚本 - 使用历史人工确认订单作为Ground Truth
方案A：基于历史成功订单建立Ground Truth
"""
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime

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

GROUND_TRUTH_FILE = Path("/Users/jinqianfei/openclaw-workspaces/ai-order/docs/test_data/test_set_A_history回流.json")
OUTPUT_DIR = Path("/Users/jinqianfei/openclaw-workspaces/ai-order/skills/docs/")


def clean_text(text):
    """清洗文本"""
    if not text:
        return ""
    text = str(text)
    text = text.strip()
    text = re.sub(r'[\t\u00a0\u3000\u200b-\u200f\ufeff]+', '', text)
    text = text.replace(' ', '')
    return text


def evaluate_with_ground_truth(order_data, db_config):
    """
    使用Ground Truth评估订单
    
    order_data格式:
    {
        "source": "订单来源",
        "stores": {
            "门店名": {
                "name": "门店名",
                "items": [{"name": "商品名", "spec": "规格", "qty": 数量, "unit": "单位"}, ...]
            }, ...
        },
        "ground_truth": {
            "1": [{"sku": "SKU编码", "unit_type": "大单位/小单位"}, ...],
            "2": [...],
            ...
        }
    }
    """
    results = {
        "source": order_data.get("source", "unknown"),
        "stores": [],
        "total_items": 0,
        "correct": 0,
        "incorrect": 0,
        "unmatched": 0,
        "errors": []
    }
    
    ground_truth = order_data.get("ground_truth", {})
    stores = order_data.get("stores", {})
    
    store_idx = 1
    for store_name, store_data in stores.items():
        items = store_data.get("items", [])
        if not items:
            continue
        
        # 门店匹配
        store_match = match_store(store_name, db_config=db_config)
        owner_code = store_match.get("owner_code") if store_match else None
        
        store_result = {
            "store_name": store_name,
            "owner_code": owner_code,
            "store_matched": owner_code is not None,
            "items": [],
            "correct": 0,
            "incorrect": 0
        }
        
        # 获取该门店的Ground Truth
        store_gt_key = str(store_idx)
        store_gt = ground_truth.get(store_gt_key, [])
        
        item_idx = 0
        for item in items:
            item_name = clean_text(item.get("name", ""))
            if not item_name:
                continue
            
            gt_item = store_gt[item_idx] if item_idx < len(store_gt) else None
            expected_sku = gt_item.get("sku") if gt_item else None
            expected_unit_type = gt_item.get("unit_type") if gt_item else None
            
            # 调用Skill进行SKU映射
            mapped = map_sku(owner_code, item_name, item.get("unit", ""), db_config)
            actual_sku = mapped.get("sku_code")
            
            # 对比Ground Truth
            is_correct = (expected_sku and actual_sku == expected_sku)
            
            item_result = {
                "name": item_name,
                "qty": item.get("qty"),
                "unit": item.get("unit"),
                "expected_sku": expected_sku,
                "actual_sku": actual_sku,
                "matched": mapped.get("matched", False),
                "correct": is_correct,
                "confidence": mapped.get("confidence", 0),
                "match_method": mapped.get("match_method", "")
            }
            
            store_result["items"].append(item_result)
            results["total_items"] += 1
            
            if is_correct:
                results["correct"] += 1
                store_result["correct"] += 1
            elif expected_sku and not actual_sku:
                results["unmatched"] += 1
            else:
                results["incorrect"] += 1
        
        store_idx += 1
        results["stores"].append(store_result)
    
    results["accuracy"] = (results["correct"] / results["total_items"] * 100) if results["total_items"] > 0 else 0
    
    return results


def main():
    print("=" * 70)
    print("Skill测评 v5.8 - 使用历史人工确认Ground Truth")
    print("=" * 70)
    print(f"\nGround Truth来源: {GROUND_TRUTH_FILE}")
    print(f"测评日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 加载Ground Truth数据
    print(f"\n📂 加载历史订单数据集...")
    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    
    print(f"   订单总数: {len(test_data)}")
    
    # 执行评估
    all_results = []
    total_correct = 0
    total_items = 0
    total_incorrect = 0
    total_unmatched = 0
    
    print("\n" + "=" * 70)
    print("📊 开始测评")
    print("=" * 70)
    
    for i, order in enumerate(test_data):
        source = order.get("source", f"订单{i+1}")
        print(f"\n[{i+1}/{len(test_data)}] 处理: {source}")
        
        result = evaluate_with_ground_truth(order, DB_CONFIG)
        all_results.append(result)
        
        total_correct += result["correct"]
        total_items += result["total_items"]
        total_incorrect += result["incorrect"]
        total_unmatched += result["unmatched"]
        
        accuracy = result["accuracy"]
        print(f"   准确率: {accuracy:.1f}% ({result['correct']}/{result['total_items']})")
        
        # 显示错误case
        if result["incorrect"] > 0 or result["unmatched"] > 0:
            print(f"   ⚠️ 错误/未匹配: {result['incorrect'] + result['unmatched']}")
            for item in result["stores"]:
                for prod in item["items"]:
                    if not prod["correct"]:
                        print(f"      - {prod['name'][:25]}")
                        print(f"        期望: {prod['expected_sku']} | 实际: {prod['actual_sku'] or '未匹配'}")
    
    # 汇总统计
    overall_accuracy = (total_correct / total_items * 100) if total_items > 0 else 0
    
    print("\n" + "=" * 70)
    print("📊 测评结果汇总")
    print("=" * 70)
    print(f"\n【整体准确率】")
    print(f"  总商品数: {total_items}")
    print(f"  正确匹配: {total_correct}")
    print(f"  错误匹配: {total_incorrect}")
    print(f"  未匹配:   {total_unmatched}")
    print(f"  准确率:   {overall_accuracy:.1f}%")
    
    # 计算高/中/低置信度
    high_conf = 0
    mid_conf = 0
    low_conf = 0
    
    for result in all_results:
        for store in result["stores"]:
            for item in store["items"]:
                conf = item.get("confidence", 0)
                if conf >= 0.8:
                    high_conf += 1
                elif conf >= 0.7:
                    mid_conf += 1
                else:
                    low_conf += 1
    
    print(f"\n【置信度分布】")
    print(f"  高置信度(≥0.8): {high_conf} ({high_conf/total_items*100:.1f}%)")
    print(f"  中置信度(0.7-0.8): {mid_conf} ({mid_conf/total_items*100:.1f}%)")
    print(f"  低置信度(<0.7): {low_conf} ({low_conf/total_items*100:.1f}%)")
    
    # 生成报告
    report = {
        "evaluation_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "skill_version": "v5.8",
        "ground_truth_source": "test_set_A_history回流.json",
        "total_orders": len(test_data),
        "total_items": total_items,
        "correct": total_correct,
        "incorrect": total_incorrect,
        "unmatched": total_unmatched,
        "accuracy_pct": round(overall_accuracy, 1),
        "confidence_distribution": {
            "high": high_conf,
            "mid": mid_conf,
            "low": low_conf
        },
        "details": all_results
    }
    
    # 保存JSON结果
    output_file = OUTPUT_DIR / f"evaluation_results_v5.8_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📁 详细结果已保存到: {output_file}")
    
    return report


if __name__ == "__main__":
    main()