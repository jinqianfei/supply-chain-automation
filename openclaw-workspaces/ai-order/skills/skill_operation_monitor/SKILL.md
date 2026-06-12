# Skill 运营监控方案

## 目标

监控 Skill 上线后用户使用情况，自动化运营分析，总结共性问题，决定 Skill 是否迭代升级。

---

## 核心指标体系

### 1. 使用量指标

| 指标 | 说明 | 统计方式 |
|------|------|---------|
| `daily_orders` | 每日处理订单数 | 计数 |
| `weekly_orders` | 周处理订单数 | 计数 |
| `monthly_orders` | 月处理订单数 | 计数 |
| `peak_hour` | 高峰时段 | 按小时分组 |
| `active_users` | 活跃用户数 | 去重计数 |

### 2. 质量指标

| 指标 | 说明 | 统计方式 |
|------|------|---------|
| `match_rate` | 匹配成功率 | matched / total |
| `avg_confidence` | 平均置信度 | sum(confidence) / total |
| `low_conf_rate` | 低置信度占比 | < 0.8 / total |
| `unmatched_count` | 未匹配商品数 | 计数 |
| `unmatched_types` | 未匹配类型分布 | 分组统计 |

### 3. 用户行为指标

| 指标 | 说明 | 统计方式 |
|------|------|---------|
| `manual_confirm_rate` | 手动确认率 | confirm / total |
| `user_correct_count` | 用户纠正次数 | 计数 |
| `user_skip_count` | 跳过确认次数 | 计数 |
| `avg_session_time` | 平均处理时长 | 时间统计 |

### 4. 失败模式指标

| 指标 | 说明 | 统计方式 |
|------|------|---------|
| `error_types` | 错误类型分布 | 分组计数 |
| `top_unmatched_products` | Top 未匹配商品 | Top 10 |
| `top_unmatched_stores` | Top 未匹配门店 | Top 10 |
| `failure_ reasons` | 失败原因分析 | 归类 |

---

## 数据收集方式

### 方式1：内置日志（推荐）

在 Skill 处理过程中自动记录：

```python
class OperationLogger:
    """运营日志记录器"""

    def __init__(self, log_path: str = None):
        self.log_path = log_path or "data/operation_log.jsonl"

    def log_order(self, order_id: str, result: dict, meta: dict):
        """记录每笔订单处理结果"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "order_id": order_id,
            "success": result.get("matched", False),
            "confidence": result.get("confidence", 0),
            "user_action": result.get("user_action", "auto"),  # auto/confirm/skip/correct
            "sku_code": result.get("sku_code", ""),
            "store_id": meta.get("store_id", ""),
            "item_count": meta.get("item_count", 0),
            "processing_time_ms": meta.get("processing_time_ms", 0),
            "error": result.get("error", ""),
        }
        self._append(self.log_path, entry)

    def _append(self, path: str, entry: dict):
        """追加到 JSONL 文件"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

### 方式2：数据库记录

```sql
-- operation_logs 表
CREATE TABLE operation_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    skill_name VARCHAR(50),
    order_id VARCHAR(100),
    matched BOOLEAN,
    confidence FLOAT,
    user_action VARCHAR(20),  -- auto/confirm/skip/correct
    sku_code VARCHAR(50),
    store_id VARCHAR(50),
    item_count INT,
    processing_time_ms INT,
    error_message TEXT
);
```

---

## 日/周/月报告生成

```python
class OperationReport:
    """运营报告生成器"""

    def __init__(self, skill_name: str, db_config: dict):
        self.skill_name = skill_name
        self.db_config = db_config

    def daily_report(self, date: str = None) -> dict:
        """生成日报"""
        date = date or datetime.now().strftime("%Y-%m-%d")
        data = self._query_logs(date, date)
        return self._build_report(data, "daily")

    def weekly_report(self, week_start: str = None) -> dict:
        """生成周报"""
        # 自动计算上周
        today = datetime.now()
        week_start = week_start or (today - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
        data = self._query_logs(week_start, week_end)
        return self._build_report(data, "weekly")

    def _query_logs(self, start_date: str, end_date: str) -> dict:
        """查询指定日期范围的日志"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN matched THEN 1 ELSE 0 END) as matched,
                AVG(confidence) as avg_conf,
                SUM(CASE WHEN confidence < 0.8 THEN 1 ELSE 0 END) as low_conf,
                COUNT(DISTINCT user_id) as active_users
            FROM operation_logs
            WHERE skill_name = %s
              AND timestamp::date BETWEEN %s AND %s
        """, [self.skill_name, start_date, end_date])
        row = cur.fetchone()
        return {
            "total": row[0],
            "matched": row[1],
            "avg_confidence": row[2] or 0,
            "low_conf_count": row[3],
            "active_users": row[4],
        }

    def _build_report(self, data: dict, period: str) -> dict:
        """构建报告"""
        total = data["total"] or 0
        matched = data["matched"] or 0

        return {
            "period": period,
            "skill_name": self.skill_name,
            "generated_at": datetime.now().isoformat(),
            "total_orders": total,
            "match_rate": f"{matched/total*100:.1f}%" if total > 0 else "0%",
            "avg_confidence": f"{data['avg_confidence']:.2f}",
            "low_conf_rate": f"{data['low_conf_count']/total*100:.1f}%" if total > 0 else "0%",
            "active_users": data["active_users"],
        }
```

---

## 迭代决策引擎

```python
class IterationDecider:
    """
    迭代决策引擎
    根据运营数据判断 Skill 是否需要迭代升级
    """

    # 迭代阈值配置
    THRESHOLDS = {
        "match_rate_warning": 0.85,      # 匹配率 < 85% 警告
        "match_rate_critical": 0.70,     # 匹配率 < 70% 立即优化
        "low_conf_rate_warning": 0.10,   # 低置信度 > 10% 警告
        "user_intervention_rate": 0.20,  # 用户干预 > 20% 需优化体验
        "error_rate_warning": 0.05,      # 错误率 > 5% 警告
        "daily_volume_threshold": 100,   # 日均 < 100 单考虑下线
    }

    def evaluate(self, report: dict) -> dict:
        """
        评估是否需要迭代

        返回决策：
        - immediate_upgrade: 立即升级
        - plan_upgrade: 计划升级
        - monitor: 持续监控
        - consider_deprecate: 考虑下线
        """
        decisions = []
        reasons = []

        # 1. 匹配率检查
        match_rate = self._parse_rate(report.get("match_rate", "0%"))
        if match_rate < self.THRESHOLDS["match_rate_critical"]:
            decisions.append("immediate_upgrade")
            reasons.append(f"匹配率 {match_rate:.1%} < {self.THRESHOLDS['match_rate_critical']:.1%}，严重")
        elif match_rate < self.THRESHOLDS["match_rate_warning"]:
            decisions.append("plan_upgrade")
            reasons.append(f"匹配率 {match_rate:.1%} < {self.THRESHOLDS['match_rate_warning']:.1%}，需优化")

        # 2. 低置信度检查
        low_conf_rate = self._parse_rate(report.get("low_conf_rate", "0%"))
        if low_conf_rate > self.THRESHOLDS["low_conf_rate_warning"]:
            decisions.append("plan_upgrade")
            reasons.append(f"低置信度 {low_conf_rate:.1%} > {self.THRESHOLDS['low_conf_rate_warning']:.1%}")

        # 3. 用户干预率检查
        intervention_rate = self._parse_rate(report.get("user_intervention_rate", "0%"))
        if intervention_rate > self.THRESHOLDS["user_intervention_rate"]:
            decisions.append("plan_upgrade")
            reasons.append(f"用户干预率 {intervention_rate:.1%} > {self.THRESHOLDS['user_intervention_rate']:.1%}，体验需优化")

        # 4. 综合决策
        if "immediate_upgrade" in decisions:
            final_decision = "🔴 立即升级"
        elif "plan_upgrade" in decisions:
            final_decision = "🟡 计划升级"
        elif report.get("total_orders", 0) < self.THRESHOLDS["daily_volume_threshold"]:
            final_decision = "🟠 考虑优化或下线"
            reasons.append("日均订单量过低")
        else:
            final_decision = "🟢 持续监控"
            reasons.append("各项指标正常")

        return {
            "decision": final_decision,
            "decisions": decisions,
            "reasons": reasons,
            "report": report,
        }

    def _parse_rate(self, rate_str: str) -> float:
        """解析百分比字符串"""
        if isinstance(rate_str, float):
            return rate_str
        return float(rate_str.strip("%")) / 100
```

---

## 使用场景

### 场景1：每日自动生成运营报告

```
每天 17:00（下班前）自动生成
→ 金姐查看今日处理了多少单、成功率如何
→ 发现问题立即处理
```

### 场景2：每周迭代决策

```
每周一生成上周运营报告
→ IterationDecider 判断是否需要升级
→ 决定本周工作重点
```

### 场景3：用户反馈驱动迭代

```
某类问题用户反馈 > 10 次/周
→ 自动标记为高优先级修复
→ 触发 Skill 升级流程
```

---

## 文件结构建议

```
skill_operation_monitor/
├── SKILL.md                    # Skill 文档
├── __init__.py                 # 主入口
├── logger.py                   # 日志记录器
├── reporter.py                  # 报告生成器
├── decider.py                   # 迭代决策引擎
├── data/                       # 数据目录
│   └── operation_log.jsonl    # 运营日志
├── docs/                       # 文档
│   ├── 运营报告_YYYYMMDD.md
│   └── 迭代建议_YYYYMMDD.md
└── config/
    └── thresholds.yaml         # 阈值配置
```

---

## 下一步

1. **先跑起来** — 在 `skill_order_to_huading_template` 中加入日志记录
2. **每日报告** — 每天 17:00 自动生成运营报告
3. **迭代决策** — 每周一根据数据决定是否升级

要开始实现吗？