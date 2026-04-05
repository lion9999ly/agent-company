"""Claude 思考通道 — 通过 Playwright 操作 claude.ai 对话

支持三种连接模式（按优先级排序）：
1. CDP 模式（推荐）- 连接到已运行的 Chrome（需要 --remote-debugging-port）
2. Profile 模式 - 使用 Chrome profile（需要先关闭 Chrome）
3. Fallback 模式 - 使用 Edge 独立 profile（需要手动登录）

CDP 模式启动方法：
  powershell -File scripts/chrome_cdp_restart.ps1

三方记忆共享：
  - founder_mindset.md: 创始人心智模型
  - product_anchor.md: 产品锚点
  - thinking_history.jsonl: 思考历史（含纠正记录）
"""
import time
import json
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 思考通道的对话 URL
THINKING_CHANNEL_URL = "https://claude.ai/chat/06d4bcbe-f474-4de9-9f88-ed187c0c687c"

# CDP 端口（默认）
CDP_PORT = 9333

# Chrome 用户数据目录
CHROME_USER_DATA = str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")


def _build_thinking_context() -> str:
    """构建思考上下文——让思考通道的 Claude 有完整记忆

    三个来源：
    1. founder_mindset.md: 创始人心智模型
    2. product_anchor.md: 产品锚点
    3. thinking_history.jsonl: 最近的思考历史（含纠正）
    """
    context_parts = []

    # 1. 创始人心智模型
    mindset_path = PROJECT_ROOT / ".ai-state" / "founder_mindset.md"
    if mindset_path.exists():
        content = mindset_path.read_text(encoding='utf-8')[:3000]
        if content.strip():
            context_parts.append(f"## 创始人心智模型\n{content}")

    # 2. 产品锚点
    anchor_path = PROJECT_ROOT / ".ai-state" / "product_anchor.md"
    if anchor_path.exists():
        content = anchor_path.read_text(encoding='utf-8')[:2000]
        if content.strip():
            context_parts.append(f"## 产品锚点\n{content}")

    # 3. 最近的思考历史（最近 10 条）
    history_path = PROJECT_ROOT / ".ai-state" / "thinking_history.jsonl"
    if history_path.exists():
        lines = history_path.read_text(encoding='utf-8').strip().split('\n')
        recent = lines[-10:] if len(lines) > 10 else lines
        history_entries = []
        for line in recent:
            try:
                entry = json.loads(line)
                q = entry.get('question', '')[:100]
                r = entry.get('response', '')[:200]
                correction = entry.get('correction', '')
                if correction:
                    history_entries.append(f"Q: {q}\nA: {r}\n[Leo 纠正]: {correction}")
                else:
                    history_entries.append(f"Q: {q}\nA: {r}")
            except:
                pass
        if history_entries:
            context_parts.append("## 最近的思考记录\n" + "\n---\n".join(history_entries))

    return "\n\n".join(context_parts)


def record_correction(request_id: str, correction: str) -> bool:
    """记录纠正到思考历史

    Args:
        request_id: 请求 ID（如 think_1775383863）
        correction: 纠正内容

    Returns:
        是否成功
    """
    history_path = PROJECT_ROOT / ".ai-state" / "thinking_history.jsonl"
    if not history_path.exists():
        return False

    lines = history_path.read_text(encoding='utf-8').strip().split('\n')
    updated = False
    new_lines = []

    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get('id') == request_id:
                entry['correction'] = correction
                entry['corrected_at'] = time.strftime('%Y-%m-%d %H:%M')
                updated = True
            new_lines.append(json.dumps(entry, ensure_ascii=False))
        except:
            new_lines.append(line)

    if updated:
        history_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        print(f"[Bridge] 已记录纠正: {request_id}")
        return True

    return False


def update_founder_mindset(update_text: str) -> bool:
    """更新创始人心智模型

    Args:
        update_text: 要追加的更新内容

    Returns:
        是否成功
    """
    mindset_path = PROJECT_ROOT / ".ai-state" / "founder_mindset.md"

    timestamp = time.strftime('%Y-%m-%d %H:%M')
    update_block = f"\n\n## 对齐更新 ({timestamp})\n{update_text}\n"

    try:
        with open(mindset_path, 'a', encoding='utf-8') as f:
            f.write(update_block)
        print(f"[Bridge] 已更新创始人心智模型")
        return True
    except Exception as e:
        print(f"[Bridge] 更新失败: {e}")
        return False


def call_claude_via_cdp(prompt: str, timeout: int = 180, port: int = CDP_PORT,
                        inject_context: bool = True) -> str:
    """通过 CDP 连接到已运行的 Chrome（推荐模式）

    优点：绕过 Cloudflare，复用已登录状态
    前置：Chrome 需要以 --remote-debugging-port 启动

    启动方法：
      powershell -ExecutionPolicy Bypass -File scripts/chrome_cdp_restart.ps1

    或手动：
      1. 关闭所有 Chrome
      2. 启动: chrome.exe --remote-debugging-port=9333 --user-data-dir=%TEMP%\chrome-cdp-debug
      3. 登录 claude.ai 并打开思考通道

    Args:
        prompt: 要发送的问题
        timeout: 超时时间（秒）
        port: CDP 端口
        inject_context: 是否注入上下文（默认 True）
    """
    result = ""

    # 构建完整 prompt（注入上下文）
    if inject_context:
        context = _build_thinking_context()
        if context:
            full_prompt = f"[系统上下文 — 请基于以下信息回答]\n\n{context}\n\n---\n\n[当前问题]\n{prompt}"
        else:
            full_prompt = prompt
    else:
        full_prompt = prompt

    with sync_playwright() as p:
        try:
            # 连接到已运行的 Chrome
            browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
            print(f"[Bridge-CDP] 已连接到 Chrome (端口 {port})")

            context = browser.contexts[0]
            pages = context.pages
            print(f"[Bridge-CDP] 已打开的页面数: {len(pages)}")

            # 找到思考通道页面
            target_page = None
            for page in pages:
                if '06d4bcbe' in page.url:
                    target_page = page
                    print(f"[Bridge-CDP] 找到思考通道: {page.url}")
                    break

            if not target_page:
                print("[Bridge-CDP] 未找到思考通道页面")
                print(f"[Bridge-CDP] 请在 Chrome 中打开: {THINKING_CHANNEL_URL}")
                return ""

            # 找输入框
            input_selectors = [
                'div[contenteditable="true"]',
                'div[data-testid="composer-input"]',
                'div[role="textbox"]',
                'textarea',
            ]

            input_el = None
            for selector in input_selectors:
                try:
                    input_el = target_page.wait_for_selector(selector, timeout=5000)
                    if input_el:
                        print(f"[Bridge-CDP] 找到输入框: {selector}")
                        break
                except:
                    continue

            if not input_el:
                print("[Bridge-CDP] 找不到输入框，可能页面未完全加载")
                return ""

            # 输入 full_prompt（包含上下文）
            input_el.click()
            time.sleep(0.3)
            target_page.keyboard.type(full_prompt, delay=10)
            time.sleep(0.5)

            # 发送（按 Enter）
            target_page.keyboard.press("Enter")
            print("[Bridge-CDP] 已发送消息，等待回复...")

            # 等待回复开始（检测 Stop 按钮出现）
            time.sleep(3)
            max_wait = timeout
            waited = 0
            reply_started = False

            # 先等待回复开始（Stop 按钮出现）
            while waited < 30 and not reply_started:
                stop_btn = target_page.query_selector('button[aria-label="Stop"]')
                if stop_btn:
                    reply_started = True
                    print("[Bridge-CDP] 回复已开始生成...")
                    break
                time.sleep(1)
                waited += 1

            # 然后等待回复完成（Stop 按钮消失）
            if reply_started:
                waited = 0
                while waited < max_wait:
                    stop_btn = target_page.query_selector('button[aria-label="Stop"]')
                    if stop_btn:
                        if waited % 10 == 0:
                            print(f"[Bridge-CDP] 回复中... ({waited}s)")
                        time.sleep(2)
                        waited += 2
                        continue
                    time.sleep(3)
                    # 再次确认 Stop 按钮消失
                    stop_btn = target_page.query_selector('button[aria-label="Stop"]')
                    if not stop_btn:
                        print(f"[Bridge-CDP] 回复完成 ({waited}s)")
                        break
                    waited += 3
            else:
                print("[Bridge-CDP] 回复未开始，可能网络问题或消息已存在")

            # 获取 Claude 的回复（使用 JavaScript 直接获取）
            # claude.ai 回复在 .font-claude-response 类中
            time.sleep(3)  # 等待 DOM 更新

            # 用 JS 获取最新的助手回复
            js_code = """
            () => {
                // font-claude-response 是 Claude 回复的类名
                const claudeResponses = document.querySelectorAll('.font-claude-response');
                const results = [];
                for (const r of claudeResponses) {
                    const text = r.innerText.trim();
                    if (text.length > 0 && text.length < 500) {
                        results.push(text);
                    }
                }

                // 返回倒数第二个（最后一个是项目名称）
                if (results.length >= 2) {
                    return results[results.length - 2];
                } else if (results.length === 1) {
                    return results[0];
                }
                return '';
            }
            """
            result = target_page.evaluate(js_code)

            if result:
                print(f"[Bridge-CDP] 收到回复: {len(result)} 字符")

                # 保存到思考历史
                request_id = f"think_{int(time.time())}"
                history_path = PROJECT_ROOT / ".ai-state" / "thinking_history.jsonl"
                try:
                    history_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(history_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "id": request_id,
                            "question": prompt[:200],
                            "response": result[:1000],
                            "source": "cdp_bridge",
                            "timestamp": time.strftime('%Y-%m-%d %H:%M')
                        }, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"[Bridge-CDP] 保存历史失败: {e}")
            else:
                print("[Bridge-CDP] 未找到回复内容")

            # 注意：不关闭 browser，只断开连接
            # browser.close() 会关闭整个 Chrome

        except Exception as e:
            print(f"[Bridge-CDP] 错误: {e}")

    return result


def check_cdp_available(port: int = CDP_PORT) -> bool:
    """检查 CDP 端口是否可用"""
    try:
        import urllib.request
        urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2)
        return True
    except:
        return False


def call_claude_thinking(prompt: str, timeout: int = 180) -> str:
    """向 Claude 思考通道发消息（自动选择最佳模式）

    优先级：
    1. CDP 模式（如果端口可用）
    2. Profile 模式（如果 Chrome 未运行）
    3. Fallback 模式（兜底）
    """
    # 优先尝试 CDP
    if check_cdp_available():
        print("[Bridge] 使用 CDP 模式")
        return call_claude_via_cdp(prompt, timeout)

    # 检查 Chrome 是否运行
    chrome_running = subprocess.run(
        ['powershell', '-Command', 'Get-Process chrome -ErrorAction SilentlyContinue'],
        capture_output=True, text=True
    ).stdout.strip()

    if not chrome_running:
        print("[Bridge] Chrome 未运行，尝试 Profile 模式")
        return call_claude_with_profile(prompt, timeout)

    print("[Bridge] Chrome 运行中但 CDP 不可用，使用 Fallback 模式")
    print("[Bridge] 提示: 运行 scripts/chrome_cdp_restart.ps1 启用 CDP 模式")
    return call_claude_with_fallback(prompt, timeout)


def call_claude_with_profile(prompt: str, timeout: int = 180) -> str:
    """使用 Chrome profile（需要先关闭 Chrome）"""
    result = ""

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA,
            headless=False,
            channel="chrome",
            args=["--disable-extensions"],
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            print("[Bridge-Profile] 打开思考通道...")
            page.goto(THINKING_CHANNEL_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            print(f"[Bridge-Profile] 当前 URL: {page.url}")

            if "__cf_chl" in page.url:
                print("[Bridge-Profile] Cloudflare 挑战，等待自动完成...")
                for i in range(30):
                    time.sleep(1)
                    if "__cf_chl" not in page.url:
                        break
                time.sleep(3)

            if "login" in page.url.lower():
                print("[Bridge-Profile] 需要登录 claude.ai")
                return ""

            input_selectors = ['div[contenteditable="true"]', 'textarea']
            input_el = None
            for selector in input_selectors:
                try:
                    input_el = page.wait_for_selector(selector, timeout=5000)
                    if input_el:
                        break
                except:
                    continue

            if not input_el:
                return ""

            input_el.click()
            time.sleep(0.3)
            page.keyboard.type(prompt, delay=10)
            time.sleep(0.5)
            page.keyboard.press("Enter")
            print("[Bridge-Profile] 已发送消息...")

            time.sleep(5)
            for i in range(timeout // 2):
                stop_btn = page.query_selector('button[aria-label="Stop"]')
                if stop_btn:
                    time.sleep(2)
                    continue
                time.sleep(2)
                if not page.query_selector('button[aria-label="Stop"]'):
                    break

            messages = page.query_selector_all('[data-testid="message-content"], .prose')
            if messages:
                result = messages[-1].inner_text()

        except Exception as e:
            print(f"[Bridge-Profile] 错误: {e}")
        finally:
            context.close()

    return result


def call_claude_with_fallback(prompt: str, timeout: int = 180) -> str:
    """使用 Edge 独立 profile（兜底模式）"""
    result = ""

    with sync_playwright() as p:
        profile_dir = str(Path.home() / ".claude-bridge-profile")
        Path(profile_dir).mkdir(parents=True, exist_ok=True)

        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel="msedge",
            args=["--disable-extensions", "--disable-gpu"],
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            print("[Bridge-Fallback] 打开思考通道（Edge）...")
            page.goto(THINKING_CHANNEL_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            print(f"[Bridge-Fallback] 当前 URL: {page.url}")

            if "__cf_chl" in page.url:
                print("[Bridge-Fallback] Cloudflare 挑战，需手动验证（等待 60s）...")
                for i in range(60):
                    time.sleep(1)
                    if "__cf_chl" not in page.url:
                        break

            if "login" in page.url.lower():
                print("[Bridge-Fallback] 需要登录，等待 120s...")
                time.sleep(120)

            input_selectors = ['div[contenteditable="true"]', 'textarea']
            input_el = None
            for selector in input_selectors:
                try:
                    input_el = page.wait_for_selector(selector, timeout=5000)
                    if input_el:
                        break
                except:
                    continue

            if not input_el:
                print("[Bridge-Fallback] 找不到输入框")
                return ""

            input_el.click()
            time.sleep(0.3)
            page.keyboard.type(prompt, delay=10)
            time.sleep(0.5)
            page.keyboard.press("Enter")
            print("[Bridge-Fallback] 已发送消息...")

            time.sleep(5)
            for i in range(timeout // 2):
                stop_btn = page.query_selector('button[aria-label="Stop"]')
                if stop_btn:
                    time.sleep(2)
                    continue
                time.sleep(2)
                if not page.query_selector('button[aria-label="Stop"]'):
                    break

            messages = page.query_selector_all('[data-testid="message-content"], .prose')
            if messages:
                result = messages[-1].inner_text()

        except Exception as e:
            print(f"[Bridge-Fallback] 错误: {e}")
        finally:
            context.close()

    return result


def test_cdp():
    """测试 CDP 模式"""
    print("测试 CDP 模式...")
    if not check_cdp_available():
        print("CDP 端口不可用，请先运行: powershell -File scripts/chrome_cdp_restart.ps1")
        return False
    result = call_claude_via_cdp("你好，请回复你的模型名称，只回复名称。")
    print(f"\n回复: {result[:200] if result else '(无回复)'}")
    return bool(result)


def test_auto():
    """测试自动选择模式"""
    print("测试自动模式...")
    result = call_claude_thinking("你好，请简要说明你是什么模型。")
    print(f"\n回复: {result[:200] if result else '(无回复)'}")
    return bool(result)


if __name__ == "__main__":
    # 默认测试 CDP 模式
    test_cdp()