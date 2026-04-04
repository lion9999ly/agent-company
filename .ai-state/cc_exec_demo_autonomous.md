# 补充改进：Demo 全自主闭环

> 目标: 飞书发"生成 HUD Demo"后，系统完全自主跑完——缺信息自己搜、缺设定问你、自动调试、支持迭代修改。你看到的是经过调教的成品。

---

## V1: Demo 信息自动补齐

Demo 生成器在开始前，自动检查 KB 中是否有足够的设计信息。如果缺失，自动触发针对性搜索。

```python
def _ensure_demo_prerequisites(demo_type: str) -> dict:
    """检查并补齐 Demo 生成所需的前置信息"""
    
    required_knowledge = {
        "hud_demo": [
            ("HUD 信息布局规范", "HUD layout specification display position"),
            ("HUD 色彩方案", "HUD color scheme helmet visor daylight night"),
            ("HUD 信息优先级", "HUD information priority navigation speed call"),
            ("HUD 动画规范", "HUD animation transition fade duration"),
            ("竞品 HUD 布局参考", "EyeRide Jarvish Forcite HUD layout screenshot"),
        ],
        "app_demo": [
            ("App 配对流程", "smart helmet app pairing bluetooth flow"),
            ("App 骑行仪表盘", "motorcycle riding dashboard UI speedometer"),
            ("App 组队地图", "group ride map real-time location sharing"),
            ("竞品 App 参考", "Cardo Sena app UI design screenshot"),
        ],
    }
    
    results = {}
    missing = []
    
    for topic, search_query in required_knowledge.get(demo_type, []):
        kb_results = search_knowledge(topic, limit=3)
        if len(kb_results) >= 2 and any(r.get("confidence") in ("high", "authoritative") for r in kb_results):
            results[topic] = kb_results
        else:
            missing.append((topic, search_query))
    
    # 自动补齐缺失信息
    if missing:
        print(f"  [DemoPrep] 缺少 {len(missing)} 项信息，自动搜索补齐...")
        for topic, query in missing:
            # 用三通道并行搜索
            search_result = _quick_research(query)
            if search_result:
                add_knowledge(title=f"[Demo准备] {topic}", domain="components",
                             content=search_result, tags=["demo_prep"], 
                             source="auto_demo_prep", confidence="medium")
                results[topic] = [{"content": search_result}]
    
    return results
```

commit: `"feat: demo auto-prerequisite — auto-research missing design information before generation"`

---

## V2: 生成中暂停等人确认

当 Demo 生成器遇到需要用户决策的问题时（设计偏好、功能取舍），通过飞书提问并等待回答。

```python
# 在飞书交互层中维护一个"等待回答"状态
_demo_pending_questions = {}  # {open_id: {"question": "...", "callback": func}}

def _ask_user_preference(question: str, options: list, reply_target: str, 
                          send_reply, open_id: str, callback):
    """暂停 Demo 生成，问用户一个设计偏好问题"""
    
    options_text = "\n".join([f"  {i+1}. {opt}" for i, opt in enumerate(options)])
    send_reply(reply_target, 
        f"🎨 Demo 设计确认\n\n{question}\n\n{options_text}\n\n回复数字选择，或输入你的想法。")
    
    _demo_pending_questions[open_id] = {
        "question": question,
        "options": options,
        "callback": callback,
    }


def _handle_demo_preference_reply(text: str, open_id: str) -> bool:
    """处理用户对 Demo 设计问题的回复"""
    pending = _demo_pending_questions.get(open_id)
    if not pending:
        return False
    
    # 解析回复（数字选择或自由文本）
    choice = text.strip()
    callback = pending["callback"]
    del _demo_pending_questions[open_id]
    
    # 回调继续 Demo 生成
    threading.Thread(target=callback, args=(choice,), daemon=True).start()
    return True
```

Demo 生成器中使用：
```python
    # 检测到需要用户决策
    if not design_spec.get("nav_arrow_position"):
        _ask_user_preference(
            "导航箭头放在视野的什么位置？",
            ["中央偏下（推荐，视线自然落点）", "左下角（不遮挡前方视野）", "右下角", "底部居中"],
            reply_target, send_reply, open_id,
            callback=lambda choice: _continue_demo_with_preference("nav_position", choice)
        )
        return  # 暂停，等用户回复后 callback 继续
```

commit: `"feat: demo interactive preferences — pause and ask user for design decisions"`

---

## V3: 成品迭代修改

Demo 发送到飞书后，用户可以直接说"导航箭头改大一点"，系统基于上一版代码修改，而不是从头生成。

```python
# 维护每个用户的最近 Demo 状态
_demo_sessions = {}  # {open_id: {"type": "hud", "html_path": "...", "design_spec": {...}, "version": 1}}

def _handle_demo_iteration(text: str, open_id: str, reply_target: str, send_reply):
    """处理 Demo 迭代修改请求"""
    session = _demo_sessions.get(open_id)
    if not session:
        send_reply(reply_target, "⚠️ 没有正在进行的 Demo，请先发"生成 HUD Demo"")
        return
    
    html_path = session["html_path"]
    current_code = Path(html_path).read_text(encoding='utf-8')
    
    send_reply(reply_target, f"🔄 修改 Demo v{session['version']}...")
    
    def _run():
        # 让模型基于当前代码 + 修改请求，生成新版本
        result = gateway.call("gpt_5_4",
            f"以下是当前 HUD Demo 的 HTML 代码:\n\n```html\n{current_code[:8000]}\n```\n\n"
            f"用户要求修改: {text}\n\n"
            f"请输出修改后的完整 HTML 代码。只改用户要求的部分，保持其他不变。",
            "你是前端工程师，精确修改 UI。", "code_generation")
        
        if result.get("success"):
            # 提取并保存新代码
            new_code = _extract_html(result["response"])
            new_version = session["version"] + 1
            new_path = Path(html_path).parent / f"hud_demo_v{new_version}.html"
            new_path.write_text(new_code, encoding='utf-8')
            
            # 自动截屏验证
            screenshots = auto_debug_html(str(new_path), session.get("design_spec_text", ""))
            
            # 更新 session
            session["html_path"] = str(new_path)
            session["version"] = new_version
            
            # 发送新版本截图
            send_reply(reply_target, f"✅ Demo v{new_version} 已更新（基于你的修改: {text[:30]}）")
            # 发送截图文件...
        else:
            send_reply(reply_target, f"修改失败: {result.get('error', '')[:200]}")
    
    threading.Thread(target=_run, daemon=True).start()
```

在 text_router.py 中，当用户有活跃的 Demo session 时，自然语言修改请求自动路由到迭代：

```python
    # 如果用户有活跃的 Demo session，检查是否是修改请求
    if open_id in _demo_sessions:
        demo_keywords = ["改", "调", "大一点", "小一点", "换", "移", "加", "删", "颜色", "位置", "字体", "动画"]
        if any(kw in text_stripped for kw in demo_keywords):
            _handle_demo_iteration(text_stripped, open_id, reply_target, send_reply)
            return
```

commit: `"feat: demo iterative refinement — modify existing demo based on natural language feedback"`

---

## V4: Demo 全流程编排器

把 V1-V3 和已有的 P2-P6、S1/S6 串成一个完整的自主流水线：

```python
def generate_demo_autonomous(demo_type: str, reply_target: str, send_reply, 
                               open_id: str, gateway):
    """Demo 全自主生成流水线
    
    完整流程:
    1. 检查并补齐前置信息（V1）
    2. 生成设计规范（P2）
    3. 遇到需要用户决策的点 → 飞书提问等回复（V2）
    4. 生成场景脚本（P3）
    5. 生成代码（P5/P6）
    6. 自动截屏验证修复 5 轮（S1/S6）
    7. 发送成品截图+文件到飞书
    8. 进入迭代模式，等待用户修改请求（V3）
    """
    
    send_reply(reply_target, f"🚀 开始自主生成 {demo_type} Demo...\n预计 5-10 分钟")
    
    # Step 1: 前置信息检查
    send_reply(reply_target, "📚 检查设计信息...")
    prerequisites = _ensure_demo_prerequisites(demo_type)
    
    # Step 2: 生成设计规范
    send_reply(reply_target, "📐 生成设计规范...")
    design_spec = _generate_design_spec(demo_type, prerequisites, gateway)
    
    # Step 3: 检查是否需要用户输入（如有，V2 会暂停等待）
    # ...由 V2 的 callback 机制处理
    
    # Step 4: 生成场景脚本
    send_reply(reply_target, "🎬 生成场景脚本...")
    scenario = _generate_scenario_script(demo_type, design_spec, gateway)
    
    # Step 5: 生成代码
    send_reply(reply_target, "💻 生成 Demo 代码...")
    html_path = _generate_demo_code(demo_type, design_spec, scenario, gateway)
    
    # Step 6: 自动视觉调试
    send_reply(reply_target, "🔍 自动视觉调试（最多 5 轮）...")
    debug_result = auto_debug_html(html_path, design_spec, max_rounds=5)
    
    if debug_result["success"]:
        send_reply(reply_target, f"✅ Demo 生成完成（{debug_result['rounds']} 轮调试通过）")
    else:
        send_reply(reply_target, f"⚠️ Demo 生成完成但有 {len(debug_result.get('remaining_issues',[]))} 个未解决问题")
    
    # Step 7: 发送成品
    # 发送截图 + HTML 文件到飞书...
    
    # Step 8: 进入迭代模式
    _demo_sessions[open_id] = {
        "type": demo_type,
        "html_path": html_path,
        "design_spec_text": str(design_spec),
        "version": 1,
    }
    send_reply(reply_target, "🎨 Demo 已进入迭代模式。你可以直接说修改意见，如"导航箭头改大一点"、"颜色换成橙色"。说"退出Demo"结束。")
```

commit: `"feat: demo autonomous orchestrator — end-to-end generation with auto-research, user interaction, visual debug, and iterative refinement"`

---

## 效果

飞书发"生成 HUD Demo"后的完整体验：

```
Leo: 生成 HUD Demo
Bot: 🚀 开始自主生成 HUD Demo... 预计 5-10 分钟
Bot: 📚 检查设计信息... 缺少 2 项，自动搜索补齐中
Bot: 📐 生成设计规范...
Bot: 🎨 Demo 设计确认
    导航箭头放在视野的什么位置？
    1. 中央偏下（推荐）
    2. 左下角
    3. 右下角
    4. 底部居中
Leo: 1
Bot: 💻 生成 Demo 代码...
Bot: 🔍 自动视觉调试（第 1 轮: 发现 2 个问题，修复中）
Bot: 🔍 自动视觉调试（第 2 轮: 全部通过）
Bot: ✅ Demo 生成完成（2 轮调试通过）
Bot: [发送截图]
Bot: [发送 HTML 文件]
Bot: 🎨 Demo 已进入迭代模式。说修改意见即可。

Leo: 导航箭头改大一点，颜色换成橙色
Bot: 🔄 修改 Demo v1...
Bot: ✅ Demo v2 已更新
Bot: [发送新截图]

Leo: 加一个来电通知的弹出动画
Bot: 🔄 修改 Demo v2...
Bot: ✅ Demo v3 已更新
Bot: [发送新截图]

Leo: 退出Demo
Bot: ✅ 已退出 Demo 迭代模式。最终版本: v3
```
