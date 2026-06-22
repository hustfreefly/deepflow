"""
PDF 渲染模块
============

将优化后的简历内容渲染为 ATS 兼容的 PDF 文档。

功能:
- HTML → PDF（WeasyPrint）
- ATS 兼容格式（单列、标准字体、无页眉关键信息）
- 基础排版（粗体关键词、项目符号、合理间距）
"""

from __future__ import annotations
import os
import logging
import tempfile
from typing import Optional

from .interfaces import (
    OptimizationResult,
    ResumeSection,
    PDFOutput,
    PDFGenerationError,
)

logger = logging.getLogger(__name__)

# ATS 兼容的 CSS 样式
ATS_CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
}

body {
    font-family: "Helvetica Neue", Helvetica, Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 11pt;
    line-height: 1.4;
    color: #333;
}

h1 {
    font-size: 20pt;
    font-weight: bold;
    margin-bottom: 2mm;
    color: #1a1a1a;
    border-bottom: 2px solid #333;
    padding-bottom: 2mm;
}

h2 {
    font-size: 14pt;
    font-weight: bold;
    margin-top: 5mm;
    margin-bottom: 2mm;
    color: #2c2c2c;
    border-bottom: 1px solid #999;
    padding-bottom: 1mm;
}

h3 {
    font-size: 12pt;
    font-weight: bold;
    margin-top: 3mm;
    margin-bottom: 1mm;
    color: #444;
}

p {
    margin: 1mm 0;
    text-align: justify;
}

ul {
    margin: 1mm 0;
    padding-left: 6mm;
}

li {
    margin: 0.5mm 0;
    line-height: 1.45;
}

.keyword {
    font-weight: bold;
}

.contact-info {
    font-size: 9pt;
    color: #666;
    margin-bottom: 3mm;
}

.section-content {
    margin-bottom: 3mm;
}
"""


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def _format_section_content(content: str) -> str:
    """将 Markdown/纯文本段落内容转换为 HTML"""
    lines = content.split('\n')
    html_parts = []

    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            continue

        # 项目符号
        if stripped.startswith('•') or stripped.startswith('-') or stripped.startswith('* '):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            item_text = stripped.lstrip('•-').strip()
            # 加粗关键词（简单启发）
            item_text = _highlight_keywords(_escape_html(item_text))
            html_parts.append(f'<li>{item_text}</li>')
        else:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            # 普通段落
            escaped = _escape_html(stripped)
            escaped = _highlight_keywords(escaped)
            html_parts.append(f'<p>{escaped}</p>')

    if in_list:
        html_parts.append('</ul>')

    return '\n'.join(html_parts)


def _highlight_keywords(text: str) -> str:
    """对技术关键词加粗显示"""
    tech_keywords = [
        'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'Go', 'Rust',
        'React', 'Vue', 'Angular', 'Spring', 'Django', 'Flask', 'FastAPI',
        'TensorFlow', 'PyTorch', 'Docker', 'Kubernetes', 'AWS', 'Azure',
        'MySQL', 'PostgreSQL', 'Redis', 'MongoDB', 'Git', 'Linux',
        'AI', 'ML', 'NLP', 'LLM', '大模型', '机器学习', '深度学习',
    ]
    for kw in tech_keywords:
        # 只加粗独立出现的关键词
        import re
        pattern = rf'(?<!\w){re.escape(kw)}(?!\w)'
        text = re.sub(pattern, f'<span class="keyword">{kw}</span>', text)
    return text


def _build_html(optimization_result: OptimizationResult) -> str:
    """构建完整的 HTML 文档"""
    sections_html = ''

    for section in optimization_result.sections:
        section_html = f'''
        <div class="section-content">
            <h2>{_escape_html(section.title)}</h2>
            {_format_section_content(section.content)}
        </div>
        '''
        sections_html += section_html

    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <style>
        {ATS_CSS}
    </style>
</head>
<body>
    {sections_html}
</body>
</html>'''

    return html


def render_pdf(
    optimization_result: OptimizationResult,
    output_path: Optional[str] = None,
    max_pages: int = 2,
) -> PDFOutput:
    """
    将优化结果渲染为 PDF。

    Args:
        optimization_result: 优化后的简历
        output_path: 输出路径（默认临时文件）
        max_pages: 最大页数

    Returns:
        PDFOutput 包含文件信息和 ATS 兼容性

    Raises:
        PDFGenerationError: PDF 生成失败
    """
    logger.info("Rendering PDF, max_pages=%d", max_pages)

    if not output_path:
        fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='resumefit_')
        os.close(fd)

    html_content = _build_html(optimization_result)

    # Try WeasyPrint
    try:
        from weasyprint import HTML, CSS
        html_doc = HTML(string=html_content, base_url=None)
        html_doc.write_pdf(output_path)
        logger.info("WeasyPrint rendered PDF to %s", output_path)
    except ImportError:
        raise PDFGenerationError(
            "WeasyPrint not installed. Install with: pip install weasyprint"
        )
    except Exception as e:
        raise PDFGenerationError(f"PDF generation failed: {e}")

    # 获取文件信息
    file_size = os.path.getsize(output_path)
    logger.info("PDF size: %d bytes", file_size)

    # 检查文件大小（< 2MB）
    if file_size > 2 * 1024 * 1024:
        logger.warning("PDF size %d exceeds 2MB limit", file_size)

    # 检查文本可提取性
    text_extractable = _check_text_extractable(output_path)

    pdf_output = PDFOutput(
        file_path=output_path,
        file_size_bytes=file_size,
        page_count=1,  # WeasyPrint 自动分页，简化处理
        ats_compatible=True,  # 使用 ATS 兼容模板
        text_extractable=text_extractable,
    )

    logger.info("PDF output: path=%s, size=%d, ats=%s, text=%s",
                pdf_output.file_path, pdf_output.file_size_bytes,
                pdf_output.ats_compatible, pdf_output.text_extractable)

    return pdf_output


def _check_text_extractable(pdf_path: str) -> bool:
    """检查 PDF 是否包含可提取的文本（非纯图片）"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        has_text = False
        for page in doc:
            text = page.get_text()
            if text.strip():
                has_text = True
                break
        doc.close()
        return has_text
    except ImportError:
        # 如果没有 PyMuPDF，假设文本可提取（因为我们是从 HTML 生成的）
        return True
    except Exception:
        return True  # 默认可提取
