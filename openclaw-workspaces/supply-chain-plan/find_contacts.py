#!/usr/bin/env python3
"""
方案B v2：精准补搜联系方式
清理公司名 + 改进搜索策略
"""

import csv
import json
import time
import subprocess
import re
from datetime import datetime

TAVILY_API_KEY = "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"
INPUT_CSV = "outputs/target_companies_v3.csv"
OUTPUT_CSV = "outputs/target_companies_v3_with_contacts.csv"

def clean_company_name(raw_name):
    """清理公司名：去掉1688/百度等后缀，只保留公司名"""
    # 去掉常见后缀
    suffixes = [
        r'-企业信息查询黄页-阿里巴巴.*$',
        r'-批发价格-优质货源-?.*$',
        r'-百度爱采购.*$',
        r'-中国制造网.*$',
        r'_.*阿里巴巴.*$',
        r'公司介绍-联系方式.*$',
        r'联系方式.*$',
        r'-.*官网$',
    ]
    name = raw_name
    for suffix in suffixes:
        name = re.sub(suffix, '', name)

    # 只保留前30个字符（中英文混合）
    name = name.strip()[:30]
    return name

def clean_html(text):
    """清除HTML标签"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('<<<EXTERNAL_UNTRUSTED_CONTENT', '').replace('END_EXTERNAL_UNTRUSTED_CONTENT>>>', '')
    return text.strip()

def search_contact_info(company_name, max_results=5):
    """搜索企业联系方式 - 多种查询词"""
    results = []

    queries = [
        f'"{company_name}" 官网 联系方式',
        f'"{company_name}" 邮箱 电话',
        f'"{company_name}" 联系人',
    ]

    for query in queries:
        cmd = [
            "curl", "-s", "--max-time", "30",
            "-X", "POST", "https://api.tavily.com/search",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "query": query,
                "api_key": TAVILY_API_KEY,
                "max_results": max_results,
                "include_answer": False
            })
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                results.extend(data.get("results", []))
        except:
            pass

        time.sleep(0.5)

    return results

def extract_contact_from_results(results):
    """从搜索结果中提取联系方式"""
    email = ""
    phone = ""
    contact = ""

    for r in results:
        snippet = clean_html(r.get("snippet", ""))
        url = r.get("url", "")

        # 跳过非官网链接（减少噪音）
        skip_urls = ["1688.com", "b2b.baidu", "made-in-china", "china.cn",
                     "youhui", "map", "baike", "wikipedia", "tieba"]
        if any(s in url.lower() for s in skip_urls):
            continue

        # 邮箱 - 多种模式
        if not email:
            email_patterns = [
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                r'邮箱[：:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            ]
            for pattern in email_patterns:
                matches = re.findall(pattern, snippet)
                for e in matches:
                    if "http" not in e and len(e) > 5:
                        email = e.lower()
                        break
                if email:
                    break

        # 电话
        if not phone:
            phone_patterns = [
                r'(?:1[3-9]\d{9})',  # 手机号
                r'(?:电话[：:\s]*)(1[3-9]\d{9}|(?:\+86\s?)?0?\d{2,3[)-]\d{7,8})',
                r'(?:\+86\s?)?0?\d{2,3[)-]\d{7,8}',  # 固话
            ]
            for pattern in phone_patterns:
                match = re.search(pattern, snippet)
                if match:
                    phone = match.group(0)
                    break

        # 联系人
        if not contact:
            contact_patterns = [
                r'联系人[：:\s]*([^\s,，。\n]{2,10})',
                r'联系人：\s*([^\s，,。\n]{2,10})',
                r'经理[：:\s]*([^\s,，\n]{2,8})',
                r'先生[，,]?\s*(?:电话|手机)',
                r'女士[，,]?\s*(?:电话|手机)',
                r'联系人：\s*([A-Za-z\u4e00-\u9fa5]{2,8})',
            ]
            for pattern in contact_patterns:
                match = re.search(pattern, snippet)
                if match:
                    contact = match.group(1).strip()[:10]
                    if len(contact) >= 2:
                        break

    return email, phone, contact

def main():
    print("=" * 70)
    print("方案B v2：精准补搜联系方式")
    print("=" * 70)

    # 读取企业名单
    companies = []
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)

    print(f"\n共 {len(companies)} 家企业待处理")

    # 处理前20家
    batch = companies[:20]
    print(f"本次处理前 {len(batch)} 家\n")

    success_email = 0
    success_phone = 0
    success_contact = 0

    for i, company in enumerate(batch):
        raw_name = company["公司名称"]
        clean_name = clean_company_name(raw_name)

        print(f"[{i+1}/{len(batch)}] 搜索: {clean_name}")

        results = search_contact_info(clean_name)
        email, phone, contact = extract_contact_from_results(results)

        if email:
            company["邮箱"] = email
            success_email += 1
            print(f"  📧 {email}")
        if phone:
            company["手机"] = phone
            success_phone += 1
            print(f"  📱 {phone}")
        if contact:
            company["联系人"] = contact
            success_contact += 1
            print(f"  👤 {contact}")

        if not email and not phone:
            print(f"  ⏭ 未找到")

        time.sleep(1)

    # 保存
    print(f"\n{'=' * 70}")
    print(f"补搜完成: 邮箱+{success_email} 电话+{success_phone} 联系人+{success_contact}")

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "公司名称", "行业", "规模", "联系人", "手机", "邮箱",
            "网址", "地址", "搜索时间", "状态", "邮件主题", "邮件内容"
        ])
        writer.writeheader()
        for company in companies:
            writer.writerow(company)

    print(f"已保存到: {OUTPUT_CSV}")

    # 有邮箱的
    has_email = [c for c in companies if c.get("邮箱")]
    print(f"\n已有邮箱: {len(has_email)} 家")
    for c in has_email:
        print(f"  {clean_company_name(c['公司名称'])[:30]} → {c['邮箱']}")

if __name__ == "__main__":
    main()