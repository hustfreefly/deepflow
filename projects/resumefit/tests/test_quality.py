"""测试质量报告模块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import (
    JDSchema, JDRequirement, OptimizationLevel, OptimizationResult,
    ResumeSection, PDFOutput, QualityReport, QualityMetrics,
    QUALITY_THRESHOLDS,
)
from src.quality import (
    generate_quality_report,
    _compute_keyword_coverage,
    _compute_semantic_similarity,
    _compute_formatting_score,
    _compute_ats_compatibility,
    _compute_naturalness_score,
    _generate_warnings,
)

SAMPLE_JD = JDSchema(
    job_title="高级Python开发工程师",
    company="科技有限公司",
    hard_requirements=[
        JDRequirement(text="精通Python", category="skill", priority="must", weight=0.9),
        JDRequirement(text="熟悉Django框架", category="skill", priority="must", weight=0.9),
    ],
    soft_requirements=[
        JDRequirement(text="良好的沟通能力", category="soft_skill", priority="should", weight=0.7),
    ],
    keywords=["Python", "Django", "Docker", "MySQL", "Git"],
    weight_matrix={"skill": 0.9, "soft_skill": 0.7},
    confidence_score=0.85,
)

SAMPLE_OPT_RESULT = OptimizationResult(
    sections=[
        ResumeSection(title="工作经历", content="使用 Python 和 Django 开发系统，性能提升 30%，使用 Docker 部署", section_type="experience"),
        ResumeSection(title="教育背景", content="北京大学 计算机科学 本科", section_type="education"),
        ResumeSection(title="专业技能", content="Python, Django, Docker, MySQL, Git", section_type="skills"),
    ],
    changes=[],
    fidelity_score=95.0,
    optimization_level=OptimizationLevel.STANDARD,
)

SAMPLE_PDF = PDFOutput(
    file_path="/tmp/test.pdf",
    file_size_bytes=100000,
    page_count=1,
    ats_compatible=True,
    text_extractable=True,
)

def test_keyword_coverage():
    """测试关键词覆盖率"""
    resume_text = '\n'.join(s.content for s in SAMPLE_OPT_RESULT.sections)
    coverage = _compute_keyword_coverage(resume_text, SAMPLE_JD)
    assert 0 <= coverage <= 100
    print(f"  ✓ Keyword coverage: {coverage}%")

def test_semantic_similarity():
    """测试语义相似度"""
    resume_text = '\n'.join(s.content for s in SAMPLE_OPT_RESULT.sections)
    similarity = _compute_semantic_similarity(resume_text, SAMPLE_JD)
    assert 0 <= similarity <= 100
    print(f"  ✓ Semantic similarity: {similarity}%")

def test_formatting_score():
    """测试排版评分"""
    score = _compute_formatting_score(SAMPLE_PDF)
    assert 0 <= score <= 100
    print(f"  ✓ Formatting score: {score}")

def test_ats_compatibility():
    """测试 ATS 兼容性"""
    resume_text = '\n'.join(s.content for s in SAMPLE_OPT_RESULT.sections)
    score = _compute_ats_compatibility(SAMPLE_PDF, resume_text)
    assert 0 <= score <= 100
    print(f"  ✓ ATS compatibility: {score}")

def test_naturalness_score():
    """测试自然度评分"""
    resume_text = '\n'.join(s.content for s in SAMPLE_OPT_RESULT.sections)
    score = _compute_naturalness_score(SAMPLE_OPT_RESULT, resume_text)
    assert 0 <= score <= 100
    print(f"  ✓ Naturalness score: {score}")

def test_6d_metrics():
    """测试 6 维度评分全部可计算"""
    report = generate_quality_report(SAMPLE_JD, SAMPLE_OPT_RESULT, SAMPLE_PDF)

    assert isinstance(report, QualityReport)
    assert isinstance(report.metrics, QualityMetrics)

    # 检查 6 维度
    m = report.metrics
    assert m.keyword_coverage >= 0, "keyword_coverage must be >= 0"
    assert m.semantic_similarity >= 0, "semantic_similarity must be >= 0"
    assert m.fidelity_score >= 0, "fidelity_score must be >= 0"
    assert m.formatting_score >= 0, "formatting_score must be >= 0"
    assert m.ats_compatibility >= 0, "ats_compatibility must be >= 0"
    assert m.naturalness_score >= 0, "naturalness_score must be >= 0"

    print(f"  ✓ 6 metrics computed:")
    print(f"    keyword_coverage: {m.keyword_coverage}")
    print(f"    semantic_similarity: {m.semantic_similarity}")
    print(f"    fidelity_score: {m.fidelity_score}")
    print(f"    formatting_score: {m.formatting_score}")
    print(f"    ats_compatibility: {m.ats_compatibility}")
    print(f"    naturalness_score: {m.naturalness_score}")

def test_threshold_check():
    """测试阈值检查生效"""
    report = generate_quality_report(SAMPLE_JD, SAMPLE_OPT_RESULT, SAMPLE_PDF)

    assert report.metrics.passed_thresholds is not None
    assert isinstance(report.metrics.passed_thresholds, bool)
    assert report.summary, "Summary must not be empty"
    print(f"  ✓ Threshold check: passed={report.metrics.passed_thresholds}")
    print(f"  ✓ Summary: {report.summary}")

def test_warnings_and_recommendations():
    """测试告警和建议"""
    report = generate_quality_report(SAMPLE_JD, SAMPLE_OPT_RESULT, SAMPLE_PDF)

    assert isinstance(report.metrics.warnings, list)
    assert isinstance(report.recommendations, list)
    assert len(report.recommendations) > 0, "Must have recommendations"
    print(f"  ✓ Warnings: {len(report.metrics.warnings)}")
    print(f"  ✓ Recommendations: {report.recommendations}")

if __name__ == '__main__':
    print("=== Test Quality Report ===")
    test_keyword_coverage()
    test_semantic_similarity()
    test_formatting_score()
    test_ats_compatibility()
    test_naturalness_score()
    test_6d_metrics()
    test_threshold_check()
    test_warnings_and_recommendations()
    print("\n=== All Quality Report tests passed! ===")
