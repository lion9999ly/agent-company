#!/usr/bin/env python3
"""
@description: Selenium 截图采集工具 - 用于采集UI/UX截图、产品界面、APP截图
@dependencies: selenium, webdriver-manager, PIL
@last_modified: 2026-03-16

安装依赖:
    pip install selenium webdriver-manager pillow

使用方法:
    python scripts/selenium_screenshot.py --url "https://example.com" --output "screenshot.png"
    python scripts/selenium_screenshot.py --batch screenshot_tasks.json
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    print("WARNING: selenium not installed. Run: pip install selenium webdriver-manager")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ==========================================
# 配置
# ==========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / ".ai-state" / "competitive_analysis" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# 默认等待时间
DEFAULT_WAIT_SECONDS = 5
DEFAULT_TIMEOUT = 30


# ==========================================
# 数据结构
# ==========================================
@dataclass
class ScreenshotTask:
    """截图任务"""
    name: str           # 任务名称
    url: str            # 目标URL
    output: str         # 输出文件名
    wait_seconds: int = DEFAULT_WAIT_SECONDS
    full_page: bool = False  # 是否截取整页
    selector: Optional[str] = None  # 特定元素选择器
    description: str = ""


@dataclass
class ScreenshotResult:
    """截图结果"""
    task_name: str
    success: bool
    output_path: str
    error_message: Optional[str] = None
    timestamp: str = ""
    file_size_bytes: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ==========================================
# 核心类
# ==========================================
class SeleniumScreenshot:
    """Selenium 截图采集器"""

    def __init__(self, headless: bool = True, window_size: Tuple[int, int] = (1920, 1080)):
        if not HAS_SELENIUM:
            raise ImportError("selenium not installed")

        self.headless = headless
        self.window_size = window_size
        self.driver = None

    def _init_driver(self):
        """初始化 WebDriver"""
        options = ChromeOptions()

        if self.headless:
            options.add_argument("--headless")

        options.add_argument("--disable-gpu")
        options.add_argument(f"--window-size={self.window_size[0]},{self.window_size[1]}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(DEFAULT_TIMEOUT)

    def close(self):
        """关闭 WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def capture_full_page(self, url: str, output_path: str, wait_seconds: int = DEFAULT_WAIT_SECONDS) -> bool:
        """
        截取整个页面（包括滚动区域）

        Args:
            url: 目标URL
            output_path: 输出文件路径
            wait_seconds: 等待页面加载的秒数

        Returns:
            bool: 是否成功
        """
        if not self.driver:
            self._init_driver()

        try:
            self.driver.get(url)
            time.sleep(wait_seconds)

            # 获取页面总高度
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            total_width = self.driver.execute_script("return document.body.scrollWidth")

            # 设置窗口大小以容纳整个页面
            self.driver.set_window_size(total_width, total_height)

            # 截图
            self.driver.save_screenshot(output_path)

            return Path(output_path).exists()

        except Exception as e:
            print(f"全页截图失败: {e}")
            return False

    def capture_viewport(self, url: str, output_path: str, wait_seconds: int = DEFAULT_WAIT_SECONDS) -> bool:
        """
        截取当前视口

        Args:
            url: 目标URL
            output_path: 输出文件路径
            wait_seconds: 等待页面加载的秒数

        Returns:
            bool: 是否成功
        """
        if not self.driver:
            self._init_driver()

        try:
            self.driver.get(url)
            time.sleep(wait_seconds)
            self.driver.save_screenshot(output_path)

            return Path(output_path).exists()

        except Exception as e:
            print(f"视口截图失败: {e}")
            return False

    def capture_element(self, url: str, selector: str, output_path: str, wait_seconds: int = DEFAULT_WAIT_SECONDS) -> bool:
        """
        截取特定元素

        Args:
            url: 目标URL
            selector: CSS选择器
            output_path: 输出文件路径
            wait_seconds: 等待页面加载的秒数

        Returns:
            bool: 是否成功
        """
        if not self.driver:
            self._init_driver()

        try:
            self.driver.get(url)
            time.sleep(wait_seconds)

            # 等待元素出现
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )

            # 截取元素
            element.screenshot(output_path)

            return Path(output_path).exists()

        except TimeoutException:
            print(f"元素未找到: {selector}")
            return False
        except Exception as e:
            print(f"元素截图失败: {e}")
            return False

    def execute_task(self, task: ScreenshotTask) -> ScreenshotResult:
        """
        执行截图任务

        Args:
            task: 截图任务

        Returns:
            ScreenshotResult: 截图结果
        """
        output_path = str(SCREENSHOT_DIR / task.output)

        if task.selector:
            success = self.capture_element(task.url, task.selector, output_path, task.wait_seconds)
        elif task.full_page:
            success = self.capture_full_page(task.url, output_path, task.wait_seconds)
        else:
            success = self.capture_viewport(task.url, output_path, task.wait_seconds)

        file_size = Path(output_path).stat().st_bytes if success else 0

        return ScreenshotResult(
            task_name=task.name,
            success=success,
            output_path=output_path if success else "",
            error_message=None if success else "截图失败",
            file_size_bytes=file_size
        )

    def execute_batch(self, tasks: List[ScreenshotTask]) -> List[ScreenshotResult]:
        """
        批量执行截图任务

        Args:
            tasks: 截图任务列表

        Returns:
            List[ScreenshotResult]: 截图结果列表
        """
        results = []

        try:
            for task in tasks:
                print(f"正在处理: {task.name}...")
                result = self.execute_task(task)
                results.append(result)

                status = "✓" if result.success else "✗"
                print(f"  {status} {task.name}: {'成功' if result.success else result.error_message}")

        finally:
            self.close()

        return results


# ==========================================
# 预定义任务模板
# ==========================================
COMPETITIVE_ANALYSIS_TASKS = [
    # INMO Air3 相关截图
    ScreenshotTask(
        name="INMO官网首页",
        url="https://www.inmoxr.com",
        output="inmo_homepage.png",
        description="INMO官网首页截图"
    ),
    ScreenshotTask(
        name="INMO Air3产品页",
        url="https://www.inmoxr.com/product/air3",
        output="inmo_air3_product.png",
        full_page=True,
        description="INMO Air3产品详情页"
    ),

    # Meta Ray-Ban Display 相关截图
    ScreenshotTask(
        name="Ray-Ban Meta Display产品页",
        url="https://www.ray-ban.com/usa/l/discover-meta-ray-ban-display",
        output="rayban_meta_display.png",
        full_page=True,
        description="Ray-Ban官网Meta Display产品页"
    ),
    ScreenshotTask(
        name="Meta智能眼镜页面",
        url="https://www.meta.com/smart-glasses/",
        output="meta_smart_glasses.png",
        description="Meta官网智能眼镜页面"
    ),
]


# ==========================================
# 命令行接口
# ==========================================
def main():
    """主入口"""
    parser = argparse.ArgumentParser(description="Selenium 截图采集工具")
    parser.add_argument("--url", help="目标URL")
    parser.add_argument("--output", help="输出文件名")
    parser.add_argument("--full-page", action="store_true", help="截取整页")
    parser.add_argument("--selector", help="CSS选择器，截取特定元素")
    parser.add_argument("--wait", type=int, default=DEFAULT_WAIT_SECONDS, help="等待秒数")
    parser.add_argument("--batch", help="批量任务JSON文件")
    parser.add_argument("--template", action="store_true", help="使用预定义竞品分析任务模板")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（调试用）")

    args = parser.parse_args()

    if not HAS_SELENIUM:
        print("ERROR: selenium not installed. Run: pip install selenium webdriver-manager")
        sys.exit(1)

    screenshotter = SeleniumScreenshot(headless=not args.headed)

    if args.template:
        # 使用预定义模板
        print("执行预定义竞品分析截图任务...")
        results = screenshotter.execute_batch(COMPETITIVE_ANALYSIS_TASKS)

        # 保存结果报告
        report_path = SCREENSHOT_DIR / "screenshot_report.json"
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tasks": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "results": [asdict(r) for r in results]
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n结果报告已保存: {report_path}")

    elif args.batch:
        # 从JSON文件读取批量任务
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"ERROR: Batch file not found: {batch_file}")
            sys.exit(1)

        tasks_data = json.loads(batch_file.read_text(encoding="utf-8"))
        tasks = [ScreenshotTask(**t) for t in tasks_data]

        results = screenshotter.execute_batch(tasks)
        print(f"\n完成: {sum(1 for r in results if r.success)}/{len(results)} 成功")

    elif args.url and args.output:
        # 单个任务
        task = ScreenshotTask(
            name=args.output,
            url=args.url,
            output=args.output,
            wait_seconds=args.wait,
            full_page=args.full_page,
            selector=args.selector
        )

        result = screenshotter.execute_task(task)

        if result.success:
            print(f"截图成功: {result.output_path}")
        else:
            print(f"截图失败: {result.error_message}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()