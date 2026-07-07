"""测试内容优化模块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import (
    ResumeDocument, JDSchema, JDRequirement,
    OptimizationLevel, OptimizationResult, ContentChange,
    IMMUTABLE_ANCHORS, FIDELITY_THRESHOLDS, FidelityViolationError,
)
from src.optimizer import optimize_resume, _extract_immutable_anchors, _check_anchor_preservation

SAMPLE_RESUME = """# 张三
## 工作经历
### 高级工程师 @ 科技有限公司
2021.03 - 至今
- 负责核心系统开发，使用 Python 和 Django 框架
- 优化数据库查询，性能提升 30%
- 主导 Docker 容器化部署项目

### 软件工程师 @ 另一家公司
2018.06 - 2021.02
- 参与 Web 应用开发，使用 React 和 Node.js
- 实现自动化测试，覆盖率提升到 85%

## 教育背景
北京大学 计算机科学 本科
2014.09 - 2018.06

## 技能
Python, JavaScript, React, Django, Docker, MySQL, Git
"""

SAMPLE_JD = JDSchema(
    job_title="高级Python开发工程师",
    company="科技有限公司",
    hard_requirements=[
        JDRequirement(text="精通Python，3年以上开发经验", category="skill", priority="must", weight=0.9),
        JDRequirement(text="熟悉Django/Flask框架", category="skill", priority="must", weight=0.9),
        JDRequirement(text="本科及以上学历", category="education", priority="must", weight=0.9),
    ],
    soft_requirements=[
        JDRequirement(text="良好的沟通能力和团队协作精神", category="soft_skill", priority="should", weight=0.7),
    ],
    keywords=["Python", "Django", "Docker", "MySQL", "Git", "沟通"],
    weight_matrix={"skill": 0.9, "education": 0.9, "soft_skill": 0.7},
    confidence_score=0.85,
)

def test_conservative_optimization():
    """测试保守优化 (保真度 ≥ 95%)"""
    resume = ResumeDocument(content=SAMPLE_RESUME)
    result = optimize_resume(resume, SAMPLE_JD, OptimizationLevel.CONSERVATIVE)

    assert isinstance(result, OptimizationResult)
    assert result.fidelity_score >= FIDELITY_THRESHOLDS[OptimizationLevel.CONSERVATIVE]
    print(f"  ✓ Conservative: fidelity={result.fidelity_score:.1f} ≥ 95.0")
    print(f"  ✓ Sections: {len(result.sections)}")
    print(f"  ✓ Changes: {len(result.changes)}")

def test_standard_optimization():
    """测试标准优化 (保真度 ≥ 92%)"""
    resume = ResumeDocument(content=SAMPLE_RESUME)
    result = optimize_resume(resume, SAMPLE_JD, OptimizationLevel.STANDARD)

    assert isinstance(result, OptimizationResult)
    assert result.fidelity_score >= FIDELITY_THRESHOLDS[OptimizationLevel.STANDARD]
    print(f"  ✓ Standard: fidelity={result.fidelity_score:.1f} ≥ 92.0")
    print(f"  ✓ Sections: {len(result.sections)}")
    print(f"  ✓ Changes: {len(result.changes)}")

def test_aggressive_optimization():
    """测试积极优化 (保真度 ≥ 90%)"""
    resume = ResumeDocument(content=SAMPLE_RESUME)
    result = optimize_resume(resume, SAMPLE_JD, OptimizationLevel.AGGRESSIVE)

    assert isinstance(result, OptimizationResult)
    assert result.fidelity_score >= FIDELITY_THRESHOLDS[OptimizationLevel.AGGRESSIVE]
    print(f"  ✓ Aggressive: fidelity={result.fidelity_score:.1f} ≥ 90.0")
    print(f"  ✓ Sections: {len(result.sections)}")
    print(f"  ✓ Changes: {len(result.changes)}")

def test_anchor_preservation():
    """测试事实锚点保留"""
    anchors = _extract_immutable_anchors(SAMPLE_RESUME)
    print(f"  ✓ Extracted {len(anchors)} anchors: {anchors[:3]}...")

    # 检查锚点保留
    lost = _check_anchor_preservation(SAMPLE_RESUME, SAMPLE_RESUME, anchors)
    assert len(lost) == 0, f"Anchors lost: {lost}"
    print("  ✓ All anchors preserved in identical text")

def test_change_log():
    """测试变更日志完整性"""
    resume = ResumeDocument(content=SAMPLE_RESUME)
    result = optimize_resume(resume, SAMPLE_JD, OptimizationLevel.STANDARD)

    for change in result.changes:
        assert change.section_title, "Change must have section_title"
        assert change.change_type, "Change must have change_type"
        assert change.risk_level, "Change must have risk_level"
        assert change.reason, "Change must have reason"

    print(f"  ✓ All {len(result.changes)} changes have complete log entries")

if __name__ == '__main__':
    print("=== Test Optimizer ===")
    test_anchor_preservation()
    test_conservative_optimization()
    test_standard_optimization()
    test_aggressive_optimization()
    test_change_log()
    print("\n=== All Optimizer tests passed! ===")

