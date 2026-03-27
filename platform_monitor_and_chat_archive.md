# 一次性执行：平台监控 + Chat 洞察自动存档 + 自学习集成

## 任务 1：创建 `scripts/platform_monitor.py`

新建文件，功能：定期扫描 GitHub/ClawHub 上与项目相关的新仓库、新 skill、新工具，自动入库 + 飞书通知。

```python
"""
@description: 平台技术雷达 — 定期扫描 GitHub/ClawHub 发现与项目相关的新技术、新工具、新 skill
@dependencies: requests, json, src.tools.knowledge_base, src.utils.model_gateway
@last_modified: 2026-03-26

用法:
    python scripts/platform_monitor.py                    # 手动执行一次
    python scripts/platform_monitor.py --notify           # 执行 + 飞书通知

集成到 daily_learning.py 的定时器中，每天跑一次。
"""

import json
import time
import requests
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".ai-state" / "platform_monitor_state.json"


# ============================================================
# 1. 监控源配置
# ============================================================

GITHUB_SEARCH_QUERIES = [
    # MCP/Skill 生态
    "MCP motorcycle helmet",
    "MCP riding safety",
    "MCP navigation motorcycle",
    "awesome-mcp-servers",
    # 智能头盔直接相关
    "smart motorcycle helmet",
    "motorcycle helmet HUD",
    "motorcycle helmet bluetooth intercom",
    "motorcycle helmet AR display",
    "riding helmet communication",
    # 关键技术方向
    "OLED microdisplay helmet",
    "waveguide AR glasses",
    "mesh intercom motorcycle",
    "motorcycle ADAS blind spot",
    # 供应链/芯片
    "Qualcomm AR1 glasses",
    "Snapdragon AR smart glasses",
]

GITHUB_REPOS_TO_WATCH = [
    # 跟踪特定仓库的新 release/commit
    "punkpeye/awesome-mcp-servers",
    "modelcontextprotocol/servers",
]

# ClawHub 目前没有公开 API，用 web 搜索替代
CLAWHUB_SEARCH_QUERIES = [
    "ClawHub motorcycle riding",
    "ClawHub navigation travel outdoor",
    "ClawHub safety emergency SOS",
    "ClawHub MCP skill 出行 骑行",
]

# 相关性关键词（LLM 判断前的粗筛）
RELEVANCE_KEYWORDS = [
    "helmet", "motorcycle", "riding", "cycling", "头盔", "骑行", "摩托",
    "HUD", "head-up", "AR glasses", "smart glasses", "光波导", "waveguide",
    "intercom", "mesh", "对讲", "通讯",
    "ADAS", "blind spot", "crash detection", "碰撞", "盲区",
    "MCP", "skill", "plugin", "agent",
    "Qualcomm AR1", "AR2", "OLEDoS", "Micro LED",
    "Cardo", "Sena", "Shoei", "EyeLights", "Forcite",
    "navigation", "导航", "safety", "安全",
]


# ============================================================
# 2. GitHub 搜索（不需要 API key，匿名限流 10 次/分钟）
# ============================================================

def search_github_repos(query: str, since_days: int = 7, max_results: int = 5) -> List[Dict]:
    """搜索 GitHub 最近创建/更新的仓库"""
    since_date = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")
    url = "https://api.github.com/search/repositories"
    params = {
        "q": f"{query} pushed:>{since_date}",
        "sort": "updated",
        "order": "desc",
        "per_page": max_results,
    }
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            return [{
                "name": item["full_name"],
                "description": item.get("description", "") or "",
                "url": item["html_url"],
                "stars": item["stargazers_count"],
                "updated": item["updated_at"][:10],
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
            } for item in items]
        elif resp.status_code == 403:
            print(f"[PlatformMonitor] GitHub 限流，等待 60 秒")
            time.sleep(60)
        else:
            print(f"[PlatformMonitor] GitHub 搜索失败: {resp.status_code}")
    except Exception as e:
        print(f"[PlatformMonitor] GitHub 搜索异常: {e}")
    return []


def check_github_repo_updates(repo: str, since_days: int = 7) -> List[Dict]:
    """检查特定仓库的最近 commit"""
    since_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    url = f"https://api.github.com/repos/{repo}/commits"
    params = {"since": since_date, "per_page": 10}
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            commits = resp.json()
            return [{
                "repo": repo,
                "sha": c["sha"][:7],
                "message": c["commit"]["message"].split("\n")[0][:100],
                "date": c["commit"]["author"]["date"][:10],
                "url": c["html_url"],
            } for c in commits[:5]]
    except Exception as e:
        print(f"[PlatformMonitor] GitHub commit 查询异常: {e}")
    return []


# ============================================================
# 3. 通用搜索（ClawHub 等没有 API 的平台，用工具搜索）
# ============================================================

def search_via_tools(query: str) -> str:
    """用项目已有的搜索工具搜索"""
    try:
        from src.tools.tool_registry import get_tool_registry
        registry = get_tool_registry()
        result = registry.call("deep_research", query)
        if result.get("success"):
            return result.get("data", "")[:3000]
    except Exception as e:
        print(f"[PlatformMonitor] 工具搜索失败: {e}")
    return ""


# ============================================================
# 4. 相关性判断 + 入库
# ============================================================

def _coarse_relevance(text: str) -> bool:
    """粗筛：包含任一关键词就过"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in RELEVANCE_KEYWORDS)


def _llm_relevance_and_summarize(items: List[Dict], gateway) -> List[Dict]:
    """用 LLM 判断相关性并生成摘要"""
    if not items:
        return []

    items_text = ""
    for i, item in enumerate(items):
        items_text += f"\n[{i}] {item.get('name', '')} — {item.get('description', '')[:150]}"
        if item.get('url'):
            items_text += f" ({item['url']})"

    prompt = (
        f"以下是从 GitHub/ClawHub 等平台发现的新项目/工具。\n"
        f"我们在做智能摩托车全盔项目（HUD、Mesh 对讲、ADAS、AR 显示、MCP 接口等）。\n"
        f"判断每个项目与我们的相关性，并为相关项目生成知识库摘要。\n\n"
        f"## 发现列表{items_text}\n\n"
        f"## 输出要求\n"
        f"只输出 JSON 数组，每个元素：\n"
        f'{{"index": 编号, "relevant": true/false, "relevance": "说明为什么相关", '
        f'"title": "入库标题（20字）", "summary": "200字摘要，包含具体技术细节", '
        f'"domain": "competitors/components/lessons/standards", "tags": ["标签"]}}\n'
        f"不相关的只输出 {{\"index\": N, \"relevant\": false}}"
    )

    from src.utils.model_gateway import call_for_search
    result = call_for_search(gateway, prompt, "只输出 JSON 数组。", "platform_monitor")

    if not result.get("success"):
        return []

    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        parsed = json.loads(resp)
        return [p for p in parsed if p.get("relevant")]
    except Exception as e:
        print(f"[PlatformMonitor] LLM 解析失败: {e}")
        return []


# ============================================================
# 5. 状态管理（避免重复入库）
# ============================================================

def _load_state() -> Dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen_urls": [], "last_run": None}


def _save_state(state: Dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    # 只保留最近 500 个 URL
    state["seen_urls"] = state.get("seen_urls", [])[-500:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 6. 主流程
# ============================================================

def run_platform_monitor(
    since_days: int = 7,
    progress_callback: Optional[Callable] = None,
    feishu_notify: Optional[Callable] = None,
) -> str:
    """执行一次平台监控扫描

    Returns:
        扫描报告文本
    """
    from src.utils.model_gateway import get_model_gateway
    from src.tools.knowledge_base import add_knowledge

    gateway = get_model_gateway()
    state = _load_state()
    seen = set(state.get("seen_urls", []))

    all_discoveries = []
    new_entries = 0

    def _log(msg):
        print(f"[PlatformMonitor] {msg}")
        if progress_callback:
            progress_callback(msg)

    _log(f"开始平台扫描（最近 {since_days} 天）")

    # === Step 1: GitHub 仓库搜索 ===
    _log(f"GitHub 搜索: {len(GITHUB_SEARCH_QUERIES)} 个查询")
    for i, query in enumerate(GITHUB_SEARCH_QUERIES):
        repos = search_github_repos(query, since_days=since_days)
        for repo in repos:
            if repo["url"] not in seen:
                if _coarse_relevance(f"{repo['name']} {repo['description']} {' '.join(repo.get('topics', []))}"):
                    all_discoveries.append(repo)
                    seen.add(repo["url"])
        # 限流保护
        if (i + 1) % 5 == 0:
            time.sleep(10)
        else:
            time.sleep(2)

    _log(f"GitHub 搜索完成: {len(all_discoveries)} 个候选")

    # === Step 2: 特定仓库更新检查 ===
    for repo in GITHUB_REPOS_TO_WATCH:
        commits = check_github_repo_updates(repo, since_days=since_days)
        if commits:
            # 把 commit 汇总为一条发现
            commit_summary = "; ".join([c["message"] for c in commits[:3]])
            all_discoveries.append({
                "name": f"{repo} 最近更新",
                "description": commit_summary,
                "url": f"https://github.com/{repo}",
                "stars": 0,
                "updated": commits[0]["date"] if commits else "",
            })
        time.sleep(2)

    _log(f"仓库跟踪完成: {len(GITHUB_REPOS_TO_WATCH)} 个仓库")

    # === Step 3: ClawHub/通用搜索 ===
    for query in CLAWHUB_SEARCH_QUERIES:
        result_text = search_via_tools(query)
        if result_text and len(result_text) > 100:
            all_discoveries.append({
                "name": f"ClawHub/Web: {query}",
                "description": result_text[:300],
                "url": "",
                "stars": 0,
                "updated": datetime.now().strftime("%Y-%m-%d"),
                "_raw_content": result_text,
            })
        time.sleep(3)

    _log(f"总计发现: {len(all_discoveries)} 个候选项")

    if not all_discoveries:
        _save_state({"seen_urls": list(seen)})
        report = f"[PlatformMonitor] 扫描完成，未发现新的相关项目"
        _log(report)
        return report

    # === Step 4: LLM 判断相关性 + 摘要 ===
    _log("LLM 相关性判断中...")
    # 分批处理（每批 10 个）
    relevant_items = []
    for batch_start in range(0, len(all_discoveries), 10):
        batch = all_discoveries[batch_start:batch_start + 10]
        batch_relevant = _llm_relevance_and_summarize(batch, gateway)

        for item in batch_relevant:
            idx = item.get("index", -1)
            if 0 <= idx < len(batch):
                item["_source"] = batch[idx]
            relevant_items.append(item)

        time.sleep(2)

    _log(f"相关项目: {len(relevant_items)} 个")

    # === Step 5: 入库 ===
    for item in relevant_items:
        title = item.get("title", "平台发现")
        summary = item.get("summary", "")
        domain = item.get("domain", "lessons")
        tags = item.get("tags", []) + ["platform_monitor", "tech_radar"]
        source_url = item.get("_source", {}).get("url", "")

        if source_url:
            summary += f"\n\n来源: {source_url}"

        path = add_knowledge(
            title=f"[Tech Radar] {title}",
            domain=domain,
            content=summary,
            tags=tags,
            source=f"platform_monitor:{source_url[:80] if source_url else 'search'}",
            confidence="medium",
            caller="auto",
        )
        if path:
            new_entries += 1

    # === Step 6: 保存状态 + 报告 ===
    _save_state({"seen_urls": list(seen)})

    report_lines = [
        f"[PlatformMonitor] 扫描报告",
        f"扫描范围: 最近 {since_days} 天",
        f"总发现: {len(all_discoveries)} | 相关: {len(relevant_items)} | 新入库: {new_entries}",
    ]

    if relevant_items:
        report_lines.append("\n📡 本次发现:")
        for item in relevant_items[:10]:
            source = item.get("_source", {})
            name = source.get("name", item.get("title", ""))
            stars = source.get("stars", 0)
            star_str = f" ⭐{stars}" if stars > 0 else ""
            report_lines.append(f"  • {name}{star_str}")
            report_lines.append(f"    {item.get('summary', '')[:100]}")

    report = "\n".join(report_lines)
    _log(report)

    # 飞书通知
    if feishu_notify and relevant_items:
        feishu_notify(f"📡 技术雷达发现 {len(relevant_items)} 个相关项目，{new_entries} 个已入库。\n发送「知识库」查看。")

    return report


# ============================================================
# 7. CLI
# ============================================================

if __name__ == "__main__":
    import sys
    notify = "--notify" in sys.argv
    report = run_platform_monitor(since_days=7)
    print("\n" + report)
```

---

## 任务 2：集成到 daily_learning.py 的定时器

在 `scripts/daily_learning.py` 中找到 `start_daily_scheduler` 函数，在定时学习的 callback 里加一行：每天第一次学习时顺带跑一次平台监控。

找到定时学习的主循环（通常在 `_learning_loop` 或类似函数中），在学习逻辑之后添加：

```python
# 每天第一次学习时顺带跑平台监控
try:
    from scripts.platform_monitor import run_platform_monitor
    # 用 state 文件判断今天是否已跑过
    from pathlib import Path
    import json as _json
    state_file = Path(__file__).parent.parent / ".ai-state" / "platform_monitor_state.json"
    should_run = True
    if state_file.exists():
        try:
            state = _json.loads(state_file.read_text(encoding="utf-8"))
            last_run = state.get("last_run", "")
            if last_run and last_run[:10] == datetime.now().strftime("%Y-%m-%d"):
                should_run = False  # 今天已跑过
        except Exception:
            pass
    if should_run:
        print("[DailyLearning] 触发每日平台监控...")
        run_platform_monitor(since_days=7, feishu_notify=feishu_notify)
except Exception as e:
    print(f"[DailyLearning] 平台监控失败: {e}")
```

---

## 任务 3：Chat 洞察自动存档

在 `scripts/feishu_sdk_client.py` 中，找到 chat 路由的兜底分支（`_smart_route_and_reply` 函数或 text 消息 else 块中 intent == "chat" 的 `_chat_bg` 函数）。

在 LLM 回复成功后、`send_reply` 之后，添加自动存档检测：

```python
                        # === Chat 洞察自动存档 ===
                        # 如果用户消息包含行业动态信号词，且机器人回复包含对项目的启发，自动存入知识库
                        try:
                            signal_words = ["发布", "上线", "推出", "宣布", "融资", "合作",
                                            "MCP", "skill", "plugin", "开源", "GitHub",
                                            "对我们", "启示", "启发", "借鉴", "参考"]
                            has_signal = any(w in text for w in signal_words)
                            has_insight = any(w in reply_text for w in ["对我们", "启示", "启发", "建议", "借鉴", "意味着"])

                            if has_signal and has_insight and len(reply_text) > 200:
                                from src.tools.knowledge_base import add_knowledge
                                archive_content = f"## 用户分享\n{text[:500]}\n\n## AI 分析\n{reply_text[:2000]}"
                                add_knowledge(
                                    title=f"[洞察] {text[:40]}",
                                    domain="lessons",
                                    content=archive_content,
                                    tags=["chat_insight", "auto_archive", "industry_signal"],
                                    source="chat_auto_archive",
                                    confidence="medium",
                                    caller="user_share",
                                )
                                print(f"[Chat] 洞察已自动存档: {text[:40]}")
                        except Exception as archive_err:
                            print(f"[Chat] 自动存档失败: {archive_err}")
```

注意：这段代码要加在 `_chat_bg` 内部的 `send_reply(reply_target, reply_text, reply_type)` 之后、`mem.add_bot_message(...)` 之前。

同样的逻辑也加到 `_smart_route_and_reply` 函数的 chat 兜底分支中。

---

## 任务 4：新增飞书指令 "技术雷达" / "平台监控"

在 `handle_message` 的 text 精确指令区添加：

```python
elif text.strip() in ("技术雷达", "平台监控", "tech radar", "platform monitor"):
    send_reply(reply_target, "📡 启动技术雷达扫描（GitHub + ClawHub），预计 5-10 分钟...", reply_type)
    def _radar():
        try:
            from scripts.platform_monitor import run_platform_monitor
            report = run_platform_monitor(
                since_days=7,
                progress_callback=lambda msg: print(f"  {msg}"),
                feishu_notify=lambda msg: send_reply(reply_target, msg, reply_type)
            )
            send_reply(reply_target, report[:3500], reply_type)
        except Exception as e:
            send_reply(reply_target, f"❌ 技术雷达失败: {e}", reply_type)
    threading.Thread(target=_radar, daemon=True).start()
```

---

## 验证

```bash
# 1. 验证 platform_monitor 可导入
python -c "from scripts.platform_monitor import run_platform_monitor; print('OK')"

# 2. 手动跑一次（不通知飞书）
python scripts/platform_monitor.py

# 3. 验证飞书指令
# 重启服务后发：技术雷达
```
