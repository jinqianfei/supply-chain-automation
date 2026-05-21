#!/usr/bin/env python3
"""
批量发送冷启动邮件 - 读取CSV并发送
"""
import smtplib
import ssl
import csv
import time
from email.mime.text import MIMEText

# ============== 配置 ==============
EMAIL_CONFIG = {
    "smtp_server": "smtp.163.com",
    "smtp_port": 465,
    "email": "17621670711@163.com",
    "password": "TDTyLwbNx9Af3fNB"
}

CSV_FILE = "outputs/target_companies.csv"
# ==================================

def send_email(to_email, subject, body):
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
    print("=" * 60)
    print("批量发送冷启动邮件")
    print("=" * 60)
    
    # 读取CSV
    companies = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)
    
    print(f"\n共读取 {len(companies)} 家企业\n")
    
    success = 0
    failed = 0
    
    for i, company in enumerate(companies):
        email = company.get("邮箱", "").strip()
        name = company.get("公司名称", "未知公司")
        
        if not email:
            print(f"[{i+1}/{len(companies)}] ⏭ 跳过 {name}（无邮箱）")
            continue
        
        subject = company.get("邮件主题", f"关于{name}的库存优化建议")
        body = company.get("邮件内容", "")
        
        print(f"[{i+1}/{len(companies)}] 发送: {name} → {email}")
        
        ok, msg = send_email(email, subject, body)
        
        if ok:
            print(f"  ✅ 成功")
            success += 1
        else:
            print(f"  ❌ 失败: {msg}")
            failed += 1
        
        time.sleep(3)  # 避免频率过高
    
    print("\n" + "=" * 60)
    print(f"发送完成: ✅ {success} 封 | ❌ {failed} 封 | 共 {len(companies)} 家")
    print("=" * 60)

if __name__ == "__main__":
    main()
