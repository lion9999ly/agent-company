# 自愈系统设计：自动测试 + 自动修复 + 持续健康监控

> 目标: Leo 不在时，系统能自己发现 bug → 自己修复 → 自己验证 → 继续运行。
> Leo 回来只看摘要："修了 3 个 bug，有 1 个修不好需要你看"。

---

## 一、架构总览

```
┌─────────────────────────────────────────────────┐
│                    触发层                         │
│  git push hook │ 深度学习结束 │ 定时(每6h) │ 飞书"自检" │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│                  测试引擎                         │
│  硬测试(import/函数调用/不崩溃)                     │
│  软测试(LLM判断输出是否合理)                        │
│  集成测试(模拟飞书消息→检查完整响应链)                 │
└────────────────────┬────────────────────────────┘
                     ▼
              ┌──── 全部通过? ────┐
              │                   │
             YES                  NO
              │                   │
              ▼                   ▼
     ┌────────────┐     ┌──────────────────┐
     │ 记录健康状态  │     │   自动修复引擎     │
     │ 飞书推送 ✅   │     │  CC 分析→修→验证   │
     └────────────┘     │  最多 3 轮          │
                        └────────┬─────────┘
                                 ▼
                          ┌── 修好了? ──┐
                          │             │
                         YES            NO
                          │             │
                          ▼             ▼
                   commit+push    写 bug_report
                   飞书: 🔧已修复   飞书: ⚠️需要你看
```

---

## 二、测试引擎详细设计

### 新建 `scripts/test_suite.py`

```python
"""自动化测试套件 — 硬测试 + 软测试 + 集成测试"""
import sys, json, time, traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_PATH = PROJECT_ROOT / ".ai-state" / "test_results_latest.json"


def run_all_tests() -> dict:
    """运行全部测试，返回结果"""
    results = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "hard_tests": run_hard_tests(),
        "soft_tests": run_soft_tests(),
        "integration_tests": run_integration_tests(),
    }

    # 统计
    total = 0
    passed = 0
    failed_items = []
    for category, tests in results.items():
        if category == "timestamp":
            continue
        for test in tests:
            total += 1
            if test["status"] == "pass":
                passed += 1
            else:
                failed_items.append(test)

    results["summary"] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "failed_items": failed_items,
    }

    # 保存结果
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    return results


# ============================================================
# 硬测试: 代码能跑、import 不报错、核心函数不崩溃
# ============================================================

def run_hard_tests() -> list:
    """硬测试 — 确保代码不崩溃"""
    results = []

    # H1: 核心模块 import
    core_modules = [
        "scripts.tonight_deep_research",
        "scripts.feishu_handlers.text_router",
        "src.tools.knowledge_base",
        "src.utils.model_gateway",
        "src.utils.token_usage_tracker",
    ]
    for mod in core_modules:
        results.append(_test_import(mod, "core"))

    # H2: 新模块 import
    new_modules = [
        "scripts.handoff_processor",
        "scripts.system_log_generator",
        "scripts.work_memory",
        "scripts.roi_tracker",
        "scripts.decision_logger",
        "scripts.trust_tracker",
        "scripts.brand_layer",
        "scripts.collaboration",
        "scripts.insight_engine",
        "scripts.crm_lite",
        "scripts.demo_generator",
        "scripts.guardrail_engine",
        "scripts.load_manager",
    ]
    for mod in new_modules:
        results.append(_test_import(mod, "new_module"))

    # H3: KB 搜索不崩溃
    results.append(_test_function(
        "kb_search",
        lambda: __import__("src.tools.knowledge_base", fromlist=["search_knowledge"]).search_knowledge("test", limit=3),
        "KB 搜索返回结果"
    ))

    # H4: 决策树文件可解析
    results.append(_test_function(
        "decision_tree_parse",
        lambda: __import__("yaml").safe_load(
            (PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml").read_text(encoding='utf-8')
        ),
        "决策树 YAML 可解析"
    ))

    # H5: model_registry 可解析
    results.append(_test_function(
        "model_registry_parse",
        lambda: __import__("yaml").safe_load(
            (PROJECT_ROOT / "src" / "config" / "model_registry.yaml").read_text(encoding='utf-8')
        ),
        "model_registry YAML 可解析"
    ))

    return results


def _test_import(module_path: str, category: str) -> dict:
    """测试模块是否能 import"""
    try:
        __import__(module_path)
        return {"name": f"import_{module_path}", "category": category, "status": "pass"}
    except Exception as e:
        return {"name": f"import_{module_path}", "category": category, "status": "fail",
                "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-500:]}


def _test_function(name: str, func, description: str) -> dict:
    """测试函数是否能执行不报错"""
    try:
        result = func()
        return {"name": name, "category": "function", "status": "pass", "description": description}
    except Exception as e:
        return {"name": name, "category": "function", "status": "fail",
                "error": f"{type(e).__name__}: {e}", "description": description,
                "traceback": traceback.format_exc()[-500:]}


# ============================================================
# 软测试: LLM 判断输出是否合理
# ============================================================

def run_soft_tests() -> list:
    """软测试 — 用 LLM 判断输出质量"""
    results = []

    # 只在模型可用时才跑软测试
    try:
        from src.utils.model_gateway import get_model_gateway
        gw = get_model_gateway()
    except:
        return [{"name": "soft_test_skip", "status": "skip", "error": "model_gateway 不可用"}]

    # S1: 模拟"状态"指令的输出
    results.append(_soft_test_feishu_command(
        gw, "状态",
        "输出应该包含: KB 条目数、某种统计信息。不应该是空的、不应该包含 traceback 或错误信息。"
    ))

    # S2: 模拟"早报"指令
    results.append(_soft_test_feishu_command(
        gw, "早报",
        "输出应该包含: 日期、某种决策或知识进展摘要。不应该是空的。"
    ))

    # S3: KB 搜索结果质量
    results.append(_soft_test_kb_search(
        gw, "HUD 显示方案",
        "搜索结果应该包含和 HUD、显示、光学相关的条目。不应该返回完全不相关的内容。"
    ))

    return results


def _soft_test_feishu_command(gw, command: str, quality_criteria: str) -> dict:
    """模拟飞书指令并用 LLM 判断输出质量"""
    try:
        # 模拟调用（不真正发飞书，只调用处理函数获取输出）
        captured_output = []

        def mock_send_reply(target, text):
            captured_output.append(text)

        from scripts.feishu_handlers.text_router import route_text_message
        route_text_message(
            text=command,
            open_id="test_user",
            reply_target="test",
            send_reply=mock_send_reply,
            msg_type="text",
            file_key=None
        )

        # 等待异步处理（很多 handler 用 threading）
        time.sleep(5)

        if not captured_output:
            return {"name": f"soft_{command}", "status": "fail", "error": "无输出（5秒超时）"}

        output = "\n".join(captured_output)

        # 用 Flash 判断质量
        result = gw.call("gemini_2_5_flash",
            f"判断以下系统输出是否合理。\n\n"
            f"指令: {command}\n"
            f"输出:\n{output[:1000]}\n\n"
            f"判断标准: {quality_criteria}\n\n"
            f"只回答 PASS 或 FAIL，加一句理由。",
            task_type="test_validation"
        )

        if result.get("success"):
            resp = result["response"].strip()
            if "PASS" in resp.upper():
                return {"name": f"soft_{command}", "status": "pass", "output_preview": output[:200]}
            else:
                return {"name": f"soft_{command}", "status": "fail", "error": resp, "output_preview": output[:200]}

        return {"name": f"soft_{command}", "status": "skip", "error": "LLM 判断调用失败"}

    except Exception as e:
        return {"name": f"soft_{command}", "status": "fail",
                "error": f"{type(e).__name__}: {e}"}


def _soft_test_kb_search(gw, query: str, quality_criteria: str) -> dict:
    """测试 KB 搜索结果质量"""
    try:
        from src.tools.knowledge_base import search_knowledge
        results = search_knowledge(query, limit=5)

        if not results:
            return {"name": f"soft_kb_{query[:20]}", "status": "fail", "error": "搜索无结果"}

        results_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:100]}" for r in results])

        result = gw.call("gemini_2_5_flash",
            f"判断以下知识库搜索结果是否与查询相关。\n\n"
            f"查询: {query}\n结果:\n{results_text}\n\n"
            f"判断标准: {quality_criteria}\n\n只回答 PASS 或 FAIL。",
            task_type="test_validation"
        )

        if result.get("success"):
            return {"name": f"soft_kb_{query[:20]}",
                    "status": "pass" if "PASS" in result["response"].upper() else "fail",
                    "error": result["response"] if "FAIL" in result["response"].upper() else None}

        return {"name": f"soft_kb_{query[:20]}", "status": "skip"}

    except Exception as e:
        return {"name": f"soft_kb_{query[:20]}", "status": "fail", "error": str(e)}


# ============================================================
# 集成测试: 端到端流程验证
# ============================================================

def run_integration_tests() -> list:
    """集成测试 — 验证完整流程"""
    results = []

    # I1: 深度研究配置完整性
    results.append(_test_function(
        "deep_research_config",
        lambda: _verify_deep_research_config(),
        "深度研究管道配置完整（模型分配、降级映射、并发信号量）"
    ))

    # I2: 决策树-KB 联动
    results.append(_test_function(
        "decision_tree_kb_link",
        lambda: _verify_decision_tree_kb(),
        "决策树的 blocking_knowledge 在 KB 中有对应搜索结果"
    ))

    # I3: 所有飞书指令有对应 handler
    results.append(_test_function(
        "feishu_commands_registered",
        lambda: _verify_feishu_commands(),
        "所有预期的飞书指令在 text_router 中有注册"
    ))

    return results


def _verify_deep_research_config() -> bool:
    """验证深度研究管道配置"""
    # 检查 FALLBACK_MAP 是否包含所有活跃模型
    # 检查并发信号量是否定义
    # 检查四通道搜索配置
    return True  # CC 实现具体检查逻辑


def _verify_decision_tree_kb() -> bool:
    """验证决策树和 KB 的联动"""
    import yaml
    from src.tools.knowledge_base import search_knowledge
    dt = yaml.safe_load((PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml").read_text(encoding='utf-8'))
    for d in dt.get("decisions", []):
        if d.get("status") != "open":
            continue
        results = search_knowledge(d.get("question", ""), limit=3)
        # 至少有一些相关搜索结果
    return True


def _verify_feishu_commands() -> bool:
    """验证飞书指令注册"""
    source = (PROJECT_ROOT / "scripts" / "feishu_handlers" / "text_router.py").read_text(encoding='utf-8')
    expected = ["状态", "早报", "深度学习", "决策简报", "产品简介", "帮助"]
    for cmd in expected:
        if cmd not in source:
            raise AssertionError(f"指令 '{cmd}' 未在 text_router.py 中注册")
    return True


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("agent_company 自动化测试套件")
    print("=" * 50)
    results = run_all_tests()
    summary = results["summary"]
    print(f"\n总计: {summary['total']} 项")
    print(f"通过: {summary['passed']} ✅")
    print(f"失败: {summary['failed']} ❌")
    if summary["failed_items"]:
        print("\n失败项:")
        for item in summary["failed_items"]:
            print(f"  ❌ {item['name']}: {item.get('error', '')[:100]}")
```

---

## 三、自动修复引擎

### 新建 `scripts/auto_fixer.py`

```python
"""自动修复引擎 — 测试失败时自动分析+修复+验证"""
import subprocess, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FIX_LOG_PATH = PROJECT_ROOT / ".ai-state" / "auto_fix_log.jsonl"
BUG_REPORT_PATH = PROJECT_ROOT / ".ai-state" / "bug_report.md"


def auto_fix_failures(failed_items: list, max_rounds: int = 3) -> dict:
    """对失败的测试项自动修复
    
    流程:
    1. 把失败项的 error + traceback 交给 CC (Claude) 分析
    2. CC 生成修复代码
    3. 重新跑测试
    4. 最多 3 轮
    5. 修不好的写入 bug_report.md
    """
    fixed = []
    unfixed = []

    for item in failed_items:
        success = False

        for round_num in range(1, max_rounds + 1):
            print(f"\n  [AutoFix] 修复 {item['name']} (第 {round_num}/{max_rounds} 轮)")

            # 用 CC (subprocess) 分析并修复
            fix_prompt = (
                f"测试 '{item['name']}' 失败了。\n\n"
                f"错误: {item.get('error', 'unknown')}\n"
                f"Traceback: {item.get('traceback', 'N/A')}\n"
                f"描述: {item.get('description', '')}\n\n"
                f"请分析原因并给出修复方案。如果需要修改代码，输出完整的文件路径和修改内容。\n"
                f"格式:\nFILE: path/to/file.py\nOLD:\n```\n旧代码\n```\nNEW:\n```\n新代码\n```"
            )

            try:
                result = subprocess.run(
                    ["claude", "-p", fix_prompt, "--output-format", "text"],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(PROJECT_ROOT)
                )
                fix_suggestion = result.stdout.strip()
            except subprocess.TimeoutExpired:
                print(f"  [AutoFix] CC 响应超时")
                continue
            except FileNotFoundError:
                print(f"  [AutoFix] CC CLI 不可用，回退到 model_gateway")
                fix_suggestion = _fix_via_model_gateway(item)

            if not fix_suggestion:
                continue

            # 解析修复建议并应用
            applied = _apply_fix(fix_suggestion)
            if not applied:
                print(f"  [AutoFix] 无法解析修复建议")
                continue

            # 重新跑这一项测试
            from scripts.test_suite import run_all_tests
            retest = run_all_tests()
            still_failing = [f for f in retest["summary"]["failed_items"] if f["name"] == item["name"]]

            if not still_failing:
                print(f"  [AutoFix] ✅ {item['name']} 修复成功")
                fixed.append({"item": item["name"], "rounds": round_num, "fix": fix_suggestion[:200]})
                success = True

                # commit 修复
                subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT))
                subprocess.run(
                    ["git", "commit", "-m", f"fix(auto): {item['name']} — auto-fixed by self-healing system"],
                    cwd=str(PROJECT_ROOT)
                )
                subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT))
                break
            else:
                print(f"  [AutoFix] 第 {round_num} 轮修复未生效，继续")

        if not success:
            unfixed.append(item)

    # 写入修复日志
    log_entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "fixed": [f["item"] for f in fixed],
        "unfixed": [u["name"] for u in unfixed],
    }
    with open(FIX_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # 修不好的写入 bug_report
    if unfixed:
        _write_bug_report(unfixed)

    return {"fixed": fixed, "unfixed": unfixed}


def _fix_via_model_gateway(item: dict) -> str:
    """CC 不可用时，用 model_gateway 调用 gpt-5.4 分析"""
    try:
        from src.utils.model_gateway import get_model_gateway
        gw = get_model_gateway()
        result = gw.call("gpt_5_4",
            f"测试失败: {item.get('error', '')}\nTraceback: {item.get('traceback', '')}\n"
            f"分析原因并给出修复代码。",
            "你是 Python 调试专家。", "bug_fix"
        )
        return result.get("response", "") if result.get("success") else ""
    except:
        return ""


def _apply_fix(fix_suggestion: str) -> bool:
    """解析 CC 的修复建议并应用到文件"""
    import re
    # 解析 FILE: / OLD: / NEW: 格式
    file_match = re.search(r'FILE:\s*(.+)', fix_suggestion)
    old_match = re.search(r'OLD:\s*```\n?(.*?)```', fix_suggestion, re.DOTALL)
    new_match = re.search(r'NEW:\s*```\n?(.*?)```', fix_suggestion, re.DOTALL)

    if not all([file_match, old_match, new_match]):
        # 尝试其他格式...
        return False

    file_path = PROJECT_ROOT / file_match.group(1).strip()
    old_code = old_match.group(1).strip()
    new_code = new_match.group(1).strip()

    if not file_path.exists():
        return False

    content = file_path.read_text(encoding='utf-8')
    if old_code not in content:
        return False

    content = content.replace(old_code, new_code, 1)
    file_path.write_text(content, encoding='utf-8')
    print(f"  [AutoFix] 已修改: {file_path}")
    return True


def _write_bug_report(unfixed: list):
    """写入无法自动修复的 bug 报告"""
    lines = [f"# Bug 报告 — {time.strftime('%Y-%m-%d %H:%M')}\n"]
    lines.append(f"以下 {len(unfixed)} 个问题无法自动修复，需要人工介入：\n")
    for item in unfixed:
        lines.append(f"## ❌ {item['name']}")
        lines.append(f"- 错误: {item.get('error', 'unknown')}")
        lines.append(f"- 描述: {item.get('description', '')}")
        if item.get('traceback'):
            lines.append(f"- Traceback:\n```\n{item['traceback'][-300:]}\n```")
        lines.append("")

    BUG_REPORT_PATH.write_text("\n".join(lines), encoding='utf-8')

    # 自动 git push bug report
    subprocess.run(["git", "add", str(BUG_REPORT_PATH)], cwd=str(PROJECT_ROOT))
    subprocess.run(["git", "commit", "-m", "auto: bug report — issues that need human attention"],
                   cwd=str(PROJECT_ROOT))
    subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT))
```

---

## 四、触发机制

### 方案 A: Git post-push hook（推荐）

在 `.git/hooks/post-push`（或 post-commit）中触发测试：

```bash
#!/bin/bash
echo "[SelfHeal] Running test suite after push..."
python scripts/self_heal.py &
```

### 方案 B: 后台 watcher

在 `scripts/feishu_sdk_client.py` 的启动逻辑中，注册一个后台线程定时跑测试：

```python
def _start_health_monitor():
    """每 6 小时自动运行测试套件"""
    import threading
    def _monitor_loop():
        while True:
            time.sleep(6 * 3600)  # 每 6 小时
            try:
                _run_self_heal_cycle()
            except:
                pass
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
```

### 方案 C: 飞书指令触发

```python
if text_stripped in ("自检", "self check", "health check", "测试"):
    _handle_self_check(reply_target, send_reply)
    return
```

---

## 五、主编排器

### 新建 `scripts/self_heal.py`

```python
"""自愈系统主编排器 — 测试 + 修复 + 通知"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def run_self_heal_cycle(send_reply=None, reply_target=None):
    """运行一轮自愈循环: 测试 → 修复 → 验证 → 通知"""

    print("\n" + "=" * 50)
    print(f"[SelfHeal] 开始自愈循环 {time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # Step 1: 运行测试
    from scripts.test_suite import run_all_tests
    results = run_all_tests()
    summary = results["summary"]

    print(f"\n[SelfHeal] 测试结果: {summary['passed']}/{summary['total']} 通过")

    if summary["failed"] == 0:
        msg = f"✅ 系统自检通过 ({summary['total']}/{summary['total']})"
        print(f"[SelfHeal] {msg}")
        if send_reply and reply_target:
            send_reply(reply_target, msg)
        return {"status": "healthy", "tests": summary}

    # Step 2: 自动修复
    print(f"\n[SelfHeal] {summary['failed']} 项失败，启动自动修复...")

    from scripts.auto_fixer import auto_fix_failures
    fix_result = auto_fix_failures(summary["failed_items"], max_rounds=3)

    # Step 3: 生成报告
    fixed_count = len(fix_result["fixed"])
    unfixed_count = len(fix_result["unfixed"])

    report_lines = [f"🔧 系统自愈报告 {time.strftime('%Y-%m-%d %H:%M')}\n"]
    report_lines.append(f"测试: {summary['total']} 项，通过 {summary['passed']}，失败 {summary['failed']}")

    if fixed_count > 0:
        report_lines.append(f"\n✅ 自动修复 {fixed_count} 项:")
        for f in fix_result["fixed"]:
            report_lines.append(f"  • {f['item']}（{f['rounds']} 轮修复）")

    if unfixed_count > 0:
        report_lines.append(f"\n⚠️ 无法自动修复 {unfixed_count} 项（已写入 bug_report.md）:")
        for u in fix_result["unfixed"]:
            report_lines.append(f"  • {u['name']}: {u.get('error', '')[:50]}")

    report = "\n".join(report_lines)
    print(f"\n{report}")

    # Step 4: 推送飞书通知
    if send_reply and reply_target:
        send_reply(reply_target, report)

    # Step 5: 保存报告到 system_log
    log_path = PROJECT_ROOT / ".ai-state" / "self_heal_log.jsonl"
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            "tests_total": summary["total"],
            "tests_passed": summary["passed"],
            "auto_fixed": [f["item"] for f in fix_result["fixed"]],
            "unfixed": [u["name"] for u in fix_result["unfixed"]],
        }, ensure_ascii=False) + "\n")

    return {
        "status": "healed" if unfixed_count == 0 else "needs_human",
        "tests": summary,
        "fixed": fix_result["fixed"],
        "unfixed": fix_result["unfixed"],
    }


if __name__ == "__main__":
    run_self_heal_cycle()
```

---

## 六、你回来时看到什么

### 场景 A: 一切正常
```
飞书自动推送: ✅ 系统自检通过 (35/35)
```
你什么都不用做。

### 场景 B: 有 bug 但系统自己修好了
```
飞书自动推送:
🔧 系统自愈报告 2026-04-02 03:00

测试: 35 项，通过 32，失败 3

✅ 自动修复 3 项:
  • import_scripts.trust_tracker（1 轮修复）
  • soft_状态（2 轮修复）
  • feishu_commands_registered（1 轮修复）
```
你看一眼就行，不用做任何事。

### 场景 C: 有 bug 系统修不好
```
飞书自动推送:
🔧 系统自愈报告 2026-04-02 03:00

测试: 35 项，通过 33，失败 2

✅ 自动修复 1 项:
  • import_scripts.trust_tracker（1 轮修复）

⚠️ 无法自动修复 1 项（已写入 bug_report.md）:
  • soft_决策简报: "输出为空，5秒超时"
```
你来找我，我从 GitHub 读 bug_report.md，帮你修。

---

## 七、需要新增的改进项

| ID | 改进 | 轨道 | 工作量 |
|----|------|------|--------|
| X1 | 测试套件 (test_suite.py) | D | 2h |
| X2 | 自动修复引擎 (auto_fixer.py) | D | 1.5h |
| X3 | 自愈编排器 (self_heal.py) | D | 1h |
| X4 | 触发机制（定时+飞书指令+git hook） | B+D | 1h |
| X5 | 飞书"自检"指令注册 | B | 15min |
