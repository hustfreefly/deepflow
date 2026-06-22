"""测试核心引擎"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import (
    ResumeFitRequest, ResumeDocument, JDInput, JDInputType,
    OptimizationLevel, ResumeFitResponse,
    ResumeFitError, JDParsingError, OCRError,
    FidelityViolationError, PDFGenerationError,
)
from src.engine import process_resume

SAMPLE_RESUME_CONTENT = """# 张三
## 工作经历
### 高级工程师 @ 科技有限公司
2021.03 - 至今
- 负责核心系统开发，使用 Python 和 Django 框架
- 优化数据库查询，性能提升 30%
- 熟练使用 Docker 容器化部署

### 软件工程师 @ 另一家公司
2018.06 - 2021.02
- 参与 Web 应用开发，使用 React 和 Node.js
- 实现自动化测试，覆盖率提升到 85%

## 教育背景
北京大学 计算机科学 本科
2014.09 - 2018.06

## 专业技能
Python, JavaScript, React, Django, Docker, MySQL, Git, Linux
"""

SAMPLE_JD_CONTENT = """
职位名称: 高级Python开发工程师
公司: 科技有限公司
要求:
- 必须精通Python，3年以上开发经验
- 熟悉Django/Flask框架
- 本科及以上学历，计算机相关专业
- 有Docker/Kubernetes经验者优先
- 良好的沟通能力和团队协作精神
- 熟悉MySQL数据库
- 加分项: 有AI/ML项目经验
"""

def test_full_pipeline():
    """测试完整流程"""
    request = ResumeFitRequest(
        base_resume=ResumeDocument(content=SAMPLE_RESUME_CONTENT),
        job_description=JDInput(content=SAMPLE_JD_CONTENT, input_type=JDInputType.TEXT),
        optimization_level=OptimizationLevel.STANDARD,
        preferred_language="zh",
        max_pages=2,
    )

    response = process_resume(request)

    assert isinstance(response, ResumeFitResponse)
    assert response.optimized_resume is not None
    assert response.quality_report is not None
    assert response.changes_summary is not None
    assert response.jd_schema is not None
    assert response.optimization_result is not None
    assert response.processing_time_seconds > 0
    assert response.version == "1.0.0"

    print(f"  ✓ Response type: {type(response).__name__}")
    print(f"  ✓ PDF output: {response.optimized_resume.file_path}")
    print(f"  ✓ PDF size: {response.optimized_resume.file_size_bytes} bytes")
    print(f"  ✓ ATS compatible: {response.optimized_resume.ats_compatible}")
    print(f"  ✓ Text extractable: {response.optimized_resume.text_extractable}")
    print(f"  ✓ Quality report: {response.quality_report.summary}")
    print(f"  ✓ Changes: {len(response.changes_summary)}")
    print(f"  ✓ Processing time: {response.processing_time_seconds:.3f}s")
    print(f"  ✓ JD schema: {response.jd_schema.job_title}")

    # Cleanup
    if os.path.exists(response.optimized_resume.file_path):
        os.remove(response.optimized_resume.file_path)

def test_conservative_level():
    """测试保守级别"""
    request = ResumeFitRequest(
        base_resume=ResumeDocument(content=SAMPLE_RESUME_CONTENT),
        job_description=JDInput(content=SAMPLE_JD_CONTENT, input_type=JDInputType.TEXT),
        optimization_level=OptimizationLevel.CONSERVATIVE,
    )
    response = process_resume(request)
    assert response.optimization_result.fidelity_score >= 95.0
    print(f"  ✓ Conservative fidelity: {response.optimization_result.fidelity_score}")

def test_aggressive_level():
    """测试积极级别"""
    request = ResumeFitRequest(
        base_resume=ResumeDocument(content=SAMPLE_RESUME_CONTENT),
        job_description=JDInput(content=SAMPLE_JD_CONTENT, input_type=JDInputType.TEXT),
        optimization_level=OptimizationLevel.AGGRESSIVE,
    )
    response = process_resume(request)
    assert response.optimization_result.fidelity_score >= 90.0
    print(f"  ✓ Aggressive fidelity: {response.optimization_result.fidelity_score}")

def test_error_handling():
    """测试错误处理"""
    # 测试未知输入类型 (should not happen with enum, but test error path)
    # Test with empty JD (should still work but with low confidence)
    request = ResumeFitRequest(
        base_resume=ResumeDocument(content=SAMPLE_RESUME_CONTENT),
        job_description=JDInput(content="", input_type=JDInputType.TEXT),
        optimization_level=OptimizationLevel.STANDARD,
    )
    # Should not crash, but produce low-confidence results
    response = process_resume(request)
    assert response.jd_schema.confidence_score < 0.5
    print(f"  ✓ Empty JD handled: confidence={response.jd_schema.confidence_score}")

    # Test error class hierarchy
    assert issubclass(JDParsingError, ResumeFitError)
    assert issubclass(OCRError, ResumeFitError)
    assert issubclass(FidelityViolationError, ResumeFitError)
    assert issubclass(PDFGenerationError, ResumeFitError)
    print("  ✓ All error classes inherit ResumeFitError")

def test_response_format():
    """测试响应格式符合接口定义"""
    request = ResumeFitRequest(
        base_resume=ResumeDocument(content=SAMPLE_RESUME_CONTENT),
        job_description=JDInput(content=SAMPLE_JD_CONTENT, input_type=JDInputType.TEXT),
        optimization_level=OptimizationLevel.STANDARD,
    )
    response = process_resume(request)

    # Check all required fields
    assert hasattr(response, 'optimized_resume')
    assert hasattr(response, 'quality_report')
    assert hasattr(response, 'changes_summary')
    assert hasattr(response, 'jd_schema')
    assert hasattr(response, 'optimization_result')
    assert hasattr(response, 'processing_time_seconds')
    assert hasattr(response, 'version')

    # Check nested types
    assert hasattr(response.optimized_resume, 'file_path')
    assert hasattr(response.optimized_resume, 'file_size_bytes')
    assert hasattr(response.optimized_resume, 'page_count')
    assert hasattr(response.optimized_resume, 'ats_compatible')
    assert hasattr(response.optimized_resume, 'text_extractable')

    assert hasattr(response.quality_report, 'metrics')
    assert hasattr(response.quality_report, 'summary')
    assert hasattr(response.quality_report, 'recommendations')

    print("  ✓ All response fields present")
    print("  ✓ All nested types correct")

    # Cleanup
    if os.path.exists(response.optimized_resume.file_path):
        os.remove(response.optimized_resume.file_path)

if __name__ == '__main__':
    print("=== Test Engine ===")
    test_full_pipeline()
    test_conservative_level()
    test_aggressive_level()
    test_error_handling()
    test_response_format()
    print("\n=== All Engine tests passed! ===")

