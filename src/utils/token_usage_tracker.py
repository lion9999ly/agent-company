"""
@description: Token使用统计模块 - 记录和统计各模型API调用情况
@dependencies: json, datetime
@last_modified: 2026-03-17
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
import threading


@dataclass
class UsageRecord:
    """单次使用记录"""
    timestamp: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    task_type: str = "general"
    success: bool = True
    latency_ms: int = 0
    cost_estimate: float = 0.0


@dataclass
class DailySummary:
    """每日汇总"""
    date: str
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    by_model: Dict[str, Dict] = field(default_factory=dict)
    by_provider: Dict[str, Dict] = field(default_factory=dict)


class TokenUsageTracker:
    """
    Token使用追踪器

    功能：
    1. 记录每次API调用的token使用
    2. 按天/模型/提供商统计
    3. 计算成本估算
    4. 支持导出报告
    """

    # 各模型每1K token的估算成本(美元)
    PRICING = {
        # Gemini
        "gemini-2.5-flash": {"input": 0.000, "output": 0.000},  # 免费层
        "gemini-2.5-flash-lite": {"input": 0.000, "output": 0.000},
        "gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
        "gemini-3-pro-preview": {"input": 0.00125, "output": 0.005},
        "deep-research-pro-preview-12-2025": {"input": 0.002, "output": 0.008},

        # Azure OpenAI
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "o3-mini": {"input": 0.0011, "output": 0.0044},
        "o1": {"input": 0.015, "output": 0.06},

        # Qwen
        "qwen-max": {"input": 0.0008, "output": 0.002},
        "qwen-plus": {"input": 0.0004, "output": 0.001},
    }

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / ".ai-state" / "usage_logs"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.records_file = self.data_dir / "usage_records.jsonl"
        self.summary_file = self.data_dir / "daily_summary.json"

        self._lock = threading.Lock()

        # 内存缓存
        self._records: List[UsageRecord] = []
        self._load_today_records()

    def _load_today_records(self):
        """加载今天的记录到内存"""
        if not self.records_file.exists():
            return

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            with open(self.records_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get('timestamp', '').startswith(today):
                            self._records.append(UsageRecord(**data))
        except Exception:
            pass

    def record(self, model: str, provider: str, prompt_tokens: int,
               completion_tokens: int, task_type: str = "general",
               success: bool = True, latency_ms: int = 0) -> UsageRecord:
        """
        记录一次API调用

        Args:
            model: 模型名称
            provider: 提供商
            prompt_tokens: 输入token数
            completion_tokens: 输出token数
            task_type: 任务类型
            success: 是否成功
            latency_ms: 延迟毫秒

        Returns:
            使用记录
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            task_type=task_type,
            success=success,
            latency_ms=latency_ms,
            cost_estimate=cost
        )

        with self._lock:
            self._records.append(record)
            self._append_record(record)

        return record

    def _estimate_cost(self, model: str, prompt_tokens: int,
                       completion_tokens: int) -> float:
        """估算成本"""
        # 尝试匹配模型定价
        base_model = model.split('-preview')[0].split('-lite')[0]
        pricing = self.PRICING.get(model) or self.PRICING.get(base_model) or {"input": 0, "output": 0}

        input_cost = (prompt_tokens / 1000) * pricing["input"]
        output_cost = (completion_tokens / 1000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    def _append_record(self, record: UsageRecord):
        """追加记录到文件"""
        try:
            with open(self.records_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + '\n')
        except Exception:
            pass

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取统计报告

        Args:
            days: 统计天数

        Returns:
            统计报告
        """
        now = datetime.now()
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")

        # 从文件读取所有记录
        all_records = []
        if self.records_file.exists():
            with open(self.records_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get('timestamp', '').split('T')[0] >= start_date:
                            all_records.append(UsageRecord(**data))

        # 合并内存中的记录
        for r in self._records:
            if r not in all_records:
                all_records.append(r)

        # 按日期分组
        by_date: Dict[str, DailySummary] = {}
        for r in all_records:
            date = r.timestamp.split('T')[0]
            if date not in by_date:
                by_date[date] = DailySummary(date=date)

            summary = by_date[date]
            summary.total_calls += 1
            if r.success:
                summary.success_calls += 1
            else:
                summary.failed_calls += 1
            summary.total_prompt_tokens += r.prompt_tokens
            summary.total_completion_tokens += r.completion_tokens
            summary.total_tokens += r.total_tokens
            summary.total_cost += r.cost_estimate

            # 按模型统计
            if r.model not in summary.by_model:
                summary.by_model[r.model] = {"calls": 0, "tokens": 0, "cost": 0.0}
            summary.by_model[r.model]["calls"] += 1
            summary.by_model[r.model]["tokens"] += r.total_tokens
            summary.by_model[r.model]["cost"] += r.cost_estimate

            # 按提供商统计
            if r.provider not in summary.by_provider:
                summary.by_provider[r.provider] = {"calls": 0, "tokens": 0, "cost": 0.0}
            summary.by_provider[r.provider]["calls"] += 1
            summary.by_provider[r.provider]["tokens"] += r.total_tokens
            summary.by_provider[r.provider]["cost"] += r.cost_estimate

        # 总计
        total_summary = {
            "period": f"最近{days}天",
            "start_date": start_date,
            "end_date": now.strftime("%Y-%m-%d"),
            "total_calls": sum(s.total_calls for s in by_date.values()),
            "success_calls": sum(s.success_calls for s in by_date.values()),
            "failed_calls": sum(s.failed_calls for s in by_date.values()),
            "total_prompt_tokens": sum(s.total_prompt_tokens for s in by_date.values()),
            "total_completion_tokens": sum(s.total_completion_tokens for s in by_date.values()),
            "total_tokens": sum(s.total_tokens for s in by_date.values()),
            "total_cost": sum(s.total_cost for s in by_date.values()),
            "by_date": {k: asdict(v) for k, v in by_date.items()}
        }

        return total_summary

    def get_today_stats(self) -> Dict[str, Any]:
        """获取今日统计"""
        return self.get_stats(days=1)

    def get_model_ranking(self, days: int = 7) -> List[Dict]:
        """获取模型使用排名"""
        stats = self.get_stats(days)
        model_stats = {}

        for date, summary in stats.get("by_date", {}).items():
            for model, data in summary.get("by_model", {}).items():
                if model not in model_stats:
                    model_stats[model] = {"calls": 0, "tokens": 0, "cost": 0.0}
                model_stats[model]["calls"] += data["calls"]
                model_stats[model]["tokens"] += data["tokens"]
                model_stats[model]["cost"] += data["cost"]

        # 按调用次数排序
        ranking = sorted(model_stats.items(), key=lambda x: x[1]["calls"], reverse=True)
        return [{"model": k, **v} for k, v in ranking]

    def get_provider_ranking(self, days: int = 7) -> List[Dict]:
        """获取提供商使用排名"""
        stats = self.get_stats(days)
        provider_stats = {}

        for date, summary in stats.get("by_date", {}).items():
            for provider, data in summary.get("by_provider", {}).items():
                if provider not in provider_stats:
                    provider_stats[provider] = {"calls": 0, "tokens": 0, "cost": 0.0}
                provider_stats[provider]["calls"] += data["calls"]
                provider_stats[provider]["tokens"] += data["tokens"]
                provider_stats[provider]["cost"] += data["cost"]

        ranking = sorted(provider_stats.items(), key=lambda x: x[1]["calls"], reverse=True)
        return [{"provider": k, **v} for k, v in ranking]

    def export_report(self, days: int = 7, output_path: str = None) -> str:
        """导出报告"""
        stats = self.get_stats(days)
        model_ranking = self.get_model_ranking(days)
        provider_ranking = self.get_provider_ranking(days)

        report = f"""# Token使用统计报告

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**统计周期**: {stats['period']} ({stats['start_date']} ~ {stats['end_date']})

---

## 总体统计

| 指标 | 数值 |
|------|------|
| 总调用次数 | {stats['total_calls']} |
| 成功调用 | {stats['success_calls']} |
| 失败调用 | {stats['failed_calls']} |
| 总输入Token | {stats['total_prompt_tokens']:,} |
| 总输出Token | {stats['total_completion_tokens']:,} |
| 总Token | {stats['total_tokens']:,} |
| 估算成本 | ${stats['total_cost']:.4f} |

---

## 模型使用排名

| 排名 | 模型 | 调用次数 | Token数 | 估算成本 |
|------|------|---------|---------|----------|
"""

        for i, m in enumerate(model_ranking, 1):
            report += f"| {i} | {m['model']} | {m['calls']} | {m['tokens']:,} | ${m['cost']:.4f} |\n"

        report += f"""
---

## 提供商使用排名

| 排名 | 提供商 | 调用次数 | Token数 | 估算成本 |
|------|--------|---------|---------|----------|
"""

        for i, p in enumerate(provider_ranking, 1):
            report += f"| {i} | {p['provider']} | {p['calls']} | {p['tokens']:,} | ${p['cost']:.4f} |\n"

        report += f"""
---

## 每日明细

| 日期 | 调用次数 | 成功 | 失败 | Token数 | 估算成本 |
|------|---------|------|------|---------|----------|
"""

        for date in sorted(stats['by_date'].keys(), reverse=True):
            s = stats['by_date'][date]
            report += f"| {date} | {s['total_calls']} | {s['success_calls']} | {s['failed_calls']} | {s['total_tokens']:,} | ${s['total_cost']:.4f} |\n"

        # 保存报告
        if output_path is None:
            output_path = self.data_dir / f"usage_report_{datetime.now().strftime('%Y%m%d')}.md"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        return str(output_path)


# 全局实例
_tracker: Optional[TokenUsageTracker] = None


def get_tracker() -> TokenUsageTracker:
    """获取全局追踪器"""
    global _tracker
    if _tracker is None:
        _tracker = TokenUsageTracker()
    return _tracker


# === 测试 ===
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    tracker = get_tracker()

    print("=" * 60)
    print("[TOKEN USAGE TRACKER TEST]")
    print("=" * 60)

    # 模拟一些记录
    print("\n[TEST] Recording sample usage...")

    tracker.record("gemini-2.5-flash", "google", 100, 50, "quick_qa", True, 500)
    tracker.record("gpt-4o", "azure_openai", 200, 100, "code_generation", True, 800)
    tracker.record("o3-mini", "azure_openai", 150, 80, "complex_reasoning", True, 1200)
    tracker.record("gemini-2.5-pro", "google", 300, 200, "analysis", True, 1500)

    # 获取统计
    print("\n[RESULT] Today's Stats:")
    stats = tracker.get_today_stats()
    print(f"  总调用: {stats['total_calls']}")
    print(f"  总Token: {stats['total_tokens']:,}")
    print(f"  估算成本: ${stats['total_cost']:.4f}")

    # 模型排名
    print("\n[RESULT] Model Ranking:")
    for m in tracker.get_model_ranking(1):
        print(f"  {m['model']}: {m['calls']} calls, {m['tokens']} tokens")

    # 导出报告
    print("\n[TEST] Exporting report...")
    report_path = tracker.export_report(7)
    print(f"  Report saved to: {report_path}")