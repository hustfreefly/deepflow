"""测试 PDF 渲染模块"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import (
    OptimizationLevel, OptimizationResult, ResumeSection, PDFOutput,
    PDFGenerationError,
)
from src.pdf_renderer import render_pdf, _build_html, _format_section_content

SAMPLE_SECTIONS = [
    ResumeSection(title="个人信息", content="张三\n电话: 138-0000-0000\n邮箱: zhangsan@example.com", section_type="summary"),
    ResumeSection(title="工作经历", content="### 高级工程师 @ 科技有限公司\n2021.03 - 至今\n- 负责核心系统开发，使用 Python 和 Django\n- 优化数据库查询，性能提升 30%\n- 熟练使用 Docker 容器化部署", section_type="experience"),
    ResumeSection(title="教育背景", content="北京大学 计算机科学 本科\n2014.09 - 2018.06", section_type="education"),
    ResumeSection(title="专业技能", content="Python, Django, Docker, MySQL, Git, React", section_type="skills"),
]

def test_html_generation():
    """测试 HTML 构建"""
    result = OptimizationResult(
        sections=SAMPLE_SECTIONS,
        changes=[],
        fidelity_score=95.0,
        optimization_level=OptimizationLevel.STANDARD,
    )
    html = _build_html(result)
    assert '<!DOCTYPE html>' in html
    assert '<h2>' in html
    assert '</html>' in html
    print("  ✓ HTML generated successfully")
    print(f"  ✓ HTML length: {len(html)} chars")

def test_section_formatting():
    """测试段落内容格式化"""
    content = "- 使用 Python 开发系统\n- 性能提升 30%\n普通段落文字"
    html = _format_section_content(content)
    assert '<ul>' in html
    assert '<li>' in html
    assert '<p>' in html
    print("  ✓ Section formatting works")

def test_pdf_render():
    """测试 PDF 生成"""
    result = OptimizationResult(
        sections=SAMPLE_SECTIONS,
        changes=[],
        fidelity_score=95.0,
        optimization_level=OptimizationLevel.STANDARD,
    )

    output_path = os.path.join(tempfile.gettempdir(), 'test_resumefit.pdf')
    pdf = render_pdf(result, output_path=output_path)

    assert isinstance(pdf, PDFOutput)
    assert os.path.exists(pdf.file_path), "PDF file must exist"
    assert pdf.file_size_bytes > 0, "PDF must have size > 0"
    assert pdf.file_size_bytes < 2 * 1024 * 1024, f"PDF must be < 2MB, got {pdf.file_size_bytes}"
    assert pdf.ats_compatible, "Must be ATS compatible"
    assert pdf.text_extractable, "Must have extractable text"

    print(f"  ✓ PDF generated: {pdf.file_path}")
    print(f"  ✓ File size: {pdf.file_size_bytes} bytes (< 2MB)")
    print(f"  ✓ ATS compatible: {pdf.ats_compatible}")
    print(f"  ✓ Text extractable: {pdf.text_extractable}")
    print(f"  ✓ Page count: {pdf.page_count}")

    # Cleanup
    os.remove(output_path)

def test_ats_format():
    """测试 ATS 格式检查"""
    result = OptimizationResult(
        sections=SAMPLE_SECTIONS,
        changes=[],
        fidelity_score=95.0,
        optimization_level=OptimizationLevel.STANDARD,
    )
    html = _build_html(result)
    # ATS 兼容格式不应包含表格或图片
    assert '<table' not in html, "ATS format should not contain tables"
    assert '<img' not in html, "ATS format should not contain images"
    print("  ✓ ATS format check passed (no tables/images)")

if __name__ == '__main__':
    print("=== Test PDF Renderer ===")
    test_html_generation()
    test_section_formatting()
    test_pdf_render()
    test_ats_format()
    print("\n=== All PDF Renderer tests passed! ===")
