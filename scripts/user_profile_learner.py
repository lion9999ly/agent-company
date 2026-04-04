"""从历史对话和评价中学习 Leo 的偏好
@description: 用户偏好学习器，从评价中提取偏好模式
@dependencies: 无
@last_modified: 2026-04-04
"""
import yaml, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROFILE_PATH = PROJECT_ROOT / ".ai-state" / "leo_profile.yaml"
RATINGS_PATH = PROJECT_ROOT / ".ai-state" / "ratings_history.jsonl"


def learn_from_ratings():
    """从 A/B/C/D 评价中提取偏好模式"""
    if not RATINGS_PATH.exists():
        return {}

    ratings = []
    for line in RATINGS_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            r = json.loads(line)
            ratings.append(r)
        except Exception:
            continue

    if not ratings:
        return {}

    # 分析高分报告的共同特征
    high_ratings = [r for r in ratings if r.get("rating") in ["A", "B"]]
    low_ratings = [r for r in ratings if r.get("rating") in ["C", "D"]]

    # 计算平均报告长度
    avg_length = sum(len(r.get("content", "")) for r in ratings) / len(ratings)

    # 提取高频话题
    topics = {}
    for r in ratings:
        for topic in r.get("topics", []):
            topics[topic] = topics.get(topic, 0) + 1
    top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]

    # 更新 profile
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding='utf-8')) if PROFILE_PATH.exists() else {}
    profile.setdefault("auto_learned", {})
    profile["auto_learned"]["avg_rating_by_type"] = _analyze_by_type(ratings)
    profile["auto_learned"]["preferred_report_length"] = avg_length
    profile["auto_learned"]["topics_most_engaged"] = [t[0] for t in top_topics]
    profile["auto_learned"]["last_updated"] = _get_timestamp()

    PROFILE_PATH.write_text(yaml.dump(profile, allow_unicode=True), encoding='utf-8')

    return profile


def _analyze_by_type(ratings: list) -> dict:
    """按报告类型分析评分"""
    type_ratings = {}
    for r in ratings:
        t = r.get("type", "unknown")
        if t not in type_ratings:
            type_ratings[t] = []
        type_ratings[t].append(r.get("rating", "C"))

    # 转换为平均分
    result = {}
    for t, rs in type_ratings.items():
        # A=4, B=3, C=2, D=1
        scores = {"A": 4, "B": 3, "C": 2, "D": 1}
        avg = sum(scores.get(r, 2) for r in rs) / len(rs)
        result[t] = avg

    return result


def _get_timestamp():
    import time
    return time.strftime('%Y-%m-%d %H:%M')


def apply_profile_to_output(text: str, profile: dict) -> str:
    """根据 profile 调整输出格式和重点"""
    if not profile:
        return text

    prefs = profile.get("decision_preferences", {})
    auto = profile.get("auto_learned", {})

    # 检查长度偏好
    preferred_len = auto.get("preferred_report_length", 1500)
    if len(text) > preferred_len * 1.5:
        # 需要精简（这里只是提示，不做实际裁剪）
        pass

    # 检查是否包含模糊建议（pet peeves）
    pet_peeves = prefs.get("pet_peeves", [])
    if "模糊的建议" in str(pet_peeves):
        # 检查并提示改进
        vague_phrases = ["可以考虑", "或许", "可能", "也许"]
        for phrase in vague_phrases:
            if phrase in text:
                # 只是检测，不修改
                pass

    return text


def get_profile() -> dict:
    """获取 Leo 的偏好画像"""
    if PROFILE_PATH.exists():
        return yaml.safe_load(PROFILE_PATH.read_text(encoding='utf-8'))
    return {}


if __name__ == "__main__":
    profile = get_profile()
    print(f"Leo 偏好画像: {profile.get('decision_preferences', {})}")