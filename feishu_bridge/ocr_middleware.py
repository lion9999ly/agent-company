"""
@description: OCR预处理中间件，基于PaddleOCR实现中英文混合识别
@dependencies: paddleocr, PIL
@last_modified: 2026-03-18
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class OCRResult:
    """OCR识别结果标准化数据结构"""
    success: bool
    text: str
    raw_text: str
    error_message: Optional[str] = None


class OCRMiddleware:
    """
    OCR预处理中间件

    基于PaddleOCR实现中英文混合识别，提供标准化的输入输出接口。
    """

    # 标准化提示文本
    MSG_NO_VALID_TEXT = "[OCR] 未识别到有效文字内容"
    MSG_FILE_NOT_FOUND = "[OCR] 图片文件不存在: {path}"
    MSG_INVALID_FORMAT = "[OCR] 不支持的图片格式: {ext}"
    MSG_RECOGNITION_FAILED = "[OCR] 识别失败: {error}"

    # 支持的图片格式
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

    def __init__(self, use_gpu: bool = False, lang: str = 'ch'):
        """
        初始化OCR引擎

        Args:
            use_gpu: 是否使用GPU加速，默认False
            lang: 识别语言，'ch'表示中英文混合，'en'表示英文
        """
        self._ocr = None
        self._use_gpu = use_gpu
        self._lang = lang
        self._initialized = False

    def _init_ocr(self) -> bool:
        """延迟初始化OCR引擎"""
        if self._initialized:
            return self._ocr is not None

        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._lang,
                use_gpu=self._use_gpu,
                show_log=False
            )
            self._initialized = True
            return True
        except ImportError:
            print("[OCR] PaddleOCR未安装，请执行: pip install paddleocr")
            self._initialized = True
            return False
        except Exception as e:
            print(f"[OCR] 初始化失败: {e}")
            self._initialized = True
            return False

    def _validate_input(self, image_path: str) -> tuple[bool, str]:
        """
        验证输入参数

        Returns:
            (是否有效, 错误消息)
        """
        if not image_path:
            return False, "图片路径不能为空"

        if not os.path.exists(image_path):
            return False, self.MSG_FILE_NOT_FOUND.format(path=image_path)

        ext = os.path.splitext(image_path)[1].lower()
        if ext not in self.SUPPORTED_FORMATS:
            return False, self.MSG_INVALID_FORMAT.format(ext=ext)

        return True, ""

    def _extract_text(self, ocr_result: list) -> str:
        """
        从OCR结果中提取并标准化文本

        Args:
            ocr_result: PaddleOCR返回的原始结果

        Returns:
            标准化后的文本（按行合并，去除首尾空白）
        """
        if not ocr_result or not ocr_result[0]:
            return ""

        lines = []
        for line in ocr_result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if isinstance(line[1], tuple) else str(line[1])
                text = text.strip()
                if text:
                    lines.append(text)

        return "\n".join(lines)

    def recognize(self, image_path: str) -> OCRResult:
        """
        识别图片中的文字

        Args:
            image_path: 本地图片的绝对路径

        Returns:
            OCRResult: 标准化的识别结果
        """
        # 1. 验证输入
        valid, error_msg = self._validate_input(image_path)
        if not valid:
            return OCRResult(
                success=False,
                text="",
                raw_text="",
                error_message=error_msg
            )

        # 2. 初始化OCR引擎
        if not self._init_ocr():
            return OCRResult(
                success=False,
                text="",
                raw_text="",
                error_message="[OCR] OCR引擎初始化失败"
            )

        # 3. 执行识别
        try:
            result = self._ocr.ocr(image_path, cls=True)

            # 4. 提取文本
            text = self._extract_text(result)
            raw_text = str(result) if result else ""

            if not text:
                return OCRResult(
                    success=True,
                    text=self.MSG_NO_VALID_TEXT,
                    raw_text=raw_text,
                    error_message=None
                )

            return OCRResult(
                success=True,
                text=text,
                raw_text=raw_text,
                error_message=None
            )

        except Exception as e:
            return OCRResult(
                success=False,
                text="",
                raw_text="",
                error_message=self.MSG_RECOGNITION_FAILED.format(error=str(e))
            )

    def recognize_to_message(self, image_path: str) -> str:
        """
        识别图片并返回标准化文本消息

        Args:
            image_path: 本地图片的绝对路径

        Returns:
            标准化的文本消息
        """
        result = self.recognize(image_path)

        if result.success:
            return result.text
        else:
            return result.error_message or self.MSG_NO_VALID_TEXT


def recognize_image(image_path: str, use_gpu: bool = False) -> str:
    """
    便捷函数：识别图片文字

    Args:
        image_path: 本地图片的绝对路径
        use_gpu: 是否使用GPU加速

    Returns:
        标准化的文本消息
    """
    middleware = OCRMiddleware(use_gpu=use_gpu)
    return middleware.recognize_to_message(image_path)


# ============== 测试入口 ==============

if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("OCR Middleware 测试")
    print("=" * 50)

    # 创建测试实例
    ocr = OCRMiddleware(use_gpu=False, lang='ch')

    # 测试用例
    test_cases = [
        # 测试1: 空路径
        "",
        # 测试2: 不存在的文件
        "D:/nonexistent/path/test.jpg",
        # 测试3: 不支持的格式
        "D:/test.txt",
    ]

    # 如果命令行提供了图片路径，加入测试
    if len(sys.argv) > 1:
        test_cases.append(sys.argv[1])

    for i, path in enumerate(test_cases, 1):
        print(f"\n--- 测试 {i} ---")
        print(f"输入路径: {path or '(空)'}")

        result = ocr.recognize(path)
        print(f"成功: {result.success}")
        print(f"文本: {result.text[:100]}..." if len(result.text) > 100 else f"文本: {result.text}")
        if result.error_message:
            print(f"错误: {result.error_message}")

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
    print("\n使用方法:")
    print("  python ocr_middleware.py <图片路径>")
    print("  python ocr_middleware.py  # 仅运行内置测试用例")