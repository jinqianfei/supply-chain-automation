#!/usr/bin/env python3
"""
补发邮件：给已联系企业发送演示视频链接
"""
import smtplib
import ssl
import time

EMAIL_CONFIG = {
    "smtp_server": "smtp.163.com",
    "smtp_port": 465,
    "email": "17621670711@163.com",
    "password": "TDTyLwbNx9Af3fNB"
}

VIDEO_URL = "https://my.feishu.cn/file/KirAbxWAJoq78Vx07P6cT27Inkd"

companies = [
    {"name": "上海温莎精密机械元件制造有限公司", "email": "david@wensha.com"},
    {"name": "阿科岚德（上海）精密机械有限公司", "email": "sales07@akland-pmc.com"},
    {"name": "上海翼联精密机械制造有限公司", "email": "sshyljx@vip.163.com"},
    {"name": "上海任和精密机械制造有限公司", "email": "zxh199123@163.com"},
    {"name": "上海汉虹精密机械有限公司", "email": "sales@hanhong.sh.cn"},
    {"name": "上海欧野精工机械有限公司", "email": "ouyejg@vip.163.com"},
    {"name": "萨驰机械工程（上海）有限公司", "email": "dingzhiying@safe-run.cn"},
]

def send_followup(to_email, company_name):
    """发送演示视频链接"""
    body = f"""您好，

补充一下，刚才给您发的邮件里提到了一个演示视频，您可以先看看效果：
{VIDEO_URL}

方便的话可以先了解一下，如果您有任何问题或兴趣，随时联系我。

祝好"""

    subject = f"补充：{company_name} - AI供应链计划工具演示视频"

    context = ssl._create_unverified_context()
    from email.mime.text import MIMEText

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
    print("补发演示视频链接邮件")
    print("=" * 60)

    success = 0
    for i, company in enumerate(companies):
        print(f"[{i+1}/{len(companies)}] 发送: {company['name']} → {company['email']}")
        ok, msg = send_followup(company['email'], company['name'])
        if ok:
            print(f"  ✅ 成功")
            success += 1
        else:
            print(f"  ❌ 失败: {msg}")
        time.sleep(3)

    print(f"\n补发完成: ✅ {success}/{len(companies)} 封")

if __name__ == "__main__":
    main()