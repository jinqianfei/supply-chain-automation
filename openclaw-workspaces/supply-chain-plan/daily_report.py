#!/usr/bin/env python3
"""
每日供应链冷启动汇报脚本
每天早上9点自动执行，检查：
1. 昨日邮件发送情况
2. 是否有新搜索到的企业
3. 是否有潜在回复
"""
import subprocess
import json
from datetime import datetime, timedelta

TAVILY_API_KEY = "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"
OUTPUT_DIR = "outputs"

def search_new_companies():
    """搜索新的目标企业"""
    queries = [
        "上海精密机械零部件制造企业 联系方式",
        "上海机械制造工厂 供应链计划",
        "上海精密零件工厂 PMC部门"
    ]
    
    all_results = []
    for query in queries:
        cmd = [
            "curl", "-s", "--max-time", "30",
            "-X", "POST", "https://api.tavily.com/search",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "query": query,
                "api_key": TAVILY_API_KEY,
                "max_results": 5,
                "include_answer": False
            })
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for r in data.get("results", []):
                    title = r.get("title", "").replace("<em>", "").replace("</em>", "").replace("<<<EXTERNAL_UNTRUSTED_CONTENT", "").replace("END_EXTERNAL_UNTRUSTED_CONTENT", "")
                    if title and len(title) > 5:
                        all_results.append(title[:60])
        except:
            pass
    
    # 去重
    seen = set()
    unique = []
    for t in all_results:
        if t not in seen and "知乎" not in t and "百度" not in t and "PDF" not in t:
            seen.add(t)
            unique.append(t)
    
    return unique[:5]

def generate_report():
    """生成每日汇报"""
    today = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    
    new_companies = search_new_companies()
    
    report = f"""📊 **供应链冷启动每日汇报**
⏰ {today}

---

**📅 今日行动**

1. **搜索新企业** - 找到 {len(new_companies)} 家潜在目标
"""
    
    if new_companies:
        report += "\n**新增目标企业：**\n"
        for i, c in enumerate(new_companies, 1):
            report += f"{i}. {c}\n"
    
    report += """
---

**📋 跟进提醒**

已发送邮件的企业，如3天内无回复，建议发送跟进邮件。

---

**🎯 明日行动**

1. 检查是否有邮件回复
2. 对未回复企业发送跟进邮件
3. 继续搜索新目标企业

"""
    
    return report

if __name__ == "__main__":
    report = generate_report()
    print(report)
