"""测试保真度校验模块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import (
    ResumeDocument, JDSchema, JDRequirement,
    OptimizationLevel, OptimizationResult, ResumeSection, ContentChange,
    RiskLevel, FidelityViolationError, FIDELITY_THRESHOLDS,
)
from src.fidelity import (
    extract_anchors, compute_diff, ner_check,
    compute_fidelity_score, validate_fidelity,
    _detect_high_risk_changes,
)

ORIGINAL = """# 张三
## 工作经历
### 高级工程师 @ 科技有限公司
2021.03 - 至今
- 负责核心系统开发，使用 Python 和 Django 框架
- 优化数据库查询，性能提升 30%

## 教育背景
北京大学 计算机科学 本科
2014.09 - 2018.06
"""

OPTIMIZED = """# 张三
## 工作经历
### 高级工程师 @ 科技有限公司
2021.03 - 至今
- 负责核心系统开发，使用 Python 和 Django 框架
- 优化数据库查询，性能提升 30%
- 熟练使用 Docker 容器化部署

## 教育背景
北京大学 计算机科学 本科
2014.09 - 2018.06
"""

def test_anchor_extraction():
    """测试锚点提取"""
    anchors = extract_anchors(ORIGINAL)
    assert 'company_name' in anchors
    assert 'employment_dates' in anchors
    assert 'education_degree' in anchors
    assert 'quantitative_metrics' in anchors
    print(f"  ✓ Anchors: {[(k, len(v)) for k, v in anchors.items()]}")

def test_diff():
    """测试 diff 计算"""
    changes = compute_diff(ORIGINAL, OPTIMIZED)
    # 应该有变更（增加了 Docker 行）
    print(f"  ✓ Diff detected {len(changes)} changed lines")
    assert len(changes) > 0, "Expected changes between original and optimized"

def test_ner_check():
    """测试 NER 校验"""
    result = ner_check(ORIGINAL, OPTIMIZED)
    print(f"  ✓ NER: added={result['added']}, removed={result['removed']}")
    # 优化后不应移除实体
    assert len(result['removed']) == 0, f"Should not remove entities: {result['removed']}"

def test_fidelity_computation():
    """测试保真度计算"""
    changes = []
    score = compute_fidelity_score(ORIGINAL, OPTIMIZED, changes)
    assert 0 <= score <= 100
    print(f"  ✓ Fidelity score: {score}")
    # 高度相似的文本应有高分
    assert score >= 80, f"Expected score >= 80, got {score}"

def test_anchor_100_preserved():
    """测试事实锚点 100% 保留"""
    # 相同文本应 100% 保留
    anchors = extract_anchors(ORIGINAL)
    total = sum(len(v) for v in anchors.values())
    assert total > 0, "Should have anchors"

    opt_anchors = extract_anchors(ORIGINAL)  # 相同文本
    preserved = 0
    for atype, values in anchors.items():
        opt_vals = set(opt_anchors.get(atype, []))
        for v in values:
            if v in opt_vals:
                preserved += 1

    assert preserved == total, f"Expected {total} preserved, got {preserved}"
    print(f"  ✓ {total}/{total} anchors preserved (100%)")

def test_validate_fidelity():
    """测试完整校验流程"""
    sections = [
        ResumeSection(title="工作经历", content=OPTIMIZED, section_type="experience"),
    ]
    opt_result = OptimizationResult(
        sections=sections,
        changes=[],
        fidelity_score=95.0,
        optimization_level=OptimizationLevel.CONSERVATIVE,
    )
    resume = ResumeDocument(content=ORIGINAL)

    score, high_risk = validate_fidelity(resume, opt_result)
    assert score >= FIDELITY_THRESHOLDS[OptimizationLevel.CONSERVATIVE]
    print(f"  ✓ Validation passed: score={score}")

if __name__ == '__main__':
    print("=== Test Fidelity ===")
    test_anchor_extraction()
    test_anchor_100_preserved()
    test_diff()
    test_ner_check()
    test_fidelity_computation()
    test_validate_fidelity()
    print("\n=== All Fidelity tests passed! ===")

