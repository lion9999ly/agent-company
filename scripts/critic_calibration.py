"""Critic 校准系统

- 采样 Critic 输出
- 推送飞书打标
- 积累校准数据
- 自动进化 few-shot 示例
- 漂移检测
"""

import json
import time
import random
from pathlib import Path
from datetime import datetime

CALIBRATION_PATH = Path(__file__).parent.parent / ".ai-state" / "critic_calibration.jsonl"
FEW_SHOT_PATH = Path(__file__).parent.parent / ".ai-state" / "critic_few_shot_evolved.json"
DRIFT_LOG_PATH = Path(__file__).parent.parent / ".ai-state" / "critic_drift_log.jsonl"


# ============================================================
# 1. 采样
# ============================================================

def sample_for_calibration(critic_data: dict, report_excerpt: str,
                           goal: str, task_title: str) -> list:
    """从 Critic 输出中采样 2-3 个挑战供人工打标

    Args:
        critic_data: Critic 的分级输出（含 p0/p1/p2）
        report_excerpt: 报告摘要（前 500 字）
        goal: 研究目标
        task_title: 任务标题

    Returns:
        待推送的样本列表
    """
    all_challenges = []

    for p0 in critic_data.get("p0_blocking", []):
        all_challenges.append({
            "level": "P0",
            "issue": p0.get("issue", ""),
            "evidence": p0.get("evidence", ""),
            "fix_required": p0.get("fix_required", ""),
        })

    for p1 in critic_data.get("p1_improvement", []):
        all_challenges.append({
            "level": "P1",
            "issue": p1.get("issue", ""),
            "evidence": p1.get("evidence", ""),
        })

    for p2 in critic_data.get("p2_note", []):
        all_challenges.append({
            "level": "P2",
            "issue": p2.get("issue", ""),
        })

    if not all_challenges:
        return []

    # 采样策略: 优先采 P0（最需要校准），再随机补 P1/P2
    p0s = [c for c in all_challenges if c["level"] == "P0"]
    others = [c for c in all_challenges if c["level"] != "P0"]
    random.shuffle(others)

    samples = p0s[:2] + others[:1]  # 最多 2 个 P0 + 1 个其他
    if not samples:
        samples = others[:2]

    # 附加上下文
    for s in samples:
        s["task_title"] = task_title
        s["goal"] = goal[:200]
        s["report_excerpt"] = report_excerpt[:300]
        s["sampled_at"] = time.strftime('%Y-%m-%d %H:%M')
        s["sample_id"] = f"cal_{int(time.time())}_{random.randint(100,999)}"

    return samples


# ============================================================
# 2. 飞书推送
# ============================================================

def push_calibration_to_feishu(samples: list, reply_func=None):
    """推送校准批量摘要到飞书（不再逐条推送）

    改为只保存到 pending，等 push_batch_calibration_summary() 统一推送。
    """
    if not samples:
        return
    save_pending_samples(samples)
    # 不再逐条推送，等深度学习结束后统一推送


def push_batch_calibration_summary(reply_func=None):
    """深度学习结束后，一次性推送批量校准摘要

    格式:
    🎯 今晚 Critic 校准（N 个样本）
    1⃣ [P0] 任务名: 挑战摘要
    2⃣ [P1] 任务名: 挑战摘要
    ...
    回复格式: 11213（依次对应每个样本，1=准确 2=偏松 3=偏紧 0=跳过）
    """
    pending = _load_pending_samples()
    if not pending or not reply_func:
        return

    # 只取最近一批（最多 10 个）
    batch = pending[-10:]

    lines = [f"🎯 Critic 校准（{len(batch)} 个样本）\n"]
    emojis = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣", "9⃣", "🔟"]

    for i, s in enumerate(batch):
        emoji = emojis[i] if i < len(emojis) else f"({i+1})"
        issue_short = s.get("issue", "")[:60]
        task_short = s.get("task_title", "")[:20]
        lines.append(f"{emoji} [{s.get('level', '?')}] {task_short}: {issue_short}")

    lines.append("")
    lines.append("回复格式: " + "x" * len(batch) + "（依次对应每个样本）")
    lines.append("1=✅准确  2=⬆️偏松  3=⬇️偏紧  0=跳过")
    lines.append(f"例如: {'1' * len(batch)} 表示全部准确")
    lines.append(f"\n[batch_cal:{len(batch)}]")  # 标记供 text_router 识别

    msg = "\n".join(lines)
    try:
        reply_func(msg)
    except Exception as e:
        print(f"  [Calibration] 批量摘要推送失败: {e}")


# ============================================================
# 3. 接收标注
# ============================================================

def record_label(sample_id: str, label: str) -> bool:
    """记录人工标注

    Args:
        sample_id: 校准样本 ID（cal_xxx_xxx）
        label: "accurate" / "too_loose" / "too_strict" / "skip"

    Returns:
        是否记录成功
    """
    valid_labels = {"accurate", "too_loose", "too_strict", "skip"}
    if label not in valid_labels:
        return False

    if label == "skip":
        return True

    # 从未标注的样本中找到对应样本
    pending = _load_pending_samples()
    sample = None
    for s in pending:
        if s.get("sample_id") == sample_id:
            sample = s
            break

    if not sample:
        print(f"  [Calibration] 未找到样本: {sample_id}")
        return False

    # 记录标注
    sample["label"] = label
    sample["labeled_at"] = time.strftime('%Y-%m-%d %H:%M')

    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIBRATION_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 从待标注列表中移除
    pending = [s for s in pending if s.get("sample_id") != sample_id]
    _save_pending_samples(pending)

    print(f"  [Calibration] 已记录: {sample_id} = {label}")

    # 检查是否积累够了，触发 few-shot 进化
    labeled_count = _count_labeled()
    if labeled_count >= 10 and labeled_count % 5 == 0:
        evolve_few_shot()

    return True


def _load_pending_samples() -> list:
    pending_path = CALIBRATION_PATH.parent / "critic_calibration_pending.json"
    if pending_path.exists():
        return json.loads(pending_path.read_text(encoding="utf-8"))
    return []


def _save_pending_samples(samples: list):
    pending_path = CALIBRATION_PATH.parent / "critic_calibration_pending.json"
    pending_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def save_pending_samples(samples: list):
    """保存待标注样本（供外部调用）"""
    existing = _load_pending_samples()
    existing.extend(samples)
    # 只保留最近 20 个未标注的
    _save_pending_samples(existing[-20:])


def _count_labeled() -> int:
    if not CALIBRATION_PATH.exists():
        return 0
    return sum(1 for _ in open(CALIBRATION_PATH, encoding="utf-8"))


# ============================================================
# 4. Few-shot 自动进化
# ============================================================

def evolve_few_shot():
    """从校准数据中自动生成进化版 few-shot 示例

    策略:
    - label=accurate 的样本 → 好的示例（按原级别）
    - label=too_loose 的样本 → "差的 Px"示例（应该更严但没有）
    - label=too_strict 的样本 → "差的 Px"示例（过度挑剔）
    """
    if not CALIBRATION_PATH.exists():
        return

    labeled = []
    with open(CALIBRATION_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                labeled.append(json.loads(line.strip()))
            except:
                continue

    if len(labeled) < 10:
        return

    print(f"  [Calibration] 从 {len(labeled)} 条标注进化 few-shot...")

    # 分类
    good_examples = []   # 准确的
    bad_loose = []       # 偏松的
    bad_strict = []      # 偏紧的

    for item in labeled:
        label = item.get("label")
        if label == "accurate":
            good_examples.append(item)
        elif label == "too_loose":
            bad_loose.append(item)
        elif label == "too_strict":
            bad_strict.append(item)

    # 生成进化版示例
    evolved = {
        "generated_at": time.strftime('%Y-%m-%d %H:%M'),
        "source_count": len(labeled),
        "good_p0_examples": [],
        "good_p1_examples": [],
        "bad_examples_loose": [],
        "bad_examples_strict": [],
    }

    for item in good_examples[-5:]:
        level = item.get("level", "")
        example = {
            "level": level,
            "issue": item.get("issue", ""),
            "evidence": item.get("evidence", ""),
            "task_context": item.get("task_title", ""),
        }
        if level == "P0":
            evolved["good_p0_examples"].append(example)
        elif level == "P1":
            evolved["good_p1_examples"].append(example)

    for item in bad_loose[-3:]:
        evolved["bad_examples_loose"].append({
            "original_level": item.get("level", ""),
            "should_be": "更严（P0）" if item.get("level") != "P0" else "P0 但理由不充分",
            "issue": item.get("issue", ""),
            "task_context": item.get("task_title", ""),
        })

    for item in bad_strict[-3:]:
        evolved["bad_examples_strict"].append({
            "original_level": item.get("level", ""),
            "should_be": f"降级为 P{int(item.get('level','P0')[1])+1}" if item.get("level") != "P2" else "不应输出",
            "issue": item.get("issue", ""),
            "task_context": item.get("task_title", ""),
        })

    FEW_SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEW_SHOT_PATH.write_text(
        json.dumps(evolved, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  [Calibration] Few-shot 进化完成: "
          f"{len(evolved['good_p0_examples'])} good P0, "
          f"{len(evolved['good_p1_examples'])} good P1, "
          f"{len(evolved['bad_examples_loose'])} bad loose, "
          f"{len(evolved['bad_examples_strict'])} bad strict")


def get_evolved_few_shot() -> str:
    """获取进化版 few-shot 文本，供 Critic prompt 使用

    如果进化版存在且够丰富，替换默认的 CRITIC_FEW_SHOT。
    否则返回空字符串（继续用默认）。
    """
    if not FEW_SHOT_PATH.exists():
        return ""

    try:
        evolved = json.loads(FEW_SHOT_PATH.read_text(encoding="utf-8"))
    except:
        return ""

    # 至少要有 2 个好的和 1 个差的才值得替换
    good_count = (len(evolved.get("good_p0_examples", []))
                  + len(evolved.get("good_p1_examples", [])))
    bad_count = (len(evolved.get("bad_examples_loose", []))
                 + len(evolved.get("bad_examples_strict", [])))

    if good_count < 2 or bad_count < 1:
        return ""

    text = "\n## 挑战质量对标（基于历史校准，优先级高于默认示例）\n\n"

    for ex in evolved.get("good_p0_examples", [])[:2]:
        text += (
            f"✅ 好的 P0（来自 '{ex.get('task_context', '')}'）:\n"
            f"  issue: {ex.get('issue', '')}\n"
            f"  evidence: {ex.get('evidence', '')}\n\n"
        )

    for ex in evolved.get("good_p1_examples", [])[:2]:
        text += (
            f"✅ 好的 P1:\n"
            f"  issue: {ex.get('issue', '')}\n\n"
        )

    for ex in evolved.get("bad_examples_loose", [])[:2]:
        text += (
            f"❌ 偏松（原判 {ex.get('original_level', '')}，应该 {ex.get('should_be', '')}）:\n"
            f"  issue: {ex.get('issue', '')}\n\n"
        )

    for ex in evolved.get("bad_examples_strict", [])[:2]:
        text += (
            f"❌ 偏紧（原判 {ex.get('original_level', '')}，应该 {ex.get('should_be', '')}）:\n"
            f"  issue: {ex.get('issue', '')}\n\n"
        )

    return text


# ============================================================
# 5. 漂移检测
# ============================================================

def check_drift(critic_data: dict, reply_func=None):
    """检测 Critic 行为漂移

    跟踪最近 N 次研究的 P0 比例:
    - 连续 5 次 P0 率 = 0% → 偏松警告
    - 连续 5 次 P0 率 > 30% → 偏紧警告
    """
    p0_count = len(critic_data.get("p0_blocking", []))
    total = (p0_count
             + len(critic_data.get("p1_improvement", []))
             + len(critic_data.get("p2_note", [])))
    p0_rate = p0_count / max(total, 1)

    # 记录
    entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "p0_count": p0_count,
        "total": total,
        "p0_rate": round(p0_rate, 2),
    }

    DRIFT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DRIFT_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")

    # 读最近 5 条
    recent = []
    if DRIFT_LOG_PATH.exists():
        lines = DRIFT_LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
        for line in lines[-5:]:
            try:
                recent.append(json.loads(line))
            except:
                continue

    if len(recent) < 5:
        return

    recent_p0_rates = [r.get("p0_rate", 0) for r in recent]

    # 偏松: 连续 5 次 P0 率 = 0
    if all(r == 0 for r in recent_p0_rates):
        msg = (
            "⚠️ Critic 漂移检测: 偏松\n"
            f"最近 5 次研究 P0 率均为 0%\n"
            "Critic 可能太宽松，建议做一轮校准（回复几个校准样本）"
        )
        print(f"  [Drift] {msg}")
        if reply_func:
            try:
                reply_func(msg)
            except:
                pass

    # 偏紧: 连续 5 次 P0 率 > 30%
    elif all(r > 0.3 for r in recent_p0_rates):
        msg = (
            "⚠️ Critic 漂移检测: 偏紧\n"
            f"最近 5 次研究 P0 率均 > 30%\n"
            "Critic 可能过度挑剔，建议做一轮校准"
        )
        print(f"  [Drift] {msg}")
        if reply_func:
            try:
                reply_func(msg)
            except:
                pass