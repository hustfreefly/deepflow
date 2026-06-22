"""
OCR 辅助工具

支持图片（PNG/JPG）和 PDF 文件的文本提取
优先级：PyMuPDF（PDF）→ PaddleOCR（图片）

版本: 1.0.0-Lite
"""

import os
import sys
from typing import Optional


def ocr_extract(file_path: str) -> str:
    """
    从图片或 PDF 文件中提取文本

    Args:
        file_path: 文件路径

    Returns:
        提取的文本内容

    Raises:
        ValueError: 文件不存在或格式不支持
        RuntimeError: OCR 提取失败
    """
    if not os.path.exists(file_path):
        raise ValueError(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    # PDF 文件：优先使用 PyMuPDF
    if ext == '.pdf':
        return _extract_from_pdf(file_path)

    # 图片文件：使用 PaddleOCR
    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
        return _extract_from_image(file_path)

    else:
        raise ValueError(f"不支持的文件格式: {ext}。支持: .pdf, .png, .jpg, .jpeg, .bmp, .tiff")


def _extract_from_pdf(file_path: str) -> str:
    """使用 PyMuPDF 提取 PDF 文本"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF 未安装。请运行: pip install pymupdf")

    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        text = text.strip()
        if not text:
            raise RuntimeError("PDF 文件中未找到文本内容")

        return text
    except Exception as e:
        raise RuntimeError(f"PDF 文本提取失败: {str(e)}")


def _extract_from_image(file_path: str) -> str:
    """使用 PaddleOCR 提取图片文本"""
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise RuntimeError("PaddleOCR 未安装。请运行: pip install paddleocr paddlepaddle")

    try:
        # 初始化 OCR（使用中文模型）
        ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)

        # 执行 OCR
        result = ocr.ocr(file_path, cls=True)

        # 提取文本
        text_lines = []
        for line in result[0]:
            if line:
                text_lines.append(line[1][0])  # [坐标, (文本, 置信度)]

        text = '\n'.join(text_lines).strip()
        if not text:
            raise RuntimeError("图片中未识别到文本内容")

        return text
    except Exception as e:
        raise RuntimeError(f"图片 OCR 失败: {str(e)}")


def check_ocr_dependencies() -> dict:
    """
    检查 OCR 依赖是否已安装

    Returns:
        {
            'pymupdf': bool,
            'paddleocr': bool,
            'ready': bool
        }
    """
    status = {
        'pymupdf': False,
        'paddleocr': False
    }

    try:
        import fitz
        status['pymupdf'] = True
    except ImportError:
        pass

    try:
        from paddleocr import PaddleOCR
        status['paddleocr'] = True
    except ImportError:
        pass

    status['ready'] = status['pymupdf'] or status['paddleocr']
    return status
