# CC 任务：飞书指令整合 + 功能全面排查 + 回归验证机制

> 背景：Day 12 的 model_gateway 拆分和 feishu_sdk_client_v2 重构过程中，token 统计等功能丢失。
> 本任务做三件事：排查所有功能现状 → 整合精简 → 建立防止未来再丢的机制。

---

## 第一步：功能现状排查

逐条检查以下功能是否仍然可用。对每条输出：✅ 可用 / ❌ 丢失 / ⚠️ 部分可用

### 飞书指令排查

对每条指令，检查方式是：在 `scripts/feishu_handlers/text_router.py`（或 text_handler）中找到对应的路由匹配 → 追踪到实际 handler 函数 → 确认函数存在且可调用。

```bash
# 批量排查路由匹配
grep -rn "token\|日报\|对齐\|知识库\|删除.*KB\|研究\|深度研究\|深度学习\|今晚研究\|JDM\|学习\|关注\|@dev\|设置目标\|进化记录\|系统状态\|状态\|导入文档\|PRD\|清单\|决策简报\|产品一页纸\|Demo\|demo\|圆桌\|重载模块" scripts/feishu_handlers/ scripts/feishu_sdk_client_v2.py
```

要排查的指令清单：

1. `token` / `tokens` / `用量` / `token统计` → token 使用量报告
2. `日报` → 系统日报
3. `对齐` → 每日对齐报告
4. `知识库` / `知识库 详细` → 知识库统计
5. `删除 KB xxx` → 删除知识库条目
6. `研究 XXX` → 单主题深度研究
7. `深度研究` → 预配置研究队列
8. `深度学习` → 多小时深度学习模式
9. `今晚研究` → 今晚研究队列
10. `JDM学习` → JDM 定向学习
11. `学习` → 手动触发一轮学习
12. `关注 XXX` → 动态添加学习主题
13. `@dev 需求描述` → 代码提案生成
14. `A` / `B` / `C` / `D` → 方案评价
15. `设置目标 XXX` → 产品目标设定
16. `进化记录` → 查看自进化历史
17. `系统状态` / `状态` → 系统健康状况
18. `导入文档` → inbox 文档导入
19. `PRD` / `清单` 等结构化文档快速通道
20. `决策简报 XXX` → 决策简报生成
21. `产品一页纸` → 产品 one-pager 生成
22. `生成HUD Demo` / `生成App Demo` / `Demo状态`
23. `圆桌:XXX` → 圆桌系统
24. `重载模块` → 飞书模块热重载

### 内部功能排查

25. `_log_token_usage` — 检查 `src/utils/model_gateway/` 各 provider 是否仍在调用
```bash
grep -rn "_log_token_usage\|log_token\|token_usage" src/utils/model_gateway/
```

26. URL 分享检测 + 平台识别
```bash
grep -rn "_has_shareable_url\|platform_search\|handle_share" scripts/feishu_handlers/
```

27. 图片消息 OCR 处理
```bash
grep -rn "handle_image\|ocr\|image_handler" scripts/feishu_handlers/
```

28. 语音消息转文字
```bash
grep -rn "handle_audio\|voice\|audio_handler\|transcrib" scripts/feishu_handlers/
```

29. 消息去重机制
```bash
grep -rn "processed_msg\|msg_cache\|dedup\|重复消息" scripts/feishu_sdk_client_v2.py scripts/feishu_handlers/
```

30. Watchdog 心跳监控
```bash
grep -rn "watchdog\|heartbeat\|Watchdog" scripts/feishu_sdk_client_v2.py scripts/feishu_handlers/
```

### 定时任务排查

31. 每天 00:00 自动深度学习
32. 每天 06:00 竞品监控扫描
33. 每天 07:00 系统日报推送
34. 每 30min/2h 自动学习轮次

```bash
grep -rn "scheduler\|_run_at\|定时\|cron\|schedule\|Timer\|setInterval" scripts/feishu_sdk_client_v2.py scripts/daily_learning.py scripts/feishu_handlers/
```

**输出一份排查报告**，格式：
```
功能排查报告
============
1. token统计: ❌ 丢失 — _log_token_usage 函数在 model_gateway 拆分时未迁移
2. 日报: ✅ 可用
3. ...
```

---

## 第二步：指令整合

排查完成后，按以下方案整合。最终只保留 10 个指令入口。

### 要合并的指令

**学习类合并**：`研究 XXX` / `深度研究` / `今晚研究` / `JDM学习` / `学习` / `关注 XXX` → 统一为：
- `深度学习` [时长] — 多小时深度学习模式（保持现有）
- `学习 XXX` — 单主题研究（合并"研究 XXX"）
- `学习 关注 XXX` — 添加持续关注主题（合并"关注 XXX"）
- 废弃：`深度研究`、`今晚研究`、`JDM学习` 作为独立入口（它们的功能通过 `学习 XXX` 或 `深度学习` 覆盖）

**知识库类合并**：`知识库` / `知识库 详细` / `删除 KB xxx` → 统一为：
- `知识库` — 基础统计
- `知识库 详细` — 详细统计（子命令）
- `知识库 删除 xxx` — 删除条目（子命令）

**日报类合并**：`对齐` 和 `日报` → 统一为：
- `日报` — 包含系统状态 + 知识库变化 + 对齐维度覆盖，一份报告覆盖两个功能

### 要砍掉的指令

- `设置目标 XXX` — 产品目标在 product_anchor.md 管理，不通过飞书消息修改
- `进化记录` — 被圆桌知识结晶机制替代
- `@dev 需求描述` — 有 CC 直接执行，不再需要飞书中转

对这些指令，在路由中移除匹配，但保留 handler 函数代码（注释标记为 deprecated），不删除代码防止将来需要恢复。

### 定时任务整合

三个独立定时器合并为一个夜间流水线：
```
00:00 → 启动深度学习
深度学习结束 → 自动触发竞品监控扫描
竞品监控结束 → 生成日报 → 飞书推送
```
不再用三个独立的 `_run_at()` 定时器。

每 30min/2h 自动学习保留，但与深度学习共享任务池（深度学习运行中时，自动学习跳过）。

### 整合后的最终指令表

| 指令 | 路由匹配 | Handler |
|------|---------|---------|
| `深度学习` [时长] | `深度学习` | deep_learning |
| `学习 XXX` | `学习 ` + topic | single_topic_research |
| `学习 关注 XXX` | `学习 关注` + topic | add_watch_topic |
| `圆桌:XXX` | `圆桌:` / `圆桌：` | roundtable.run_task |
| `知识库` [详细/删除] | `知识库` | kb_management |
| `日报` | `日报` | daily_report (含对齐) |
| `token` | `token` / `tokens` / `用量` | token_stats |
| `状态` | `状态` / `系统状态` | system_status |
| `PRD` / 结构化文档 | 现有 structured_doc 匹配 | structured_doc |
| `重载模块` | `重载模块` | hot_reload |
| `生成HUD Demo` 等 | 现有匹配 | demo_generator (标记待迁移圆桌) |

---

## 第三步：修复所有丢失的功能

根据第一步排查结果，修复所有标记为 ❌ 的功能。

**已知必须修复的：**

### token 统计修复

1. 确认 `_log_token_usage` 函数是否存在于 `src/utils/model_gateway/` 的某个模块中
2. 如果不存在，在 `src/utils/model_gateway/config.py`（或合适的位置）中恢复该函数
3. 在每个 provider 中恢复调用点：
   - `providers/azure_openai.py` — 在成功返回前记录 usage
   - `providers/gemini.py` — 在成功返回前记录（估算 token）
   - `providers/volcengine.py` — 在成功返回前记录
   - `providers/others.py` — 同上
4. 确认 token 数据写入 `.ai-state/token_usage.json`
5. 确认飞书路由中 `token` 指令能读取并展示数据

### 其他丢失功能

根据排查结果逐个修复，每个修复后立即验证。

---

## 第四步：建立回归验证机制

### 4a. 创建 `.ai-state/capability_registry.json`

```json
{
  "version": "2026-04-06",
  "feishu_commands": {
    "深度学习": {
      "match_patterns": ["深度学习"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_deep_learning",
      "depends_on": ["scripts/deep_research/runner.py"]
    },
    "学习 XXX": {
      "match_patterns": ["学习 "],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_single_research",
      "depends_on": ["scripts/deep_research/pipeline.py"]
    },
    "圆桌": {
      "match_patterns": ["圆桌:", "圆桌："],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "roundtable.run_task",
      "depends_on": ["scripts/roundtable/__init__.py"]
    },
    "token": {
      "match_patterns": ["token", "tokens", "用量"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_token_stats",
      "depends_on": ["src/utils/model_gateway/config.py"]
    },
    "日报": {
      "match_patterns": ["日报"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_daily_report",
      "depends_on": ["scripts/daily_system_report.py"]
    },
    "知识库": {
      "match_patterns": ["知识库"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_kb_management",
      "depends_on": ["src/tools/knowledge_base.py"]
    },
    "状态": {
      "match_patterns": ["状态", "系统状态"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_system_status",
      "depends_on": []
    },
    "重载模块": {
      "match_patterns": ["重载模块"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "handle_hot_reload",
      "depends_on": []
    },
    "PRD": {
      "match_patterns": ["PRD", "清单"],
      "handler_file": "scripts/feishu_handlers/structured_doc.py",
      "handler_function": "try_structured_doc_fast_track",
      "depends_on": ["scripts/structured_doc.py"]
    },
    "Demo生成": {
      "match_patterns": ["生成hud demo", "生成app demo", "demo状态"],
      "handler_file": "scripts/feishu_handlers/text_router.py",
      "handler_function": "demo_generator",
      "depends_on": ["scripts/demo_generator.py"],
      "note": "待迁移到圆桌系统"
    }
  },
  "internal_functions": {
    "token_logging": {
      "entry_point": "_log_token_usage",
      "location": "src/utils/model_gateway/config.py",
      "callers": [
        "src/utils/model_gateway/providers/azure_openai.py",
        "src/utils/model_gateway/providers/gemini.py",
        "src/utils/model_gateway/providers/volcengine.py",
        "src/utils/model_gateway/providers/others.py"
      ]
    },
    "url_share_detection": {
      "entry_point": "_has_shareable_url",
      "location": "scripts/feishu_handlers/text_router.py",
      "callers": ["scripts/feishu_handlers/text_router.py"]
    },
    "image_ocr": {
      "entry_point": "handle_image_message",
      "location": "scripts/feishu_handlers/image_handler.py",
      "callers": ["scripts/feishu_sdk_client_v2.py"]
    },
    "message_dedup": {
      "entry_point": "_processed_msgs",
      "location": "scripts/feishu_sdk_client_v2.py",
      "callers": ["scripts/feishu_sdk_client_v2.py"]
    },
    "watchdog": {
      "entry_point": "Watchdog",
      "location": "scripts/feishu_sdk_client_v2.py",
      "callers": ["scripts/feishu_sdk_client_v2.py"]
    }
  },
  "scheduled_tasks": {
    "nightly_pipeline": {
      "trigger": "00:00",
      "steps": ["deep_learning", "competitor_monitor", "daily_report"],
      "location": "scripts/feishu_sdk_client_v2.py"
    },
    "periodic_learning": {
      "trigger": "every 30min or 2h",
      "location": "scripts/daily_learning.py"
    }
  }
}
```

### 4b. 创建 `scripts/regression_check.py`

```python
"""
回归验证脚本：读取 capability_registry.json，逐条验证功能完整性。
用法：
  python scripts/regression_check.py          # 全量检查
  python scripts/regression_check.py --quick   # 快速检查（只验证文件和函数存在性）
"""

import json
import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def load_registry():
    reg_path = PROJECT_ROOT / ".ai-state" / "capability_registry.json"
    return json.loads(reg_path.read_text(encoding="utf-8"))

def check_feishu_commands(registry):
    """检查每个飞书指令的 handler 是否存在且可调用"""
    results = []
    for cmd_name, cmd_info in registry["feishu_commands"].items():
        handler_file = PROJECT_ROOT / cmd_info["handler_file"]
        status = "✅"
        issues = []
        
        # 检查 handler 文件存在
        if not handler_file.exists():
            status = "❌"
            issues.append(f"文件不存在: {cmd_info['handler_file']}")
        else:
            # 检查 handler 文件中包含 handler 函数
            content = handler_file.read_text(encoding="utf-8")
            func_name = cmd_info["handler_function"].split(".")[-1]
            if func_name not in content:
                status = "❌"
                issues.append(f"函数 {func_name} 未在文件中找到")
            
            # 检查 match_patterns 在路由文件中有对应匹配
            for pattern in cmd_info["match_patterns"]:
                if pattern not in content:
                    # 也检查 text_router
                    router_content = (PROJECT_ROOT / "scripts/feishu_handlers/text_router.py").read_text(encoding="utf-8")
                    if pattern not in router_content:
                        status = "⚠️"
                        issues.append(f"路由模式 '{pattern}' 未在路由文件中找到")
        
        # 检查依赖文件
        for dep in cmd_info.get("depends_on", []):
            if not (PROJECT_ROOT / dep).exists():
                status = "❌"
                issues.append(f"依赖文件不存在: {dep}")
        
        results.append((cmd_name, status, issues))
    return results

def check_internal_functions(registry):
    """检查内部功能的入口点和调用点"""
    results = []
    for func_name, func_info in registry["internal_functions"].items():
        status = "✅"
        issues = []
        
        # 检查入口点文件
        loc = PROJECT_ROOT / func_info["location"]
        if not loc.exists():
            status = "❌"
            issues.append(f"入口文件不存在: {func_info['location']}")
        else:
            content = loc.read_text(encoding="utf-8")
            if func_info["entry_point"] not in content:
                status = "❌"
                issues.append(f"入口函数 {func_info['entry_point']} 未找到")
        
        # 检查调用点
        for caller in func_info.get("callers", []):
            caller_path = PROJECT_ROOT / caller
            if not caller_path.exists():
                status = "⚠️"
                issues.append(f"调用方文件不存在: {caller}")
            else:
                caller_content = caller_path.read_text(encoding="utf-8")
                if func_info["entry_point"] not in caller_content:
                    status = "❌"
                    issues.append(f"调用方 {caller} 中未调用 {func_info['entry_point']}")
        
        results.append((func_name, status, issues))
    return results

def main():
    registry = load_registry()
    
    print("=" * 60)
    print("功能回归验证报告")
    print("=" * 60)
    
    print("\n--- 飞书指令 ---")
    cmd_results = check_feishu_commands(registry)
    fail_count = 0
    for name, status, issues in cmd_results:
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      → {issue}")
            if status == "❌":
                fail_count += 1
    
    print("\n--- 内部功能 ---")
    func_results = check_internal_functions(registry)
    for name, status, issues in func_results:
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      → {issue}")
            if status == "❌":
                fail_count += 1
    
    print("\n" + "=" * 60)
    if fail_count == 0:
        print("✅ 全部通过")
    else:
        print(f"❌ {fail_count} 个功能缺失，需要修复")
    print("=" * 60)
    
    return fail_count

if __name__ == "__main__":
    sys.exit(main())
```

### 4c. 建立使用规则

在项目根目录的 `CLAUDE.md`（CC 的全局指令文件）中追加：

```markdown
## 重构/拆分规则

任何涉及文件拆分、重命名、模块重组的任务，必须执行以下步骤：

1. 重构前：运行 `python scripts/regression_check.py`，保存结果为 `pre_refactor_check.txt`
2. 执行重构
3. 重构后：再次运行 `python scripts/regression_check.py`，保存结果为 `post_refactor_check.txt`
4. 对比两份结果：任何从 ✅ 变为 ❌ 或 ⚠️ 的项都是 bug，必须修复后才能 commit
5. 如果新增了功能，必须同步更新 `.ai-state/capability_registry.json`

违反此规则的 commit 视为不合格。
```

---

## 执行顺序

1. 先跑第一步排查，输出完整报告
2. 根据报告 + 第二步整合方案，一起做（合并指令 + 修复丢失功能）
3. 创建 capability_registry.json
4. 创建 regression_check.py
5. 运行 regression_check.py 确认全部 ✅
6. 更新 CLAUDE.md
7. 全部完成后 git commit

每步完成后飞书通知进度。
