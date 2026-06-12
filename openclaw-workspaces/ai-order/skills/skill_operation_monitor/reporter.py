"""
运营报告生成器 - 日/周/月报告

使用方式：
    from reporter import OperationReporter

    reporter = OperationReporter(
        skill_name="skill_order_to_huading_template",
        log_dir="data"
    )

    # 生成日报
    report = reporter.daily_report()

    # 生成周报
    report = reporter.weekly_report()

    # 生成月报
    report = reporter.monthly_report()
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


class OperationReporter:
    """运营报告生成器"""

    def __init__(self, skill_name: str, log_dir: str = None):
        self.skill_name = skill_name
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent / "data"
        self.log_file = self.log_dir / f"{skill_name}_log.jsonl"

    def daily_report(self, date: str = None) -> Dict[str, Any]:
        """生成日报"""
        date = date or datetime.now().strftime("%Y-%m-%d")
        start = f"{date}T00:00:00"
        end = f"{date}T23:59:59"
        stats = self._query_stats(start, end)
        report = self._build_report(stats, "daily", date)
        self._save_report(report, "daily")
        return report

    def weekly_report(self, week_start: str = None) -> Dict[str, Any]:
        """生成周报"""
        if week_start is None:
            today = datetime.now()
            week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")

        start_dt = datetime.strptime(week_start, "%Y-%m-%d")
        end_dt = start_dt + timedelta(days=6)

        start = start_dt.strftime("%Y-%m-%dT00:00:00")
        end = end_dt.strftime("%Y-%m-%dT23:59:59")

        stats = self._query_stats(start, end)
        report = self._build_report(stats, "weekly", f"{week_start}~{end_dt.strftime('%Y-%m-%d')}")
        self._save_report(report, "weekly")
        return report

    def monthly_report(self, year_month: str = None) -> Dict[str, Any]:
        """生成月报"""
        if year_month is None:
            today = datetime.now()
            year_month = today.strftime("%Y-%m")

        year, month = year_month.split("-")
        start_dt = datetime(int(year), int(month), 1)

        if int(month) == 12:
            end_dt = datetime(int(year) + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_dt = datetime(int(year), int(month) + 1, 1) - timedelta(seconds=1)

        start = start_dt.strftime("%Y-%m-%dT00:00:00")
        end = end_dt.strftime("%Y-%m-%dT23:59:59")

        stats = self._query_stats(start, end)
        report = self._build_report(stats, "monthly", year_month)
        self._save_report(report, "monthly")
        return report

    def _query_stats(self, start_iso: str, end_iso: str) -> Dict[str, Any]:
        """查询指定时间范围的统计数据"""
        if not self.log_file.exists():
            return self._empty_stats()

        stats = self._empty_stats()

        with open(self.log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except:
                    continue

                ts = entry.get("timestamp", "")
                if ts < start_iso or ts > end_iso:
                    continue
                if entry.get("skill_name") != self.skill_name:
                    continue

                stats["total"] += 1
                if entry.get("matched"):
                    stats["matched"] += 1

                conf = entry.get("confidence", 0)
                stats["confidence_sum"] += conf
                if conf < 0.8:
                    stats["low_confidence"] += 1

                stats["processing_time_sum"] += entry.get("processing_time_ms", 0)

                action = entry.get("user_action", "auto")
                stats["actions"][action] = stats["actions"].get(action, 0) + 1

                # 统计未匹配类型
                if not entry.get("matched"):
                    error = entry.get("error", "unknown")
                    stats["error_types"][error] = stats["error_types"].get(error, 0) + 1

                # 统计门店
                store_id = entry.get("store_id", "")
                if store_id:
                    stats["stores"][store_id] = stats["stores"].get(store_id, 0) + 1

        return stats

    def _empty_stats(self) -> Dict[str, Any]:
        """返回空统计数据"""
        return {
            "total": 0,
            "matched": 0,
            "confidence_sum": 0,
            "low_confidence": 0,
            "processing_time_sum": 0,
            "actions": {"auto": 0, "confirm": 0, "skip": 0, "correct": 0},
            "error_types": {},
            "stores": {},
        }

    def _build_report(self, stats: dict, period: str, date_range: str) -> Dict[str, Any]:
        """构建报告"""
        total = stats["total"]
        matched = stats["matched"]

        report = {
            "report_id": f"{self.skill_name}_{period}_{date_range}",
            "generated_at": datetime.now().isoformat(),
            "period": period,
            "date_range": date_range,
            "skill_name": self.skill_name,
            # 核心指标
            "total_orders": total,
            "match_rate": f"{matched/total*100:.1f}%" if total > 0 else "0%",
            "match_rate_value": matched/total if total > 0 else 0,
            "avg_confidence": f"{stats['confidence_sum']/total:.2f}" if total > 0 else "0.00",
            "low_confidence_rate": f"{stats['low_confidence']/total*100:.1f}%" if total > 0 else "0%",
            "avg_processing_time_ms": f"{stats['processing_time_sum']/total:.0f}" if total > 0 else "0",
            # 用户行为
            "user_actions": stats["actions"],
            "auto_rate": f"{stats['actions']['auto']/total*100:.1f}%" if total > 0 else "0%",
            "intervention_rate": f"{(stats['actions']['confirm'] + stats['actions']['correct'])/total*100:.1f}%" if total > 0 else "0%",
            # 问题分布
            "top_error_types": sorted(
                stats["error_types"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "top_stores": sorted(
                stats["stores"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }

        return report

    def _save_report(self, report: dict, period: str):
        """保存报告到文件"""
        reports_dir = self.log_dir.parent / "docs"
        reports_dir.mkdir(parents=True, exist_ok=True)

        date_str = report["date_range"].replace("~", "_").replace("-", "")[:8]
        report_file = reports_dir / f"运营报告_{period}_{date_str}.md"

        md_content = self._build_markdown(report)

        with open(report_file, "w") as f:
            f.write(md_content)

        report["report_file"] = str(report_file)

    def _build_markdown(self, report: dict) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            f"# {self.skill_name} 运营报告",
            f"",
            f"**报告周期**: {report['date_range']}",
            f"**生成时间**: {report['generated_at']}",
            f"",
            f"## 核心指标",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总订单数 | {report['total_orders']} |",
            f"| 匹配成功率 | {report['match_rate']} |",
            f"| 平均置信度 | {report['avg_confidence']} |",
            f"| 低置信度占比 | {report['low_confidence_rate']} |",
            f"| 平均处理时长 | {report['avg_processing_time_ms']} ms |",
            f"",
            f"## 用户行为",
            f"",
            f"| 行为 | 次数 | 占比 |",
            f"|------|------|------|",
        ]

        total = report["total_orders"]
        for action, count in report["user_actions"].items():
            rate = f"{count/total*100:.1f}%" if total > 0 else "0%"
            lines.append(f"| {action} | {count} | {rate} |")

        lines.extend([
            f"",
            f"**自动处理率**: {report['auto_rate']}",
            f"**用户干预率**: {report['intervention_rate']}",
            f"",
        ])

        if report["top_error_types"]:
            lines.extend([
                f"## Top 未匹配错误类型",
                f"",
                f"| 错误类型 | 次数 |",
                f"|------|------|",
            ])
            for error_type, count in report["top_error_types"]:
                lines.append(f"| {error_type} | {count} |")
            lines.append("")

        if report["top_stores"]:
            lines.extend([
                f"## Top 处理门店",
                f"",
                f"| 门店 | 订单数 |",
                f"|------|------|",
            ])
            for store, count in report["top_stores"]:
                lines.append(f"| {store} | {count} |")
            lines.append("")

        return "\n".join(lines)