#!/usr/bin/env python3
"""
供应链冷启动邮件自动化工具 v4
优化：使用 Tavily Extract API 逐个访问企业官网提取联系方式
"""

import smtplib
import ssl
import csv
import json
import time
import subprocess
import re
from email.mime.text import MIMEText
from datetime import datetime

# ============== 配置区 ==============
EMAIL_CONFIG = {
    "smtp_server": "smtp.163.com",
    "smtp_port": 465,
    "email": "17621670711@163.com",
    "password": "TDTyLwbNx9Af3fNB"
}

TAVILY_API_KEY = "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"
VIDEO_URL = "https://my.feishu.cn/file/KirAbxWAJoq78Vx07P6cT27Inkd"

INPUT_CSV = "outputs/target_companies_v3.csv"
OUTPUT_CSV = "outputs/target_companies_final.csv"
OUTPUT_DIR = "outputs"
# ====================================

def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('<<<EXTERNAL_UNTRUSTED_CONTENT', '').replace('END_EXTERNAL_UNTRUSTED_CONTENT>>>', '')
    return text.strip()

def clean_company_name(name):
    """清理公司名"""
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
    return name.strip()[:30]

def tavily_search(query, max_results=5):
    """Tavily Search API"""
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
    except:
        pass
    return []

def tavily_extract(url, query="公司名称 联系人 电话 邮箱"):
    """Tavily Extract API - 直接访问网页提取内容"""
    cmd = [
        "curl", "-s", "--max-time", "30",
        "-X", "POST", "https://api.tavily.com/extract",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({
            "urls": [url],
            "query": query,
            "api_key": TAVILY_API_KEY
        })
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            results = data.get("results", [])
            if results:
                return results[0].get("raw_content", "")
    except:
        pass
    return ""

def extract_contacts(text):
    """从文本中提取联系方式"""
    email = phone = contact = ""

    # 邮箱
    patterns = [
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        r'邮箱[：:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            e = m.group(1) if len(m.groups()) > 0 else m.group(0)
            if "http" not in e and "qq.com" not in e.lower() and len(e) > 5:
                email = e.lower()
                break

    # 电话
    patterns = [
        r'1[3-9]\d{9}',  # 手机
        r'(?:电话[：:\s]*)(1[3-9]\d{9}|(?:\+86\s?)?0?\d{2,3[)-]\d{7,8})',
        r'(?:\+86\s?)?0?\d{2,3[)-]\d{7,8}',  # 固话
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            phone = m.group(0)
            break

    # 联系人
    patterns = [
        r'联系人[：:\s]*([^\s,，。\n]{2,10})',
        r'联系人：\s*([A-Za-z\u4e00-\u9fa5]{2,8})',
        r'经理[：:\s]*([^\s,，\n]{2,8})',
        r'先生[，,]?\s*(?:电话|手机)',
        r'女士[，,]?\s*(?:电话|手机)',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            contact = m.group(1).strip()[:10]
            if len(contact) >= 2:
                break

    return email, phone, contact

def generate_email_content(company_name, industry="精密机械零部件制造"):
    """生成邮件内容"""
    return f"""您好，冒昧打扰。

我注意到贵司主营{industry}，想请教一个计划部门常见的问题：你们的MRP运算后，是否经常出现"系统建议买多了"或者"该买的没买到"的情况？

我最近用AI供应链计划工具帮几家类似规模的工厂做了库存诊断，发现一个普遍现象：安全库存水位往往比实际需求虚高20%-30%，导致大量资金压在库存上。

不知道您这边有没有兴趣做一次免费的库存健康诊断？大概需要您提供近3个月的销售数据和BOM（脱敏处理），2天内给您一份15页的诊断报告。

如果有兴趣，我可以发一份样例报告给您参考。您也可以先看看这个演示视频，了解一下工具的效果：
{VIDEO_URL}

祝好"""

def send_email(to_email, subject, body):
    """发送邮件"""
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

def main():
    print("=" * 70)
    print("供应链冷启动邮件自动化工具 v4 - Tavily Extract版")
    print("=" * 70)

    # 读取企业名单
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        companies = list(csv.DictReader(f))

    print(f"\n共 {len(companies)} 家企业待处理")
    print("使用 Tavily Extract API 逐个访问官网提取联系方式\n")

    new_email = 0
    new_phone = 0
    new_contact = 0
    processed = 0

    for i, company in enumerate(companies):
        # 跳过已有邮箱的
        if company.get("邮箱"):
            continue

        raw_name = company["公司名称"]
        clean_name = clean_company_name(raw_name)

        print(f"[{i+1}/{len(companies)}] {clean_name}")

        # Step 1: 搜索官网
        results = tavily_search(f'"{clean_name}" 官网')
        official_url = ""
        for r in results:
            url = r.get("url", "").lower()
            # 优先选官网
            if "1688" not in url and "made-in-china" not in url and "b2b.baidu" not in url:
                official_url = r.get("url", "")
                break

        if not official_url:
            # 如果没找到官网，试试第一个结果
            if results:
                official_url = results[0].get("url", "")

        if not official_url:
            print(f"  ⏭ 未找到官网")
            continue

        print(f"  🔗 {official_url[:60]}")

        # Step 2: 用 Tavily Extract 提取网页内容
        content = tavily_extract(official_url)

        if not content:
            print(f"  ⏭ 页面无法访问")
            time.sleep(1)
            continue

        # Step 3: 从内容中提取联系方式
        email, phone, contact = extract_contacts(content)

        if email:
            company["邮箱"] = email
            new_email += 1
            print(f"  📧 {email}")
        if phone:
            company["手机"] = phone
            new_phone += 1
            print(f"  📱 {phone}")
        if contact:
            company["联系人"] = contact
            new_contact += 1
            print(f"  👤 {contact}")

        if not email:
            print(f"  ⏭ 未找到邮箱")

        processed += 1

        # 每处理5个暂停一下，避免API限制
        if processed % 5 == 0:
            print(f"\n  ... 已处理 {processed} 家，暂停2秒 ...")
            time.sleep(2)

        time.sleep(1.5)

    # 生成邮件内容
    print(f"\n生成邮件内容...")
    for company in companies:
        if company.get("邮箱") and not company.get("邮件内容"):
            company["邮件内容"] = generate_email_content(company["公司名称"])
            company["邮件主题"] = f"关于{clean_company_name(company['公司名称'])}的库存优化建议"

    # 保存
    print(f"保存结果...")
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "公司名称", "行业", "规模", "联系人", "手机", "邮箱",
            "网址", "地址", "搜索时间", "状态", "邮件主题", "邮件内容"
        ])
        writer.writeheader()
        for company in companies:
            writer.writerow(company)

    # 统计
    has_email = [c for c in companies if c.get("邮箱")]
    print(f"\n{'=' * 70}")
    print(f"完成! 新增邮箱: {new_email} | 电话: {new_phone} | 联系人: {new_contact}")
    print(f"总计有邮箱的企业: {len(has_email)} 家")
    print(f"结果已保存到: {OUTPUT_CSV}")

    # 预览
    if has_email:
        print(f"\n{'=' * 70}")
        print("有邮箱的企业:")
        print("=" * 70)
        for c in has_email[:10]:
            print(f"  {clean_company_name(c['公司名称'])[:35]} → {c['邮箱']}")

if __name__ == "__main__":
    main()