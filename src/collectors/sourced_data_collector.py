"""
@description: 严格数据采集器 - 每项数据必须有出处
@dependencies: requests, beautifulsoup4
@last_modified: 2026-03-16

核心原则：
1. 无来源不写入
2. 来源必须可追溯（URL/文档名）
3. 置信度分级：实测 > 官方 > 媒体 > 推断
"""

import json
import re
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path


class DataSourceType(Enum):
    """数据来源类型"""
    OFFICIAL = "官方数据"      # 官网、官方公告
    ECOMMERCE = "电商平台"     # 京东、天猫商品页
    MEDIA = "媒体报道"         # 新闻、评测文章
    REVIEW = "用户评价"        # 评论区数据
    DATABASE = "数据库"        # 行业数据库
    MANUAL = "人工采集"        # 需人工补充
    INFERRED = "推断数据"      # 禁止使用，仅作标记


@dataclass
class DataPoint:
    """数据点 - 带来源"""
    dimension: str           # 维度名称
    value: Any              # 数据值
    source_type: DataSourceType
    source_url: str         # 来源URL
    source_name: str        # 来源名称
    collected_at: str       # 采集时间
    confidence: str         # 置信度: high/medium/low
    raw_text: str = ""      # 原始文本

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "source": {
                "type": self.source_type.value,
                "url": self.source_url,
                "name": self.source_name
            },
            "collected_at": self.collected_at,
            "confidence": self.confidence,
            "raw_text": self.raw_text[:200] if self.raw_text else ""
        }


@dataclass
class SourcedReport:
    """带来源的报告"""
    subject: str                    # 分析对象
    created_at: str
    data_points: List[DataPoint]
    missing_dimensions: List[str]   # 未采集维度
    blocked_reasons: List[str]      # 阻断原因

    def to_markdown(self) -> str:
        """生成Markdown报告"""
        lines = [
            f"# {self.subject} 竞品分析报告",
            "",
            f"> **生成时间**: {self.created_at}",
            f"> **数据采集原则**: 无来源不写入",
            "",
            "---",
            "",
            "## 数据来源说明",
            "",
            "| 置信度 | 说明 |",
            "|--------|------|",
            "| high | 官方数据/实测 |",
            "| medium | 媒体报道/电商页面 |",
            "| low | 二手引用/需验证 |",
            "",
            "---",
            ""
        ]

        # 按维度输出
        current_category = None
        for dp in self.data_points:
            # 输出数据点
            lines.append(f"### {dp.dimension}")
            lines.append("")
            lines.append(f"| 项目 | 值 | 来源 | 置信度 |")
            lines.append("|------|-----|------|--------|")

            if isinstance(dp.value, dict):
                for k, v in dp.value.items():
                    lines.append(f"| {k} | {v} | [{dp.source_name}]({dp.source_url}) | {dp.confidence} |")
            elif isinstance(dp.value, list):
                for item in dp.value:
                    if isinstance(item, dict):
                        lines.append(f"| {item.get('name', '-')} | {item.get('value', '-')} | [{dp.source_name}]({dp.source_url}) | {dp.confidence} |")
                    else:
                        lines.append(f"| - | {item} | [{dp.source_name}]({dp.source_url}) | {dp.confidence} |")
            else:
                lines.append(f"| 值 | {dp.value} | [{dp.source_name}]({dp.source_url}) | {dp.confidence} |")

            lines.append("")
            lines.append(f"> 原文引用: \"{dp.raw_text[:100]}...\"" if dp.raw_text else "")
            lines.append("")
            lines.append("---")
            lines.append("")

        # 缺失维度
        if self.missing_dimensions:
            lines.append("## 待采集维度")
            lines.append("")
            lines.append("| 维度 | 状态 | 需要操作 |")
            lines.append("|------|------|----------|")
            for dim in self.missing_dimensions:
                lines.append(f"| {dim} | 缺失 | 需人工采集 |")
            lines.append("")

        # 阻断原因
        if self.blocked_reasons:
            lines.append("## 采集阻断原因")
            lines.append("")
            for reason in self.blocked_reasons:
                lines.append(f"- {reason}")
            lines.append("")

        return "\n".join(lines)


class SourcedDataCollector:
    """严格数据采集器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.data_points: List[DataPoint] = []
        self.missing_dimensions: List[str] = []
        self.blocked_reasons: List[str] = []

    def fetch_url(self, url: str) -> Optional[str]:
        """获取URL内容"""
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.text
            else:
                self.blocked_reasons.append(f"URL {url} 返回状态码 {resp.status_code}")
                return None
        except Exception as e:
            self.blocked_reasons.append(f"URL {url} 请求失败: {str(e)}")
            return None

    def add_data_point(self, dimension: str, value: Any, source_type: DataSourceType,
                       source_url: str, source_name: str, confidence: str, raw_text: str = ""):
        """添加数据点"""
        dp = DataPoint(
            dimension=dimension,
            value=value,
            source_type=source_type,
            source_url=source_url,
            source_name=source_name,
            collected_at=datetime.now().isoformat(),
            confidence=confidence,
            raw_text=raw_text
        )
        self.data_points.append(dp)

    def mark_missing(self, dimension: str, reason: str = ""):
        """标记缺失维度"""
        self.missing_dimensions.append(f"{dimension}: {reason}" if reason else dimension)

    def generate_report(self, subject: str) -> SourcedReport:
        """生成报告"""
        return SourcedReport(
            subject=subject,
            created_at=datetime.now().isoformat(),
            data_points=self.data_points,
            missing_dimensions=self.missing_dimensions,
            blocked_reasons=self.blocked_reasons
        )


# === 测试 ===
if __name__ == "__main__":
    collector = SourcedDataCollector()

    # 测试：获取京东商品页
    test_url = "https://item.jd.com/100070432376.html"
    print(f"[TEST] Fetching: {test_url}")
    content = collector.fetch_url(test_url)

    if content:
        print(f"[SUCCESS] Got {len(content)} characters")
        collector.add_data_point(
            dimension="测试数据",
            value="获取成功",
            source_type=DataSourceType.ECOMMERCE,
            source_url=test_url,
            source_name="京东商品页",
            confidence="medium",
            raw_text="测试获取"
        )
    else:
        collector.mark_missing("测试数据", "页面获取失败")

    # 生成报告
    report = collector.generate_report("测试产品")
    print("\n" + report.to_markdown()[:500])