# PRD 输出质量彻底修复 — Prompt 优化 + 文件交付 + 结构化输出

> 生成时间: 2026-03-27
> 问题: PRD 清单输出质量差（不按用户框架、缺失功能、格式混乱）+ Excel/文件发送不生效
> 目标: 用户发 PRD 类需求 → 收到高质量 Excel 文件 + 飞书树形摘要

---

## 当前问题汇总（必须全部解决）

1. **CPO 没输出 JSON**：明明要求了结构化 JSON，CPO 输出了 markdown 表格片段
2. **只发了一小段**：4240 字，只有"实体按键交互"这一个片段，不是完整清单
3. **没收到 Excel 文件**：_send_file_to_feishu 函数大概率没实现完整或 token 获取失败
4. **Agent 不按用户框架**：用户给了 16 个 HUD 一级功能，Agent 自己重组成 4 个
5. **缺失大量功能**：胎温胎压、开机动画、消息、简易路线、AI 剪片、"我的"Tab 等全没有

---

## Task 1: 修复 CPO 整合的 JSON 输出

问题根因：CPO synthesis prompt 中虽然要求了 JSON，但 LLM 仍然倾向输出 markdown。需要更强的格式约束。

### 1.1 修改 router.py 的 cpo_synthesis 函数

找到 cpo_synthesis 函数中检测到"清单/表格/excel"后设置 structured_prompt 的地方：

```bash
grep -n "structured_prompt\|format_hint\|清单\|JSON.*数组\|结构化" src/graph/router.py | head -20
```

替换 structured_prompt 为更强的版本。关键改动：把 JSON 格式要求从 system_prompt 追加改为**直接替换整个 synthesis prompt**——不给 LLM 选择余地：

```python
    # 检测用户是否要求清单/表格格式
    task_goal = state.get("task_contract", {}).get("task_goal", "")
    wants_structured = any(kw in task_goal for kw in ["清单", "表格", "excel", "Excel", "列表", "PRD"])
    
    if wants_structured:
        # 直接用结构化专用 prompt 替换整个整合 prompt
        # 不追加到原 prompt 后面——完全替代
        
        structured_system = (
            "你是智能摩托车全盔项目的 CPO。你必须输出一个 JSON 数组，不要输出任何其他内容。\n"
            "不要输出 markdown、不要输出解释文字、不要输出表格、不要输出标题。\n"
            "只输出一个以 [ 开头、以 ] 结尾的 JSON 数组。\n\n"
            "每个元素格式：\n"
            '{"module":"模块名","level":"L1或L2或L3","parent":"父功能名(L1填空字符串)","name":"功能名称","priority":"P0或P1或P2或P3","interaction":"交互方式(HUD/语音/按键/App/灯光)","description":"一句话描述","acceptance":"可测试的验收标准(含具体数字)","dependencies":"关联功能","note":"备注"}\n\n'
            "规则：\n"
            "1. 如果用户给了功能框架，以用户的一级功能作为 L1，不能重新归类\n"
            "2. 每个 L1 下至少 3 个 L2，每个 L2 至少 2 个 L3\n"
            "3. 用户列出的所有功能必须出现，不能删除\n"
            "4. 优先级统一用 P0/P1/P2/P3\n"
            "5. 验收标准必须可测试（含数字，如'成功率≥95%'、'响应时间≤3秒'）\n"
            "6. 你补充的功能在 note 中标注[补充]\n"
            "7. 合并三个 Agent 的分析，去重后统一输出，不暴露内部讨论\n"
        )
        
        structured_user = (
            f"以下是三个 Agent 的分析结果，请合并去重后输出 JSON 数组。\n\n"
            f"用户原始需求：\n{task_goal}\n\n"
            f"Agent 分析：\n{merge_summary[:12000]}\n\n"
            f"只输出 JSON 数组，不要有任何其他文字。以 [ 开头，以 ] 结尾。"
        )
        
        result = gateway.call_azure_openai("cpo", structured_user, structured_system, "synthesis")
        
        if result.get("success"):
            synthesis = result["response"]
            # 确保输出是 JSON
            import re
            json_match = re.search(r'\[[\s\S]*\]', synthesis)
            if json_match:
                synthesis = json_match.group()  # 只保留 JSON 部分
            print(f"[CPO_Synthesis] 结构化输出: {len(synthesis)} 字")
        else:
            # 降级到普通整合
            synthesis = merge_summary
            print(f"[CPO_Synthesis] 结构化调用失败，降级到普通整合")
    else:
        # 非清单类任务，走原有整合逻辑
        # ... 原有代码 ...
```

### 1.2 增加 JSON 输出的 token 上限

结构化 JSON 对 token 需求大（79 条功能 × 每条约 200 token = 16000 token）。确认 call_azure_openai 的 max_tokens 参数是否足够：

```bash
grep -n "max_tokens\|max_output" src/utils/model_gateway.py | head -10
```

如果 max_tokens < 16000，改为 16384 或更高（针对 synthesis 任务类型）。

---

## Task 2: 修复飞书文件发送

### 2.1 确认 _send_file_to_feishu 完整实现

```bash
grep -n "def _send_file_to_feishu" scripts/feishu_sdk_client.py
```

如果函数不存在或不完整，完整实现。关键是获取 tenant_access_token。

先找到当前代码中已有的 token 获取方式：
```bash
grep -n "tenant_access_token\|get_token\|app_id.*app_secret\|def.*token" scripts/feishu_sdk_client.py | head -20
```

基于已有方式实现：

```python
def _send_file_to_feishu(target_id: str, file_path, id_type: str = "open_id"):
    """上传文件到飞书并发送"""
    from pathlib import Path
    import requests, json as _json
    
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"[File] 不存在: {file_path}")
        return False
    
    try:
        # 获取 token - 用当前项目中已有的方式
        # 方式1: 如果有 lark SDK client
        # 方式2: 如果有全局 token 变量
        # 方式3: 手动请求
        token = None
        
        # 尝试从已有的 SDK 获取
        try:
            # 检查是否有全局 client 或 token
            import os
            app_id = os.environ.get("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
            app_secret = os.environ.get("FEISHU_APP_SECRET", "")
            
            if not app_secret:
                # 从 .env 读取
                from dotenv import dotenv_values
                env = dotenv_values(Path(__file__).parent.parent / ".env")
                app_secret = env.get("FEISHU_APP_SECRET", "")
            
            if app_id and app_secret:
                resp = requests.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret}
                )
                if resp.status_code == 200 and resp.json().get("code") == 0:
                    token = resp.json().get("tenant_access_token")
        except Exception as e:
            print(f"[File] Token 获取异常: {e}")
        
        if not token:
            print("[File] 无法获取 tenant_access_token")
            return False
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Step 1: 上传文件
        with open(file_path, 'rb') as f:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/files",
                headers=headers,
                data={"file_type": "stream", "file_name": file_path.name},
                files={"file": (file_path.name, f)}
            )
        
        result = resp.json()
        if result.get("code") != 0:
            print(f"[File] 上传失败: {result}")
            return False
        
        file_key = result["data"]["file_key"]
        print(f"[File] 上传成功: {file_key}")
        
        # Step 2: 发送文件消息
        resp2 = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "receive_id": target_id,
                "msg_type": "file",
                "content": _json.dumps({"file_key": file_key})
            }
        )
        
        result2 = resp2.json()
        if result2.get("code") == 0:
            print(f"[File] 发送成功: {file_path.name}")
            return True
        else:
            print(f"[File] 发送失败: {result2}")
            return False
            
    except Exception as e:
        print(f"[File] 异常: {e}")
        import traceback
        traceback.print_exc()
        return False
```

### 2.2 确认 _export_to_excel 函数存在且完整

```bash
grep -n "def _export_to_excel" scripts/feishu_sdk_client.py
```

如果不存在，添加完整实现（含格式化、颜色、冻结表头等——上一轮给过完整代码）。

确认 openpyxl 已安装：
```bash
pip install openpyxl --break-system-packages
python -c "import openpyxl; print('OK')"
```

---

## Task 3: 修复研发任务结果发送逻辑

找到 feishu_sdk_client.py 中研发任务完成后发送结果的代码。整个发送链路重写为：

```bash
grep -n "R&D.*Done\|synthesis_output\|LangGraph.*完成\|研发.*结果\|task.*result" scripts/feishu_sdk_client.py | head -20
```

替换为以下逻辑（确保这是唯一的结果发送路径，不要有多个地方发结果）：

```python
def _send_rd_result(synthesis_output: str, task_id: str, task_goal: str, 
                     reply_target: str, reply_type: str):
    """发送研发任务结果：优先 Excel，降级树形文本，绝不发原始 JSON"""
    import re, json as _json
    
    # Step 1: 尝试检测 JSON 并导出 Excel
    json_match = re.search(r'\[[\s\S]*\]', synthesis_output)
    
    if json_match:
        try:
            items = _json.loads(json_match.group())
            if isinstance(items, list) and len(items) > 0:
                print(f"[RD Result] 检测到 JSON: {len(items)} 条")
                
                # 导出 Excel
                xlsx_path = _export_to_excel(items, task_id, task_goal)
                print(f"[RD Result] Excel 生成: {xlsx_path}")
                
                # 发送 Excel 文件到飞书
                file_sent = _send_file_to_feishu(reply_target, xlsx_path, reply_type)
                
                if file_sent:
                    # 发送树形摘要作为预览
                    summary = _format_items_as_tree(items)
                    send_reply(reply_target, 
                        f"📊 功能PRD清单已生成（{len(items)} 条功能），Excel 文件已发送。\n\n"
                        f"预览：\n{summary[:3000]}", 
                        reply_type)
                else:
                    # 文件发送失败，发树形文本
                    summary = _format_items_as_tree(items)
                    send_reply(reply_target,
                        f"📋 功能PRD清单（{len(items)} 条功能）：\n\n{summary[:4000]}\n\n"
                        f"⚠️ Excel 文件发送失败，已保存在服务器。",
                        reply_type)
                
                return
        except Exception as e:
            print(f"[RD Result] JSON/Excel 处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    # Step 2: 非 JSON 内容，过滤掉 Agent 原始标记后发送
    clean = synthesis_output
    
    # 去掉 "=== CTO/CMO/CDO xxx ===" 标记
    clean = re.sub(r'===\s*(CTO|CMO|CDO)\s*[^=]*===', '', clean)
    # 去掉 "=== 汇聚状态 ===" 
    clean = re.sub(r'===\s*汇聚[^=]*===', '', clean)
    clean = clean.strip()
    
    # 兜底：永远不发空内容
    if len(clean) < 100:
        clean = synthesis_output  # 不清理了，发原始内容
    
    send_reply(reply_target, clean[:4000], reply_type)


def _format_items_as_tree(items: list) -> str:
    """将功能清单格式化为树形文本摘要"""
    lines = []
    for item in items:
        level = item.get("level", "")
        name = item.get("name", "")
        priority = item.get("priority", "")
        module = item.get("module", "")
        
        if level == "L1":
            lines.append(f"\n▎ {module} / {name} [{priority}]")
        elif level == "L2":
            lines.append(f"  ├ {name} [{priority}]")
        elif level == "L3":
            lines.append(f"  │  └ {name} [{priority}]")
    
    return "\n".join(lines)
```

然后找到原来发送研发结果的所有地方，全部替换为调用 `_send_rd_result`：

```python
    # 原来可能是：
    # send_reply(reply_target, synthesis_output[:4000], reply_type)
    
    # 改为：
    _send_rd_result(synthesis_output, task_id, task_goal, reply_target, reply_type)
```

---

## Task 4: 强化 Agent Prompt — 必须按用户框架输出

### 4.1 修改 CTO/CMO/CDO 的 prompt

在 src/config/agent_prompts.yaml 中，给 cto、cmo、cdo 三个角色的 prompt 都追加一段：

```yaml
# 在每个角色的 prompt 末尾追加
output_rules: |
  ## 输出规则（必须遵守）
  1. 如果用户在任务描述中给出了具体的功能框架、模块结构或一级功能列表，你必须以用户的框架为骨架展开
  2. 不能重新归类——用户说"导航"是一级功能，你就按一级功能展开，不能把它降到二级
  3. 不能删除——用户列了"社区/商城/开机动画/氛围灯"，哪怕你觉得 V1 不需要，也要保留并标注优先级
  4. 可以补充，但标注 [补充]
  5. 每个一级功能下至少展开 3 个二级功能
  6. 如果用户要求"清单/表格"格式，直接输出结构化内容（功能名、优先级、描述、验收标准），不要写长篇分析
```

### 4.2 修改后更新哈希

```bash
python -c "
import hashlib, json
from pathlib import Path
root = Path('.')
hashes = {}
for f in (root / '.ai-architecture').glob('*.md'):
    hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
for f in (root / 'src' / 'config').glob('*.yaml'):
    hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
(root / '.ai-state' / 'snapshot_hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
print(f'已更新 {len(hashes)} 个哈希')
"
```

---

## Task 5: 将用户的完整功能框架导入知识库

把用户的标准需求模板存入知识库，这样以后任何 PRD 类任务都会优先读到：

```python
python << 'PYEOF'
import sys; sys.path.insert(0, '.')
from src.tools.knowledge_base import add_knowledge

content = """
## 头盔 HUD 一级功能（共 16 个，每个必须作为 L1 展开）
1. 导航
2. 来电
3. 音乐
4. 消息
5. AI 语音助手
6. 简易路线
7. 主动安全预警提示
8. 组队
9. 摄像状态
10. 胎温胎压
11. 开机动画
12. 速度
13. 设备状态（电量、故障）
14. 显示队友位置
15. 实体按键交互
16. 氛围灯交互

## App 一级 Tab 结构
- 设备 Tab：头盔/手机互联、骑行轨迹、设备状况、行车记录、高光时刻、分享、第三方设备绑定（胎压计/车/相机）、AI 剪片
- 社区 Tab：内容浏览、互动、用户主页、发布
- 商城 Tab：商品浏览、下单支付、售后服务
- 我的 Tab：账号、设置、帮助、关于、隐私

## AI 功能
- 语音交互：核心导航场景
- 视觉交互：ADAS、追踪
- 其他多模态交互：陀螺仪、心率监测等

## 非功能类需求
- 首次使用引导（新手教程、权限申请、HUD 校准）
- 身份认证（注册、登录、游客模式）
- 设备互联（蓝牙配对、Wi-Fi 传输、第三方设备绑定）
- 产品介绍（品牌故事、功能说明、使用指南）

## PRD 输出格式标准
表格列：功能ID(如HUD-NAV-001)、模块、层级(L1/L2/L3)、父功能、功能名称、优先级(P0-P3)、交互方式(HUD/语音/按键/App/灯光)、功能描述、验收标准(可测试含数字)、关联功能、备注
"""

add_knowledge(
    title="[内部PRD] 智能骑行头盔 V1 软件功能框架与 PRD 输出标准（用户定义）",
    domain="components",
    content=content,
    tags=["internal", "prd", "product_definition", "anchor", "software_framework", "output_standard"],
    source="user_defined",
    confidence="authoritative"
)
print("✅ 功能框架 + 输出标准已导入知识库（最高权重）")
PYEOF
```

---

## 验证

```bash
# 1. 确认函数存在
python -c "
from scripts.feishu_sdk_client import _send_file_to_feishu, _export_to_excel, _send_rd_result, _format_items_as_tree
print('所有函数存在')
"

# 2. 测试 Excel 导出
python -c "
from scripts.feishu_sdk_client import _export_to_excel
items = [
    {'module': 'HUD', 'level': 'L1', 'parent': '', 'name': '导航', 'priority': 'P0', 'interaction': 'HUD/语音', 'description': '测试', 'acceptance': '成功率≥95%', 'dependencies': '', 'note': ''},
    {'module': 'HUD', 'level': 'L2', 'parent': '导航', 'name': '转向箭头', 'priority': 'P0', 'interaction': 'HUD', 'description': '显示转向', 'acceptance': '200m前显示', 'dependencies': '导航', 'note': ''},
]
path = _export_to_excel(items, 'test')
from pathlib import Path
p = Path(path)
print(f'Excel: {p.exists()}, size={p.stat().st_size}')
p.unlink(missing_ok=True)
print('OK')
"

# 3. 测试树形摘要
python -c "
from scripts.feishu_sdk_client import _format_items_as_tree
items = [
    {'module': 'HUD', 'level': 'L1', 'name': '导航', 'priority': 'P0'},
    {'module': 'HUD', 'level': 'L2', 'name': '转向箭头', 'priority': 'P0'},
    {'module': 'HUD', 'level': 'L3', 'name': '箭头显示时机', 'priority': 'P0'},
]
print(_format_items_as_tree(items))
print('OK')
"

# 4. 确认哈希已更新
python -c "
import json
from pathlib import Path
h = json.loads(Path('.ai-state/snapshot_hashes.json').read_text(encoding='utf-8'))
print(f'哈希文件: {len(h)} 个')
print('OK')
"

# 5. 重启服务后测试
# 在飞书群聊发送完整的 PRD 需求，检查：
# a. 收到 Excel 文件（直接在对话中下载）
# b. 收到树形摘要预览
# c. Excel 中有 L1/L2/L3 层级
# d. 按用户的 16 个 HUD 一级功能组织
# e. 验收标准有具体数字
```
