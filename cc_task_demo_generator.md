# CC 任务：Demo Generator 实现

## 背景
为智能骑行头盔产品生成两个演示 Demo（HUD + App），用于给供应商/投资人展示。
架构讨论已在 Claude Chat 完成，以下是确认后的完整实现方案。

## 重要原则
- 讨论已完成，直接执行，不需要重新讨论架构
- 所有产品设计决策在 JSON 配置文件里，Python 代码不硬编码任何产品逻辑
- 每步完成后测试验证，不要改完就 commit
- 如果碰到问题自己判断解决，不要中止

---

## 任务 1：创建三个 JSON 配置文件

### 文件 1：`.ai-state/demo_specs/hud_config.json`

```json
{
  "layout": {
    "LT": { "role": "速度+骑行状态", "type": "persistent" },
    "RT": { "role": "设备状态图标", "type": "persistent" },
    "RB": { "role": "导航主区", "type": "dynamic" },
    "LB": { "role": "通知/来电/音乐", "type": "dynamic" }
  },
  "page_states": {
    "riding_main": { "LT": "速度", "RT": "电量+蓝牙+信号", "RB": null, "LB": null },
    "navigation":  { "LT": "速度", "RT": "设备状态", "RB": "转向箭头+距离+ETA", "LB": "路名" },
    "incoming_call": { "LT": "速度", "RT": "设备状态", "RB": "保持导航或空", "LB": "来电者+接听/拒接" },
    "music":       { "LT": "速度", "RT": "设备状态", "RB": "保持导航或空", "LB": "曲名+播放状态" },
    "group_ride":  { "LT": "速度", "RT": "队友数+语音状态", "RB": "队友位置标记", "LB": "队伍消息" },
    "warning":     { "LT": "⚠️方向闪烁", "RT": "⚠️方向闪烁", "RB": "预警类型+距离", "LB": "预警指令" },
    "recording":   { "LT": "速度", "RT": "录制时长+存储", "RB": "保持导航或空", "LB": "REC指示" }
  },
  "priority_order": ["warning", "incoming_call", "navigation", "group_ride", "music", "recording", "riding_main"],
  "warning_direction_map": {
    "front_left": ["LT"], "front_right": ["RT"], "front": ["LT", "RT"],
    "rear_left": ["LB"], "rear_right": ["RB"], "rear": ["LB", "RB"]
  },
  "speed_tiers": {
    "S0": { "range": "0", "max_elements": 6, "label": "静止" },
    "S1": { "range": "1-30", "max_elements": 4, "label": "低速" },
    "S2": { "range": "31-80", "max_elements": 3, "label": "中速" },
    "S3": { "range": "81+", "max_elements": 2, "label": "高速" }
  },
  "colors": {
    "normal": "#00FF41", "caution": "#FFD700", "danger": "#FF0000",
    "info": "#00BFFF", "inactive": "#666666", "bg": "#000000"
  },
  "ab_compare": {
    "enabled": true,
    "path_a": { "name": "Free Form (OLED)", "color_mode": "monochrome_green", "fov_placeholder": "TBD" },
    "path_b": { "name": "衍射光波导 (MicroLED)", "color_mode": "monochrome_green", "fov_placeholder": "TBD" }
  },
  "icons": {
    "nav_left": "nav_arrow_left.png", "nav_right": "nav_arrow_right.png",
    "nav_uturn": "nav_u_turn.png", "speed": "speed_indicator.png",
    "bsd": "adas_warning_bsd.png", "fcw": "adas_warning_fcw.png",
    "call": "incoming_call.png", "group": "group_ride.png",
    "battery": "battery_indicator.png", "recording": "recording_dot.png"
  }
}
```

### 文件 2：`.ai-state/demo_specs/app_config.json`

```json
{
  "tabs": [
    { "id": "device", "label": "设备", "icon": "smartphone" },
    { "id": "community", "label": "社区", "icon": "users" },
    { "id": "shop", "label": "商城", "icon": "shopping-bag" },
    { "id": "profile", "label": "我的", "icon": "user" }
  ],
  "pages": {
    "device": {
      "dashboard": { "title": "设备首页", "components": ["connection_status", "helmet_battery", "quick_actions", "recent_rides"] },
      "navigation": { "title": "导航", "components": ["map_placeholder", "destination_input", "send_to_helmet"] },
      "adas_settings": { "title": "ADAS设置", "components": ["bsd_toggle", "fcw_toggle", "ldw_toggle", "sensitivity_slider"] },
      "group_ride": { "title": "组队骑行", "components": ["teammate_list", "map_positions", "voice_channel_status", "create_join_buttons"] },
      "dashcam": { "title": "行车记录", "components": ["recording_status", "clip_gallery", "storage_info"] },
      "hud_settings": { "title": "HUD设置", "components": ["brightness_slider", "layout_preview", "info_density"] }
    },
    "community": {
      "feed": { "title": "骑行动态", "components": ["ride_posts", "photo_cards"] },
      "routes": { "title": "路线分享", "components": ["route_list", "difficulty_tags"] }
    },
    "shop": {
      "store": { "title": "配件商城", "components": ["product_grid", "categories"] }
    },
    "profile": {
      "settings": { "title": "设置", "components": ["volume", "firmware_version", "about"] },
      "ride_history": { "title": "骑行历史", "components": ["ride_list", "stats_summary"] }
    }
  },
  "theme": {
    "primary": "#00FF41", "bg_dark": "#0A0A0A", "bg_card": "#1A1A1A",
    "text_primary": "#FFFFFF", "text_secondary": "#999999"
  }
}
```

### 文件 3：`.ai-state/demo_specs/demo_scenarios.json`

```json
{
  "hud_scenarios": [
    {
      "id": "daily_commute",
      "name": "日常通勤",
      "duration_sec": 75,
      "events": [
        { "t": 0, "action": "boot_sequence", "desc": "开机自检" },
        { "t": 5, "action": "bluetooth_connect", "desc": "蓝牙连接" },
        { "t": 10, "action": "nav_start", "dest": "公司", "desc": "导航启动" },
        { "t": 20, "action": "speed_change", "value": 45 },
        { "t": 30, "action": "nav_turn", "direction": "right", "distance": "200m" },
        { "t": 40, "action": "nav_turn", "direction": "left", "distance": "500m" },
        { "t": 55, "action": "speed_change", "value": 60 },
        { "t": 65, "action": "speed_change", "value": 0 },
        { "t": 70, "action": "nav_arrive", "desc": "到达目的地" }
      ]
    },
    {
      "id": "emergency",
      "name": "紧急场景",
      "duration_sec": 60,
      "events": [
        { "t": 0, "action": "speed_change", "value": 55 },
        { "t": 5, "action": "nav_turn", "direction": "straight", "distance": "1.2km" },
        { "t": 10, "action": "incoming_call", "caller": "老婆" },
        { "t": 15, "action": "call_accept" },
        { "t": 25, "action": "call_end" },
        { "t": 30, "action": "warning_fcw", "distance": "30m", "direction": "front" },
        { "t": 33, "action": "warning_clear" },
        { "t": 40, "action": "warning_bsd", "direction": "rear_right" },
        { "t": 43, "action": "warning_clear" },
        { "t": 50, "action": "nav_reroute", "desc": "偏航重算" }
      ]
    },
    {
      "id": "group_ride",
      "name": "组队骑行",
      "duration_sec": 70,
      "events": [
        { "t": 0, "action": "group_create", "name": "周末摩旅" },
        { "t": 5, "action": "group_join", "rider": "老张" },
        { "t": 8, "action": "group_join", "rider": "小王" },
        { "t": 12, "action": "group_voice_on" },
        { "t": 15, "action": "speed_change", "value": 70 },
        { "t": 30, "action": "nav_turn", "direction": "right", "distance": "300m" },
        { "t": 40, "action": "group_straggler", "rider": "小王", "desc": "掉队提醒" },
        { "t": 50, "action": "group_rejoin", "rider": "小王" },
        { "t": 60, "action": "speed_change", "value": 0 },
        { "t": 65, "action": "group_end" }
      ]
    }
  ]
}
```

---

## 任务 2：写 `scripts/demo_generator.py`

### 核心设计
- 单文件，约 500 行
- `DemoGenerator` 类，依赖 `ModelGateway`、`KnowledgeBase`、飞书通知
- 所有产品设计决策从 JSON 配置读取，Python 不硬编码产品逻辑
- 改设计 → 改 JSON；改生成流程 → 改 Python

### 5 步管道

```
Step 1: Smart Preflight（自愈式前置检查）
├── 检查图标素材（.ai-state/demo_assets/hud_icons/）
│   └── 缺失 → 自动 call_image(nano_banana_pro) 补生成
├── 检查 KB 相关条目（搜索 hud/app 相关）
│   └── 不足(<3条) → 自动 mini_research（3-5 query, L1+L2 only）
├── 检查模型可用性
│   └── 主力不可用 → 走降级链，全挂才中止
└── 飞书通知进度

Step 2: Spec Generation（配置驱动，不是从零设计）
├── 模型：gemini_2_5_flash
├── 输入：hud_config.json（产品设计） + KB 上下文
├── 输出：技术实现 spec（CSS 变量、动画参数、事件映射、速度分级规则）
├── 写入 .ai-state/demo_specs/hud_tech_spec.json
├── 飞书通知 "Spec已生成，如需修改回复'修改Spec'"
└── 不暂停，直接继续

Step 3: Asset Mapping
├── 解析 hud_config.json 的 icons 字段
├── 匹配 .ai-state/demo_assets/hud_icons/ 下的文件
├── 缺失 → call_image 补生成
└── 全部图标读取并转 base64 data URI

Step 4: Code Generation
├── HUD Demo：
│   ├── 模型：gpt_5_4，单次调用
│   ├── 输入：tech_spec JSON + base64 assets + demo_scenarios.json
│   ├── 要求：
│   │   - 单文件 HTML，零外部依赖，双击打开
│   │   - 全屏黑色背景模拟护目镜视角
│   │   - 四角信息区（LT/RT/LB/RB），中央完全留空
│   │   - 两种模式：自动剧本（底部时间轴）+ 手动沙盒（右侧抽屉事件面板）
│   │   - 键盘快捷键（←→↑导航、U掉头、B BSD、F FCW、C来电、R录制、G组队、+-速度）
│   │   - 预警时对应角落红色闪烁（参照 warning_direction_map）
│   │   - A/B 光学方案切换条（顶部）
│   │   - 速度变化时自动按 speed_tiers 调整信息密度
│   │   - 图标全部 base64 data URI 内嵌
│   └── 输出：demo_outputs/hud_demo.html
│
├── App Demo：
│   ├── 骨架生成（gpt_5_4，1次调用）
│   │   - 4 Tab 底部导航 + 路由
│   │   - 每个 Tab 内容区用占位符 <!-- TAB:device --> ... <!-- /TAB:device -->
│   │   - 手机尺寸模拟（375x812 居中，圆角边框）
│   │   - 主题色用 app_config.json 的 theme
│   ├── 逐 Tab 填充（gpt_5_4，4次调用）
│   │   - 每次传入单个 Tab 的 pages 定义
│   │   - 生成该 Tab 下所有页面的组件 HTML
│   │   - 用 str.replace 填入骨架占位符
│   └── 输出：demo_outputs/app_demo.html
│
├── 规则验证（代码，不调 LLM）
│   - HTML 标签闭合检查
│   - 功能点覆盖检查（page_states 的每个 key 在代码中有对应实现）
│   - 有问题 → 再调一次 gpt_5_4 修复

Step 5: Visual Review
├── 模型：gemini_2_5_flash
├── 将生成的 HTML 代码（截取关键部分）+ tech_spec 一起发给 flash
├── 问：这段代码是否正确实现了 spec 中的所有要求？列出不符合的地方
└── 审查结果 + 文件路径 → 飞书通知
```

### 模型分配

| 步骤 | 模型 | 理由 |
|------|------|------|
| Tech Spec 生成 | gemini_2_5_flash | 翻译型任务，JSON 输出稳定，速度快 |
| HUD HTML 生成 | gpt_5_4 | 核心代码生成，需要最强推理和代码能力 |
| App 骨架生成 | gpt_5_4 | 同上 |
| App 逐页填充 | gpt_5_4 | 保持和骨架代码风格一致 |
| Visual Review | gemini_2_5_flash | 轻量比对任务 |
| 缺失图标补生成 | nano_banana_pro | 已验证可用，HUD 绿色风格 |
| Mini Research | 复用 deep_research L1+L2 | 不走全管道，只搜索+提取 |

### 关键函数签名

```python
class DemoGenerator:
    def __init__(self, gw: ModelGateway, kb: KnowledgeBase, feishu):
        """gw = model_gateway 实例, kb = knowledge_base 实例, feishu = 飞书通知函数"""

    async def generate_hud_demo(self) -> str:
        """入口：生成 HUD Demo，返回文件路径"""

    async def generate_app_demo(self) -> str:
        """入口：生成 App Demo，返回文件路径"""

    async def get_status(self) -> str:
        """返回当前生成状态/最近结果"""

    async def _smart_preflight(self, demo_type: str) -> dict:
        """自愈式前置检查，返回 {icons: {name: Path}, kb_context: str}"""

    async def _mini_research(self, demo_type: str) -> None:
        """快速补充知识，3-5 query，L1+L2 only"""

    async def _generate_tech_spec(self, demo_type: str) -> dict:
        """gemini_flash 将产品配置翻译为技术实现 spec"""

    async def _map_and_encode_assets(self, config: dict) -> dict:
        """图标匹配 + 缺失补生成 + base64 编码"""

    async def _generate_hud_html(self, tech_spec: dict, b64_assets: dict) -> str:
        """gpt_5_4 单次生成完整 HUD HTML"""

    async def _generate_app_html(self, tech_spec: dict) -> str:
        """gpt_5_4 骨架 + 逐页填充"""

    async def _generate_app_skeleton(self, tech_spec: dict) -> str:
        """生成 App 骨架 HTML（4 Tab + 占位符）"""

    async def _fill_tab(self, tech_spec: dict, tab: dict, pages: dict) -> str:
        """填充单个 Tab 的页面内容"""

    async def _visual_review(self, html_path: str, tech_spec: dict) -> dict:
        """gemini_flash 审查代码是否符合 spec"""

    def _validate_html(self, html: str, spec: dict) -> list[str]:
        """规则验证：标签闭合 + 功能点覆盖"""

    async def _fix_issues(self, html: str, issues: list[str]) -> str:
        """调 gpt_5_4 修复验证发现的问题"""

    async def _notify(self, msg: str):
        """飞书通知"""
```

### 注意事项
- `_load_configs()` 在每次生成开始时调用，这样运行中改了 JSON 下次生成自动生效
- base64 图标拼接到 prompt 时注意总长度，如果超过模型上下文限制，只传 HUD 实际用到的图标（约 10 个）
- HUD HTML 的自动剧本模式用 `setInterval` + 事件队列驱动，时间轴用 `<input type="range">`
- App HTML 用 `hashchange` 做路由，不引入任何框架（不用 React，纯 vanilla JS）
- 生成失败时降级策略：gpt_5_4 → gpt_4o_norway，gemini_flash 失败 → 跳过该步继续

---

## 任务 3：飞书路由注册

在 `scripts/feishu_handlers/text_handler.py` 中新增路由匹配：

```python
# 在现有路由逻辑中添加：
demo_commands = {
    "生成hud demo": "hud",
    "生成huddemo": "hud",
    "生成app demo": "app",
    "生成appdemo": "app",
}
status_commands = ["demo状态", "demo status"]

text_lower = text.strip().lower()

# Demo 生成
for cmd, demo_type in demo_commands.items():
    if cmd in text_lower:
        # 异步执行，不阻塞飞书响应
        if demo_type == "hud":
            asyncio.create_task(demo_generator.generate_hud_demo())
        else:
            asyncio.create_task(demo_generator.generate_app_demo())
        return "🚀 Demo 生成已启动，会在飞书实时通知进度"

# Demo 状态查询
for cmd in status_commands:
    if cmd in text_lower:
        return await demo_generator.get_status()
```

DemoGenerator 实例在服务启动时创建，和其他 handler 共享 gw/kb/feishu 实例。

---

## 任务 4：测试验证

完成代码后，按以下顺序测试：

1. **单元测试**：`_load_configs()` 能正确读取三个 JSON
2. **集成测试**：在 Python 中直接调用 `generate_hud_demo()`，不经飞书
3. **端到端测试**：飞书发送 "生成HUD Demo"，确认：
   - 飞书收到进度通知（前置检查 → Spec生成 → 代码生成 → 完成）
   - `demo_outputs/hud_demo.html` 文件存在
   - 双击打开 HTML，四角布局正确显示
   - 键盘事件响应正常
   - 自动剧本可播放
   - A/B 切换可用
4. **App Demo 测试**：飞书发送 "生成App Demo"，确认类似
5. **异常测试**：删掉一个图标文件，再次生成，确认自动补生成

测试全部通过后再 git commit。

---

## 文件输出结构

```
.ai-state/demo_specs/
├── hud_config.json          # 产品设计配置（人工维护）
├── app_config.json          # 产品设计配置（人工维护）
├── demo_scenarios.json      # 自动剧本脚本（人工维护）
├── hud_tech_spec.json       # LLM 生成的技术 spec（自动生成）
└── app_tech_spec.json       # LLM 生成的技术 spec（自动生成）

demo_outputs/
├── hud_demo.html            # 双击打开即可演示
└── app_demo.html            # 双击打开即可演示

scripts/
└── demo_generator.py        # 生成器代码
```
