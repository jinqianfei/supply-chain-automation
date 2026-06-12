"""
迭代决策引擎 - 根据运营数据判断 Skill 是否需要迭代升级

使用方式：
    from decider import IterationDecider

    decider = IterationDecider(thresholds_config="config/thresholds.yaml")

    decision = decider.evaluate(report)
    print(decision["decision"])  # 🔴 立即升级 / 🟡 计划升级 / 🟢 持续监控
"""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class IterationDecider:
    """
    迭代决策引擎
    根据运营数据判断 Skill 是否需要迭代升级
    """

    # 默认阈值配置
    DEFAULT_THRESHOLDS = {
        "match_rate_warning": 0.85,       # 匹配率 < 85% 警告
        "match_rate_critical": 0.70,      # 匹配率 < 70% 立即优化
        "low_conf_rate_warning": 0.10,    # 低置信度 > 10% 警告
        "low_conf_rate_critical": 0.20,   # 低置信度 > 20% 严重
        "user_intervention_warning": 0.15,  # 用户干预 > 15% 警告
        "user_intervention_critical": 0.30, # 用户干预 > 30% 严重
        "error_rate_warning": 0.03,        # 错误率 > 3% 警告
        "error_rate_critical": 0.10,      # 错误率 > 10% 严重
        "daily_volume_warning": 10,       # 日均 < 10 单 警告（太低）
        "daily_volume_dead": 3,           # 日均 < 3 单 考虑下线
        "trend_threshold": 0.05,         # 趋势变化阈值（5%）
    }

    def __init__(self, thresholds_config: str = None):
        """初始化决策器"""
        self.thresholds = self.DEFAULT_THRESHOLDS.copy()
        if thresholds_config and Path(thresholds_config).exists():
            with open(thresholds_config) as f:
                config = yaml.safe_load(f)
                if config and "thresholds" in config:
                    self.thresholds.update(config["thresholds"])

    def evaluate(self, report: dict, previous_report: dict = None) -> Dict[str, Any]:
        """
        评估是否需要迭代

        Args:
            report: 当前周期报告
            previous_report: 上一周期报告（用于趋势分析）

        Returns:
            {
                "decision": "🔴 立即升级 | 🟡 计划升级 | 🟠 考虑优化 | 🟢 持续监控",
                "priority": "critical | high | medium | low",
                "reasons": [...],
                "recommendations": [...],
                "metrics_check": {...},
            }
        """
        checks = []
        reasons = []
        recommendations = []
        severity = "low"

        # ============================================================
        # 1. 匹配率检查
        # ============================================================
        match_rate = self._parse_rate(report.get("match_rate", "0%"))
        check = {
            "metric": "match_rate",
            "value": f"{match_rate:.1%}",
            "threshold": self.thresholds["match_rate_critical"],
            "status": "pass",
        }
        if match_rate < self.thresholds["match_rate_critical"]:
            check["status"] = "critical"
            checks.append(check)
            reasons.append(f"匹配率 {match_rate:.1%} 严重低于 {self.thresholds['match_rate_critical']:.1%}")
            recommendations.append("立即优化 SKU 匹配算法")
            severity = "critical"
        elif match_rate < self.thresholds["match_rate_warning"]:
            check["status"] = "warning"
            checks.append(check)
            reasons.append(f"匹配率 {match_rate:.1%} 低于 {self.thresholds['match_rate_warning']:.1%}")
            recommendations.append("计划优化 SKU 匹配算法")
            if severity != "critical":
                severity = "medium"
        else:
            checks.append(check)

        # ============================================================
        # 2. 低置信度检查
        # ============================================================
        low_conf_rate = self._parse_rate(report.get("low_confidence_rate", "0%"))
        check = {
            "metric": "low_confidence_rate",
            "value": f"{low_conf_rate:.1%}",
            "threshold": self.thresholds["low_conf_rate_warning"],
            "status": "pass",
        }
        if low_conf_rate > self.thresholds["low_conf_rate_critical"]:
            check["status"] = "critical"
            checks.append(check)
            reasons.append(f"低置信度 {low_conf_rate:.1%} 超过 {self.thresholds['low_conf_rate_critical']:.1%}")
            recommendations.append("优先解决低置信度商品匹配问题")
            if severity == "low":
                severity = "high"
        elif low_conf_rate > self.thresholds["low_conf_rate_warning"]:
            check["status"] = "warning"
            checks.append(check)
            reasons.append(f"低置信度 {low_conf_rate:.1%} 超过 {self.thresholds['low_conf_rate_warning']:.1%}")
            recommendations.append("关注低置信度商品，优化匹配规则")
            if severity == "low":
                severity = "medium"
        else:
            checks.append(check)

        # ============================================================
        # 3. 用户干预率检查
        # ============================================================
        intervention_rate = self._parse_rate(report.get("intervention_rate", "0%"))
        check = {
            "metric": "user_intervention_rate",
            "value": f"{intervention_rate:.1%}",
            "threshold": self.thresholds["user_intervention_warning"],
            "status": "pass",
        }
        if intervention_rate > self.thresholds["user_intervention_critical"]:
            check["status"] = "critical"
            checks.append(check)
            reasons.append(f"用户干预率 {intervention_rate:.1%} 超过 {self.thresholds['user_intervention_critical']:.1%}")
            recommendations.append("立即优化用户体验，减少手动确认")
            if severity in ("low", "medium"):
                severity = "high"
        elif intervention_rate > self.thresholds["user_intervention_warning"]:
            check["status"] = "warning"
            checks.append(check)
            reasons.append(f"用户干预率 {intervention_rate:.1%} 超过 {self.thresholds['user_intervention_warning']:.1%}")
            recommendations.append("优化操作流程，降低用户干预频率")
            if severity == "low":
                severity = "medium"
        else:
            checks.append(check)

        # ============================================================
        # 4. 趋势分析（如果提供了历史数据）
        # ============================================================
        trend = None
        if previous_report:
            prev_match_rate = self._parse_rate(previous_report.get("match_rate", "0%"))
            trend = match_rate - prev_match_rate
            check = {
                "metric": "match_rate_trend",
                "value": f"{trend:+.1%}",
                "threshold": self.thresholds["trend_threshold"],
                "status": "pass",
            }
            if abs(trend) > self.thresholds["trend_threshold"]:
                if trend < 0:
                    check["status"] = "warning"
                    checks.append(check)
                    reasons.append(f"匹配率下降趋势 {trend:.1%}，需关注")
                    recommendations.append("分析下降原因，及时修复")
                else:
                    check["status"] = "positive"
                    checks.append(check)
            else:
                checks.append(check)

        # ============================================================
        # 5. 处理量检查
        # ============================================================
        total_orders = report.get("total_orders", 0)
        if total_orders < self.thresholds["daily_volume_dead"]:
            reasons.append(f"日均订单量 {total_orders} 过低（< {self.thresholds['daily_volume_dead']}），考虑优化或下线")
            recommendations.append("评估 Skill 价值，考虑优化功能或暂时下线")
            severity = "critical"
        elif total_orders < self.thresholds["daily_volume_warning"]:
            reasons.append(f"日均订单量 {total_orders} 偏低（< {self.thresholds['daily_volume_warning']}）")
            recommendations.append("推广 Skill 使用，增加用户活跃度")

        # ============================================================
        # 综合决策
        # ============================================================
        if severity == "critical":
            decision = "🔴 立即升级"
            priority = "critical"
        elif severity == "high":
            decision = "🟡 计划升级"
            priority = "high"
        elif severity == "medium":
            decision = "🟡 计划升级（中期）"
            priority = "medium"
        elif total_orders < self.thresholds["daily_volume_warning"]:
            decision = "🟠 考虑优化"
            priority = "medium"
            if not reasons:
                reasons.append("日均订单量偏低，建议推广")
        else:
            decision = "🟢 持续监控"
            priority = "low"
            if not reasons:
                reasons.append("各项指标正常，无需特殊处理")

        return {
            "decision": decision,
            "priority": priority,
            "reasons": reasons,
            "recommendations": recommendations,
            "metrics_check": checks,
            "trend": trend,
            "thresholds_used": self.thresholds,
            "evaluated_at": datetime.now().isoformat(),
        }

    def _parse_rate(self, rate_str: str) -> float:
        """解析百分比字符串为浮点数"""
        if isinstance(rate_str, float):
            return rate_str
        if isinstance(rate_str, int):
            return float(rate_str)
        try:
            return float(rate_str.strip("%")) / 100
        except:
            return 0.0

    def generate_recommendation_report(self, decision: dict, report: dict) -> str:
        """生成迭代建议报告（Markdown 格式）"""
        lines = [
            f"# Skill 迭代建议报告",
            f"",
            f"**Skill**: {report.get('skill_name', 'N/A')}",
            f"**报告周期**: {report.get('date_range', 'N/A')}",
            f"**决策**: {decision['decision']}",
            f"**优先级**: {decision['priority']}",
            f"**生成时间**: {decision['evaluated_at']}",
            f"",
            f"## 决策依据",
            f"",
        ]

        for reason in decision["reasons"]:
            lines.append(f"- {reason}")

        lines.extend([
            f"",
            f"## 指标检查",
            f"",
            f"| 指标 | 数值 | 阈值 | 状态 |",
            f"|------|------|------|------|",
        ])

        for check in decision["metrics_check"]:
            status_icon = {
                "pass": "✅",
                "warning": "⚠️",
                "critical": "🔴",
                "positive": "📈",
            }.get(check["status"], check["status"])
            lines.append(
                f"| {check['metric']} | {check['value']} | {check['threshold']} | {status_icon} |"
            )

        lines.extend([
            f"",
            f"## 优化建议",
            f"",
        ])

        for i, rec in enumerate(decision["recommendations"], 1):
            lines.append(f"{i}. {rec}")

        lines.extend([
            f"",
            f"## 下一步行动",
            f"",
        ])

        if decision["priority"] in ("critical", "high"):
            lines.extend([
                f"1. **立即处理** - 召开技术会议讨论优化方案",
                f"2. **制定计划** - 确定优化内容和时间表",
                f"3. **执行修复** - 使用自动化测试+修复工作流",
                f"4. **验证效果** - 修复后复测，确认指标改善",
            ])
        else:
            lines.extend([
                f"1. **持续监控** - 每周检查运营指标",
                f"2. **收集反馈** - 关注用户使用体验",
                f"3. **计划优化** - 下个版本预留优化时间",
            ])

        return "\n".join(lines)