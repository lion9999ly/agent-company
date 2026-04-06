"""
深度研究 — 运行健康巡检
职责: 规则止血 + LLM 追因。每个任务完成后自动检查异常趋势。
被调用方: runner.py（主循环中每个任务后调用）
依赖: models.py, night_watch.py
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.deep_research.models import disable_model, is_model_disabled


@dataclass
class HealthStats:
    """单轮深度学习的运行健康统计"""

    # 模型 404 计数
    model_404_count: Dict[str, int] = field(default_factory=dict)
    # L2 提炼统计
    l2_success: int = 0
    l2_fail: int = 0
    # 连续 L2 低成功率的任务数
    l2_low_streak: int = 0
    # L1 搜索全空次数
    search_empty_count: int = 0
    # 已触发的修复动作（避免重复触发）
    actions_taken: List[str] = field(default_factory=list)
    # LLM 追因结果
    diagnoses: List[dict] = field(default_factory=list)
    # 当前 extraction 输入截断长度（可被自动调低）
    extraction_input_limit: int = 3000

    def record_model_404(self, model_name: str):
        self.model_404_count[model_name] = self.model_404_count.get(model_name, 0) + 1

    def record_l2_result(self, success: bool):
        if success:
            self.l2_success += 1
        else:
            self.l2_fail += 1

    def record_search_empty(self):
        self.search_empty_count += 1

    @property
    def l2_success_rate(self) -> float:
        total = self.l2_success + self.l2_fail
        if total == 0:
            return 1.0
        return self.l2_success / total

    def reset_l2_for_next_task(self):
        """每个任务开始时重置 L2 计数（保留跨任务的 streak）"""
        task_rate = self.l2_success_rate
        if task_rate < 0.5 and (self.l2_success + self.l2_fail) >= 4:
            self.l2_low_streak += 1
        else:
            self.l2_low_streak = 0
        self.l2_success = 0
        self.l2_fail = 0


# 全局实例（每次 run_deep_learning 开始时重置）
_stats: Optional[HealthStats] = None
_stats_lock = threading.Lock()


def init_health_stats():
    """每次 run_deep_learning 开始时调用"""
    global _stats
    _stats = HealthStats()
    return _stats


def get_health_stats() -> Optional[HealthStats]:
    return _stats


def record_model_404(model_name: str):
    """pipeline.py 在检测到 404 时调用"""
    if not _stats:
        return
    with _stats_lock:
        _stats.record_model_404(model_name)


def record_l2_result(success: bool):
    """pipeline.py 在每条 L2 提炼完成后调用"""
    if not _stats:
        return
    with _stats_lock:
        _stats.record_l2_result(success)


def record_search_empty():
    """pipeline.py 在 L1 搜索全空时调用"""
    if not _stats:
        return
    with _stats_lock:
        _stats.record_search_empty()


def run_health_check(progress_callback=None) -> List[str]:
    """每个任务完成后调用。执行规则止血 + 必要时 LLM 追因。

    Returns: 本次触发的修复动作列表
    """
    if not _stats:
        return []

    actions = []

    with _stats_lock:
        # === 规则 1: 模型 404 连续 >= 2 次 → 自动禁用 + LLM 追因 ===
        for model_name, count in list(_stats.model_404_count.items()):
            if count >= 2 and not is_model_disabled(model_name):
                action_key = f"disable_{model_name}"
                if action_key not in _stats.actions_taken:
                    # 止血
                    disable_model(model_name)
                    _stats.actions_taken.append(action_key)
                    actions.append(f"禁用 {model_name}（连续 {count} 次 404）")

                    # LLM 追因（异步，不阻塞主流程）
                    _async_diagnose_404(model_name, count, progress_callback)

        # === 规则 2: L2 成功率连续 2 个任务 < 50% → 缩短输入 ===
        if _stats.l2_low_streak >= 2:
            action_key = "shrink_l2_input"
            if action_key not in _stats.actions_taken:
                old_limit = _stats.extraction_input_limit
                _stats.extraction_input_limit = max(1500, old_limit - 500)
                _stats.actions_taken.append(action_key)
                actions.append(
                    f"L2 提炼成功率连续低，输入截断: {old_limit} → {_stats.extraction_input_limit}"
                )
                if progress_callback:
                    progress_callback(
                        f"⚠️ L2 提炼成功率连续 {_stats.l2_low_streak} 个任务低于 50%，"
                        f"已自动缩短输入到 {_stats.extraction_input_limit} 字"
                    )

        # === 规则 3: L1 搜索连续全空 >= 3 → 切换离线模式 ===
        if _stats.search_empty_count >= 3:
            action_key = "offline_fallback"
            if action_key not in _stats.actions_taken:
                _stats.actions_taken.append(action_key)
                actions.append("连续 3 次搜索全空，建议切换离线任务")
                if progress_callback:
                    progress_callback(
                        "⚠️ 连续 3 个任务搜索全空，可能是网络问题。切换到离线任务模式。"
                    )

        # 重置 L2 计数为下一个任务准备
        _stats.reset_l2_for_next_task()

    if actions:
        print(f"  [HealthCheck] 本轮修复: {actions}")

    return actions


def _async_diagnose_404(model_name: str, count: int, progress_callback=None):
    """异步调用 GLM-5 分析 404 根因，不阻塞主流程"""

    def _diagnose():
        try:
            from scripts.deep_research.models import call_model

            prompt = (
                f"深度研究管道中模型 {model_name} 连续 {count} 次返回 HTTP 404 "
                f"(DeploymentNotFound)。\n\n"
                f"这是 Azure OpenAI 的部署。可能原因：\n"
                f"A) model_registry.yaml 中的 deployment name 拼写错误\n"
                f"B) Azure 部署被删除或未创建\n"
                f"C) API version 不兼容\n"
                f"D) 区域限制\n\n"
                f"系统已自动禁用该模型并走降级链。\n"
                f"请给出最可能的根因和修复建议（一句话）。"
            )

            result = call_model("glm_4_7", prompt,
                                "你是运维诊断专家，简洁回答。",
                                "health_diagnose")

            if result.get("success"):
                diagnosis = result["response"][:300]
                print(f"  [HealthCheck] {model_name} 404 根因: {diagnosis}")

                if _stats:
                    _stats.diagnoses.append({
                        "model": model_name,
                        "issue": f"连续 {count} 次 404",
                        "diagnosis": diagnosis,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                    })

                if progress_callback:
                    progress_callback(
                        f"🔍 {model_name} 404 诊断: {diagnosis}"
                    )
        except Exception as e:
            print(f"  [HealthCheck] 404 诊断失败: {e}")

    # 在后台线程运行，不阻塞主流程
    threading.Thread(target=_diagnose, daemon=True).start()


def generate_health_summary() -> str:
    """深度学习结束后生成健康巡检摘要"""
    if not _stats:
        return ""

    lines = ["📋 运行健康巡检摘要"]

    if _stats.model_404_count:
        lines.append("\n模型 404:")
        for model, count in _stats.model_404_count.items():
            disabled = "已禁用" if is_model_disabled(model) else "未禁用"
            lines.append(f"  {model}: {count} 次 ({disabled})")

    if _stats.actions_taken:
        lines.append(f"\n自动修复动作: {len(_stats.actions_taken)} 项")
        for action in _stats.actions_taken:
            lines.append(f"  • {action}")

    if _stats.diagnoses:
        lines.append(f"\nLLM 诊断: {len(_stats.diagnoses)} 项")
        for d in _stats.diagnoses:
            lines.append(f"  [{d['model']}] {d['diagnosis'][:100]}")

    if not _stats.actions_taken and not _stats.model_404_count:
        lines.append("\n✅ 全程无异常")

    return "\n".join(lines)
