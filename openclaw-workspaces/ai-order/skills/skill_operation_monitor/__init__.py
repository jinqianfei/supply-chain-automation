"""
Skill 运营监控模块

监控 Skill 上线后用户使用情况，自动化运营分析，总结共性问题，决定 Skill 是否迭代升级。

使用方式：
    from skill_operation_monitor import OperationMonitor

    monitor = OperationMonitor(
        skill_name="skill_order_to_huading_template",
        log_dir="data",
        thresholds_config="config/thresholds.yaml",
    )

    # 记录处理结果
    monitor.log_order(...)

    # 生成日报
    report = monitor.daily_report()

    # 生成迭代建议
    decision = monitor.evaluate_and_decide(report)
"""

from .logger import OperationLogger
from .reporter import OperationReporter
from .decider import IterationDecider

import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class OperationMonitor:
    """
    Skill 运营监控主类

    整合日志记录、报告生成、迭代决策
    """

    def __init__(
        self,
        skill_name: str,
        log_dir: str = None,
        thresholds_config: str = None,
    ):
        self.skill_name = skill_name

        # 日志记录器
        self.logger = OperationLogger(skill_name=skill_name, log_dir=log_dir)

        # 报告生成器
        self.reporter = OperationReporter(skill_name=skill_name, log_dir=log_dir)

        # 迭代决策器
        self.decider = IterationDecider(thresholds_config=thresholds_config)

    def log_order(self, order_id: str, result: dict, meta: dict):
        """记录单笔订单处理结果"""
        return self.logger.log_order(order_id, result, meta)

    def daily_report(self, date: str = None) -> Dict[str, Any]:
        """生成日报"""
        return self.reporter.daily_report(date=date)

    def weekly_report(self, week_start: str = None) -> Dict[str, Any]:
        """生成周报"""
        return self.reporter.weekly_report(week_start=week_start)

    def monthly_report(self, year_month: str = None) -> Dict[str, Any]:
        """生成月报"""
        return self.reporter.monthly_report(year_month=year_month)

    def evaluate(
        self,
        report: dict,
        previous_report: dict = None,
    ) -> Dict[str, Any]:
        """评估报告，生成迭代决策"""
        return self.decider.evaluate(report, previous_report)

    def daily_routine(self):
        """
        每日运营 routine

        1. 生成昨日日报
        2. 评估是否需要迭代
        3. 生成迭代建议报告
        4. 输出关键指标摘要
        """
        import sys
        from pathlib import Path

        # 生成昨日日报
        yesterday = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f"每日运营 routine - {self.skill_name}")
        print(f"{'='*60}")
        print(f"生成日期: {yesterday}")

        # 日报
        report = self.reporter.daily_report(yesterday)
        print(f"\n📊 日报摘要:")
        print(f"  总订单数: {report['total_orders']}")
        print(f"  匹配成功率: {report['match_rate']}")
        print(f"  平均置信度: {report['avg_confidence']}")
        print(f"  用户干预率: {report['intervention_rate']}")

        # 迭代决策
        decision = self.decider.evaluate(report)
        print(f"\n🎯 迭代决策: {decision['decision']}")

        if decision["reasons"]:
            print(f"  原因:")
            for reason in decision["reasons"]:
                print(f"    - {reason}")

        if decision["recommendations"]:
            print(f"  建议:")
            for rec in decision["recommendations"]:
                print(f"    - {rec}")

        # 生成迭代建议报告
        if decision["priority"] in ("critical", "high", "medium"):
            report_path = Path(__file__).parent / "docs" / f"迭代建议_{yesterday}.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)

            report_md = self.decider.generate_recommendation_report(decision, report)
            with open(report_path, "w") as f:
                f.write(report_md)

            print(f"\n📄 迭代建议报告: {report_path}")
            print(f"   报告文件: {report.get('report_file', 'N/A')}")

        return {
            "report": report,
            "decision": decision,
        }

    def weekly_routine(self):
        """每周运营 routine"""
        print(f"\n{'='*60}")
        print(f"每周运营 routine - {self.skill_name}")
        print(f"{'='*60}")

        # 生成上周周报
        report = self.weekly_report()

        print(f"\n📊 周报摘要:")
        print(f"  周期: {report['date_range']}")
        print(f"  总订单数: {report['total_orders']}")
        print(f"  匹配成功率: {report['match_rate']}")
        print(f"  平均置信度: {report['avg_confidence']}")

        # 迭代决策
        decision = self.decider.evaluate(report)

        print(f"\n🎯 迭代决策: {decision['decision']}")
        print(f"   优先级: {decision['priority']}")

        if decision["reasons"]:
            print(f"  原因:")
            for reason in decision["reasons"]:
                print(f"    - {reason}")

        return {
            "report": report,
            "decision": decision,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Skill 运营监控")
    parser.add_argument("--skill-name", required=True, help="Skill 名称")
    parser.add_argument("--log-dir", help="日志目录")
    parser.add_argument("--thresholds", help="阈值配置文件")
    parser.add_argument("--action", choices=["log", "daily", "weekly", "evaluate"],
                        default="daily", help="操作")
    parser.add_argument("--date", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--order-id", help="订单ID (log 模式)")
    parser.add_argument("--result-json", help="结果 JSON (log 模式)")
    parser.add_argument("--meta-json", help="元数据 JSON (log 模式)")

    args = parser.parse_args()

    monitor = OperationMonitor(
        skill_name=args.skill_name,
        log_dir=args.log_dir,
        thresholds_config=args.thresholds,
    )

    if args.action == "log":
        import json
        result = json.loads(args.result_json or "{}")
        meta = json.loads(args.meta_json or "{}")
        monitor.log_order(args.order_id, result, meta)
        print(f"✅ 记录成功: {args.order_id}")

    elif args.action == "daily":
        result = monitor.daily_routine()
        print(f"\n✅ 日报生成完成")

    elif args.action == "weekly":
        result = monitor.weekly_routine()
        print(f"\n✅ 周报生成完成")

    elif args.action == "evaluate":
        # 从报告文件评估
        reports_dir = Path(__file__).parent / "docs"
        report_files = sorted(reports_dir.glob("运营报告_*.md"))
        if report_files:
            latest = report_files[-1]
            import re
            with open(latest) as f:
                content = f.read()
            # 简单解析
            match_rate = re.search(r"匹配成功率\s*\|\s*([0-9.]+)%", content)
            total = re.search(r"总订单数\s*\|\s*([0-9]+)", content)
            report = {
                "skill_name": args.skill_name,
                "match_rate": f"{float(match_rate.group(1))}%" if match_rate else "0%",
                "total_orders": int(total.group(1)) if total else 0,
            }
            decision = monitor.evaluate(report)
            print(f"决策: {decision['decision']}")
            for reason in decision["reasons"]:
                print(f"  - {reason}")


if __name__ == "__main__":
    main()