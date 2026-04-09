# CC 执行指令：Day 17 诊断修复（Part 2/2 — 验证脚本 + 自验收流程）

> 修完 Part 1 全部 20 个修复后执行本文件

---

## 步骤 1：创建验证脚本

把以下内容写入 `scripts/diagnostic_verify.py`：

```python
"""Day 17 诊断修复验证 — 21 个断点逐条代码级检查"""
import json, os, sys, re, subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "passed": condition, "detail": detail})
    print(f"  [{'OK' if condition else 'X'}] {name} — {detail}")

print("=" * 60)
print("Day 17 诊断修复验证（21 个断点）")
print("=" * 60)

# --- 读取源码 ---
def read(path):
    p = PROJECT_ROOT / path
    return p.read_text(encoding='utf-8') if p.exists() else ""

agent = read("scripts/agent.py")
rt = read("scripts/roundtable/roundtable.py")
gen = read("scripts/roundtable/generator.py")
ver = read("scripts/roundtable/verifier.py")
al = read("scripts/auto_learn.py")
cm = read("scripts/competitor_monitor.py")
nr = read("scripts/feishu_handlers/notify_rules.py")
lh = read("scripts/feishu_handlers/learning_handlers.py")
ih = read("scripts/feishu_handlers/import_handlers.py")
fo = read("scripts/feishu_output.py")
ri = read("scripts/roundtable/__init__.py")
hook_path = PROJECT_ROOT / ".git/hooks/post-commit"
hook = hook_path.read_text(encoding='utf-8', errors='ignore') if hook_path.exists() else ""

print("\n--- P0 ---")
# #1 agent.py 无 shell=True 在 handle_with_claude_code 中
agent_hwcc = agent.split("def handle_with_claude_code")[1] if "def handle_with_claude_code" in agent else ""
check("#1 agent 无 shell=True",
      "shell=True" not in agent_hwcc,
      "handle_with_claude_code 不应有 shell=True")

# #4 research_task_pool.yaml 存在且有内容
rtp = PROJECT_ROOT / ".ai-state/research_task_pool.yaml"
check("#4 research_task_pool.yaml 存在",
      rtp.exists() and rtp.stat().st_size > 100,
      f"大小: {rtp.stat().st_size if rtp.exists() else 0}")

print("\n--- P1 ---")
# #2 监控范围文件名正确
check("#2 agent 读 competitor_monitor_config.json",
      "competitor_monitor_config.json" in agent and "monitor_scope.json" not in agent)

# #3 hook 无 SDK 重启
check("#3 hook 无 start_sdk",
      "start_sdk" not in hook and "stop_sdk" not in hook)

# #5 feishu_output 内容传递
check("#5 feishu_output 有 stdin 或临时文件",
      "input=" in fo or "temp" in fo.lower() or "NamedTemporaryFile" in fo or "markdown-file" in fo)

# #7 反弹检测和第一轮比
check("#7 反弹检测 convergence_trace[0]",
      "convergence_trace[0]" in rt)

# #13 verifier 加载 task 规则文件
check("#13 verifier 加载 task_ 规则",
      "task_" in ver and "load_rules" in ver.split("_get_all_rules")[1][:500] if "_get_all_rules" in ver else False)

# #14 autolearn covered 标记
save_count = al.count("_save_covered_topic")
# 只应在 add_knowledge 附近出现 1 次
check("#14 autolearn covered 标记次数合理",
      save_count <= 2,
      f"出现 {save_count} 次")

# #17 competitor_monitor import 路径
check("#17 competitor_monitor 不用旧 import",
      "feishu_sdk_client" not in cm or "chat_helpers" in cm)

# #18 should_notify 被调用
all_py = list(PROJECT_ROOT.rglob("scripts/**/*.py"))
callers = []
for f in all_py:
    try:
        if "should_notify" in f.read_text(encoding='utf-8', errors='ignore') and f.name != "notify_rules.py":
            callers.append(f.name)
    except:
        pass
check("#18 should_notify 被至少 2 个文件调用",
      len(callers) >= 2,
      f"调用者: {callers}")

# #20 learning_handlers 调用正确函数
check("#20 learning_handlers 调 auto_learn_cycle",
      "auto_learn_cycle" in lh and "run_auto_learn" not in lh)

print("\n--- P2 ---")
# #6 hook status 更新
check("#6 hook 有 git log 更新 status",
      "git log" in hook and "system_status" in hook)

# #8 因果链 P0 ID
check("#8 critic prompt 有 P0-1 ID 要求",
      "P0-1" in rt or "P0-" in rt)

# #10 generator 有 gpt_5_3_codex
check("#10 generator 有 gpt_5_3_codex",
      "gpt_5_3_codex" in gen)

# #11 generator assemble 防御裸 JS
assemble = gen.split("_assemble_html")[1][:1000] if "_assemble_html" in gen else ""
check("#11 assemble 有裸 JS 处理",
      "script" in assemble.lower() and ("else" in assemble or "wrap" in assemble.lower() or "没有" in assemble))

# #12 verifier 字体 CDN 白名单
check("#12 verifier 豁免字体 CDN",
      "fonts" in ver or "font" in ver.split("no_external_deps")[1][:300] if "no_external_deps" in ver else False)

# #15 generator.fix 有 task 参数
fix_section = gen.split("async def fix")[1][:300] if "async def fix" in gen else ""
check("#15 generator.fix 有 task 参数",
      "task" in fix_section)

# #16 competitor_monitor 有影响研判
check("#16 competitor_monitor 有 impact 研判",
      "impact" in cm.lower() and ("assess" in cm.lower() or "relevance" in cm.lower() or "判" in cm))

# #19 agent.py 复用 handler 实现
check("#19 agent 复用 handler（不重复实现）",
      "from scripts.feishu_handlers" in agent or "_handle_dashboard" in agent or "text_router" in agent)

# #21 import_handlers 不用旧 import
check("#21 import_handlers 无旧 feishu_sdk_client",
      "feishu_sdk_client" not in ih or "chat_helpers" in ih)

# --- 汇总 ---
print("\n" + "=" * 60)
passed = sum(1 for r in results if r["passed"])
total = len(results)
print(f"通过率: {passed}/{total}")
if passed < total:
    print("\n未通过项:")
    for r in results:
        if not r["passed"]:
            print(f"  ❌ {r['name']}: {r['detail']}")
print("=" * 60)

# 写报告
report = f"# Day 17 诊断修复验证报告\n\n**通过率**: {passed}/{total}\n\n## 代码层验证\n\n"
for r in results:
    s = "✅" if r["passed"] else "❌"
    report += f"- {s} {r['name']}: {r['detail']}\n"

report_path = PROJECT_ROOT / ".ai-state/diagnostic_verify_report.md"
report_path.write_text(report, encoding='utf-8')
print(f"\n报告: {report_path}")
```

---

## 步骤 2：跑代码验证

```bash
python scripts/diagnostic_verify.py
```

如果通过率 < 18/21，根据未通过项继续修复，再跑一次，直到 >= 18/21。

---

## 步骤 3：跑运行时验证（CC 自己发飞书命令）

在飞书发以下 5 条消息并检查回复：

| 消息 | 期望回复 | 判定 |
|------|---------|------|
| 帮我看下 roundtable_runs 目录下有哪些文件 | 返回文件/目录列表（不是 GPT 兜底回复） | agent 模式生效 |
| 监控范围 | 返回 6 层配置（直接竞品/技术供应链/...） | 文件名修复 |
| 状态 | 包含最新 commit message | status 更新 |
| 自学习 | 返回"已启动"（不是 ImportError） | 函数名修复 |
| 日志 10 | 返回最近日志行 | agent 快速通道 |

把结果追加到 `.ai-state/diagnostic_verify_report.md`：
```
## 运行时验证

- ✅/❌ agent 模式: {实际回复前 50 字}
- ✅/❌ 监控范围: {实际回复前 50 字}
- ✅/❌ 状态: {实际回复前 50 字}
- ✅/❌ 自学习: {实际回复前 50 字}
- ✅/❌ 日志: {实际回复前 50 字}
```

---

## 步骤 4：结果发 GitHub Issue

```python
python -c "
import json, os, requests
token = open('.env').read().split('GITHUB_TOKEN=')[1].split('\n')[0].strip()
report = open('.ai-state/diagnostic_verify_report.md', encoding='utf-8').read()
resp = requests.post(
    'https://api.github.com/repos/lion9999ly/agent-company/issues',
    headers={'Authorization': f'token {token}'},
    json={'title': '[验证] Day 17 诊断修复验证结果', 'body': report, 'labels': ['diagnostics']}
)
print(f'Issue created: {resp.json().get(\"html_url\")}')
"
```

---

## 步骤 5：飞书通知 Leo

验证全通过时：
```
lark-cli im +messages-send --receive-id ou_8e5e4f183e9eca4241378e96bac3a751 --receive-type open_id --msg-type text --content '{"text":"✅ Day 17 诊断修复完成\n\n代码验证: X/21 通过\n运行时验证: 5/5 通过\n\n验证报告已发 GitHub Issue"}' --as bot
```

有未通过项时：
```
lark-cli im +messages-send --receive-id ou_8e5e4f183e9eca4241378e96bac3a751 --receive-type open_id --msg-type text --content '{"text":"⚠️ Day 17 诊断修复部分未通过\n\n代码验证: X/21\n运行时验证: Y/5\n\n详见 GitHub Issue，等待 Claude Chat 审查"}' --as bot
```
