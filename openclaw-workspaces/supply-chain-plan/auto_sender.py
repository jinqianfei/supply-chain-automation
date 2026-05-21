#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 获客自动化工具 - 主脚本
功能：搜索企业 → 提取联系方式 → 生成邮件 → 发送

使用方法：
    python3 auto_sender.py          # 仅生成草稿
    python3 auto_sender.py --send    # 生成并发送
"""

import os
import sys
import csv
import json
import time
import re
import argparse
import subprocess
from datetime import datetime

# 导入配置
from config import (
    EMAIL_CONFIG, TAVILY_API_KEY, VIDEO_URL,
    EMAIL_TEMPLATE, SEARCH_QUERIES, SKIP_KEYWORDS,
    DRY_RUN, SEND_DELAY, DAILY_LIMIT
)

# ============== 工具函数 ==============

def clean_html(text):
    """清除HTML标签"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('<<<EXTERNAL_UNTRUSTED_CONTENT', '').replace('END_EXTERNAL_UNTRUSTED_CONTENT>>>', '')
    return text.strip()

def clean_company_name(name):
    """清理公司名称"""
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
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    return name.strip()[:40]

def tavily_search(query, max_results=5):
    """Tavily 搜索 API"""
    if not TAVILY_API_KEY:
        print("  ⚠ 未配置 Tavily API Key，跳过搜索")
        return []

    cmd = [
        "curl", "-s", "--max-time", "25",
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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.loads(r.stdout).get("results", [])
    except Exception as e:
        print(f"  搜索失败: {e}")
    return []

def extract_contacts_from_snippet(snippet):
    """从搜索摘要中提取联系方式"""
    email = phone = contact = ""

    # 邮箱
    patterns = [
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        r'邮箱[：:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    ]
    for p in patterns:
        m = re.search(p, snippet)
        if m:
            e = m.group(1) if len(m.groups()) > 0 else m.group(0)
            if "http" not in e and "qq.com" not in e.lower() and len(e) > 5:
                email = e.lower()
                break

    # 电话
    patterns = [
        r'1[3-9]\d{9}',  # 手机
        r'(?:\+86\s?)?0?\d{2,3[)-]\d{7,8}',  # 固话
    ]
    for p in patterns:
        m = re.search(p, snippet)
        if m:
            phone = m.group(0)
            break

    # 联系人
    patterns = [
        r'联系人[：:\s]*([^\s,，。\n]{2,10})',
        r'经理[：:\s]*([^\s,，\n]{2,8})',
    ]
    for p in patterns:
        m = re.search(p, snippet)
        if m:
            contact = m.group(1).strip()[:10]
            if len(contact) >= 2:
                break

    return email, phone, contact

def generate_email_content(company_name, contact="", industry="精密机械零部件"):
    """生成邮件内容"""
    # 提取联系人姓名
    if not contact:
        contact = "您好"

    content = EMAIL_TEMPLATE.format(
        company=company_name,
        industry=industry,
        contact=contact,
        video_url=VIDEO_URL
    )
    return content

def send_email(to_email, subject, body):
    """发送邮件"""
    import smtplib
    import ssl
    from email.mime.text import MIMEText

    context = ssl._create_unverified_context()
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = EMAIL_CONFIG["email"]
    msg['To'] = to_email
    msg['Subject'] = subject

    try:
        with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"],
                             EMAIL_CONFIG["smtp_port"],
                             context=context, timeout=20) as server:
            server.login(EMAIL_CONFIG["email"], EMAIL_CONFIG["password"])
            server.send_message(msg)
        return True, "发送成功"
    except Exception as e:
        return False, str(e)

def is_valid_result(title, url):
    """判断搜索结果是否为目标企业"""
    # 排除包含过滤词的结果
    for kw in SKIP_KEYWORDS:
        if kw in title:
            return False
    # 标题太短不要
    if len(title) < 5:
        return False
    return True

# ============== 主流程 ==============

def search_companies():
    """搜索目标企业"""
    print("\n" + "="*60)
    print("第一步：搜索目标企业")
    print("="*60)

    all_companies = []
    seen_urls = set()
    seen_names = set()

    for i, query in enumerate(SEARCH_QUERIES):
        print(f"\n[{i+1}/{len(SEARCH_QUERIES)}] 搜索: {query}")

        results = tavily_search(query, max_results=8)
        found = 0

        for r in results:
            title = clean_html(r.get("title", ""))
            url = r.get("url", "")
            snippet = clean_html(r.get("snippet", ""))

            if not title or url in seen_urls:
                continue

            if not is_valid_result(title, url):
                continue

            seen_urls.add(url)

            # 提取联系方式
            email, phone, contact = extract_contacts_from_snippet(snippet)

            company = {
                "公司名称": title[:80],
                "行业": "精密机械零部件",
                "规模": "年产值5000万-2亿",
                "联系人": contact,
                "手机": phone,
                "邮箱": email,
                "网址": url[:200],
                "地址": "",
                "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "状态": "待联系" if email else "待补充邮箱",
                "邮件主题": f"关于{clean_company_name(title)}的库存优化建议",
                "邮件内容": ""
            }

            # 去重
            name_key = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title)[:30]
            if name_key not in seen_names:
                seen_names.add(name_key)
                all_companies.append(company)
                found += 1

                marker = "📧" if email else "  "
                print(f"  {marker} {title[:50]}")

        if not found:
            print(f"  ⏭ 未找到新企业")

        time.sleep(1)

    print(f"\n共找到 {len(all_companies)} 家目标企业")

    # 统计
    has_email = [c for c in all_companies if c["邮箱"]]
    print(f"  其中有邮箱: {len(has_email)} 家")
    print(f"  待补充邮箱: {len(all_companies) - len(has_email)} 家")

    return all_companies

def generate_emails(companies):
    """生成邮件内容"""
    print("\n" + "="*60)
    print("第二步：生成个性化邮件")
    print("="*60)

    for company in companies:
        if company.get("邮箱") and not company.get("邮件内容"):
            company["邮件内容"] = generate_email_content(
                company["公司名称"],
                company["联系人"],
                company["行业"]
            )
            print(f"  ✓ {clean_company_name(company['公司名称'])}")

def save_draft(companies):
    """保存邮件草稿"""
    print("\n" + "="*60)
    print("第三步：保存邮件草稿")
    print("="*60)

    os.makedirs("outputs", exist_ok=True)
    filepath = f"outputs/draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "公司名称", "行业", "规模", "联系人", "手机", "邮箱",
            "网址", "地址", "搜索时间", "状态", "邮件主题", "邮件内容"
        ])
        writer.writeheader()
        for company in companies:
            writer.writerow(company)

    print(f"  已保存: {filepath}")
    return filepath

def send_emails(companies):
    """发送邮件"""
    print("\n" + "="*60)
    print("第四步：发送邮件")
    print("="*60)

    to_send = [c for c in companies if c.get("邮箱")]
    print(f"  共 {len(to_send)} 封邮件待发送")
    print(f"  发送上限: {DAILY_LIMIT} 封/天")

    success = 0
    failed = 0

    for i, company in enumerate(to_send[:DAILY_LIMIT]):
        print(f"\n[{i+1}/{len(to_send)}] {clean_company_name(company['公司名称'])}")
        print(f"  → {company['邮箱']}")

        ok, msg = send_email(
            company["邮箱"],
            company["邮件主题"],
            company["邮件内容"]
        )

        if ok:
            print(f"  ✅ 发送成功")
            company["状态"] = "已发送"
            success += 1
        else:
            print(f"  ❌ 失败: {msg}")
            company["状态"] = f"发送失败"
            failed += 1

        time.sleep(SEND_DELAY)

    print(f"\n发送完成: ✅ {success} 成功 | ❌ {failed} 失败")

def main():
    parser = argparse.ArgumentParser(description='AI 获客自动化工具')
    parser.add_argument('--send', action='store_true', help='生成后立即发送')
    parser.add_argument('--limit', type=int, default=DAILY_LIMIT, help=f'发送数量上限 (默认{DAILY_LIMIT})')
    args = parser.parse_args()

    print("\n" + "="*60)
    print("🤖 AI 获客自动化工具 v1.0")
    print("="*60)

    # 第一步：搜索
    companies = search_companies()

    if not companies:
        print("\n⚠️ 未找到任何企业，请检查搜索配置")
        return

    # 第二步：生成邮件
    generate_emails(companies)

    # 第三步：保存草稿
    filepath = save_draft(companies)

    # 第四步：发送
    if args.send:
        if DRY_RUN:
            print("\n⚠️ 当前为演示模式，实际发送已禁用")
            print("  如需发送，请修改 config.py 中的 DRY_RUN = False")
        else:
            send_emails(companies)

    # 预览
    has_email = [c for c in companies if c.get("邮箱")]
    if has_email:
        print("\n" + "="*60)
        print("邮件预览（前3封）:")
        print("="*60)
        for c in has_email[:3]:
            print(f"\n--- {clean_company_name(c['公司名称'])} ---")
            print(f"收件人: {c['邮箱']}")
            print(f"主题: {c['邮件主题']}")
            print(f"正文:\n{c['邮件内容'][:150]}...")

    print("\n" + "="*60)
    print("✅ 完成！")
    print(f"📁 草稿已保存到: {filepath}")
    print("="*60)

if __name__ == "__main__":
    main()
