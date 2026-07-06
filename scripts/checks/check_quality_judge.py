#!/usr/bin/env python3
"""
check_quality_judge.py - 验证 LLM-as-Judge 输出质量检查框架

检查项：
1. core/quality_judge.py 文件存在
2. QualityJudge 类存在且可实例化
3. QualityVerdict 数据类存在且有 passed 属性
4. QualityDimension 数据类存在
5. solution_quality_judge 预设工厂函数存在
6. ship_package_quality_judge 预设工厂函数存在
7. 降级模式（无 spawn_fn）可正常工作
8. build_judge_prompt 生成有效 prompt
"""
import sys
import pathlib

# 契约笼子: 自动发现 .deepflow 根目录
_p = pathlib.Path(__file__).resolve()
_root = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _root and str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def test_module_exists():
    """检查 core/quality_judge.py 文件存在"""
    module_path = _root / 'core' / 'quality_judge.py'
    assert module_path.exists(), f"文件不存在: {module_path}"
    print("✅ core/quality_judge.py 文件存在")


def test_classes_importable():
    """检查核心类和函数可导入"""
    import importlib
    import core.quality_judge as qj
    importlib.reload(qj)

    # 检查 QualityJudge 类
    assert hasattr(qj, 'QualityJudge'), "缺少 QualityJudge 类"
    print("✅ QualityJudge 类存在")

    # 检查 QualityVerdict 数据类
    assert hasattr(qj, 'QualityVerdict'), "缺少 QualityVerdict 数据类"
    print("✅ QualityVerdict 数据类存在")

    # 检查 QualityDimension 数据类
    assert hasattr(qj, 'QualityDimension'), "缺少 QualityDimension 数据类"
    print("✅ QualityDimension 数据类存在")

    # 检查预设工厂函数
    assert hasattr(qj, 'solution_quality_judge'), "缺少 solution_quality_judge 工厂函数"
    print("✅ solution_quality_judge 工厂函数存在")

    assert hasattr(qj, 'ship_package_quality_judge'), "缺少 ship_package_quality_judge 工厂函数"
    print("✅ ship_package_quality_judge 工厂函数存在")


def test_quality_verdict_passed_property():
    """检查 QualityVerdict 有 passed 属性"""
    from core.quality_judge import QualityVerdict

    # PASS → passed=True
    v1 = QualityVerdict(overall_score=8.0, recommendation="PASS")
    assert v1.passed is True, f"PASS 应 passed=True, 实际 {v1.passed}"
    print("✅ PASS recommendation → passed=True")

    # CONDITIONAL → passed=True
    v2 = QualityVerdict(overall_score=6.0, recommendation="CONDITIONAL")
    assert v2.passed is True, f"CONDITIONAL 应 passed=True, 实际 {v2.passed}"
    print("✅ CONDITIONAL recommendation → passed=True")

    # FAIL → passed=False
    v3 = QualityVerdict(overall_score=3.0, recommendation="FAIL")
    assert v3.passed is False, f"FAIL 应 passed=False, 实际 {v3.passed}"
    print("✅ FAIL recommendation → passed=False")


def test_quality_dimension_creation():
    """检查 QualityDimension 可正常创建"""
    from core.quality_judge import QualityDimension

    dim = QualityDimension("completeness", weight=2.0, description="覆盖所有需求")
    assert dim.name == "completeness"
    assert dim.weight == 2.0
    assert dim.description == "覆盖所有需求"
    print("✅ QualityDimension 创建正常")


def test_judge_instantiation():
    """检查 QualityJudge 可正常实例化"""
    from core.quality_judge import QualityJudge, QualityDimension

    judge = QualityJudge(dimensions=[
        QualityDimension("test_dim", weight=1.0, description="测试维度"),
    ])
    assert len(judge.dimensions) == 1
    assert judge.min_pass_score == 6.0
    print("✅ QualityJudge 实例化正常")


def test_build_judge_prompt():
    """检查 build_judge_prompt 生成有效 prompt"""
    from core.quality_judge import QualityJudge, QualityDimension

    judge = QualityJudge(dimensions=[
        QualityDimension("completeness", 2.0, "是否覆盖所有需求"),
        QualityDimension("clarity", 1.0, "表述是否清晰"),
    ])

    prompt = judge.build_judge_prompt(
        deliverable="这是一个测试方案文档，包含需求分析和实现步骤。",
        context="用户需求：实现一个登录功能",
    )

    # 检查 prompt 包含关键信息
    assert "独立质量评审专家" in prompt, "prompt 缺少角色定义"
    assert "测试方案文档" in prompt, "prompt 缺少交付物内容"
    assert "登录功能" in prompt, "prompt 缺少上下文"
    assert "completeness" in prompt, "prompt 缺少评分维度"
    assert "clarity" in prompt, "prompt 缺少评分维度"
    assert "overall_score" in prompt, "prompt 缺少输出格式要求"
    assert "PASS" in prompt and "CONDITIONAL" in prompt and "FAIL" in prompt, "prompt 缺少评分标准"
    print("✅ build_judge_prompt 生成有效 prompt")


def test_heuristic_evaluate():
    """检查降级模式（无 spawn_fn）可正常工作"""
    from core.quality_judge import QualityJudge, QualityDimension

    judge = QualityJudge(dimensions=[
        QualityDimension("test", 1.0, "测试"),
    ])

    # 测试短文本（应得低分）
    short_verdict = judge._heuristic_evaluate("短文本")
    assert 1.0 <= short_verdict.overall_score <= 10.0
    assert short_verdict.recommendation in ("PASS", "CONDITIONAL", "FAIL")
    assert "启发式评估" in str(short_verdict.weaknesses)
    print(f"✅ 短文本降级评估: score={short_verdict.overall_score}, rec={short_verdict.recommendation}")

    # 测试长文本（应得高分）
    long_text = "这是一段足够长的文本。" * 100
    long_verdict = judge._heuristic_evaluate(long_text)
    assert long_verdict.overall_score > short_verdict.overall_score
    print(f"✅ 长文本降级评估: score={long_verdict.overall_score}, rec={long_verdict.recommendation}")


def test_evaluate_without_spawn_fn():
    """检查 evaluate() 在 spawn_fn=None 时降级到启发式评估"""
    from core.quality_judge import QualityJudge, QualityDimension

    judge = QualityJudge(dimensions=[
        QualityDimension("test", 1.0, "测试"),
    ])

    verdict = judge.evaluate(
        deliverable="测试交付物内容" * 50,
        context="测试上下文",
        spawn_fn=None,
    )

    assert isinstance(verdict.overall_score, float)
    assert verdict.recommendation in ("PASS", "CONDITIONAL", "FAIL")
    assert "启发式评估" in str(verdict.weaknesses)
    print("✅ evaluate(spawn_fn=None) 降级到启发式评估")


def test_preset_judges():
    """检查预设 Judge 配置正确"""
    from core.quality_judge import solution_quality_judge, ship_package_quality_judge

    # Solution Pro Judge
    sol_judge = solution_quality_judge()
    dim_names = {d.name for d in sol_judge.dimensions}
    assert "completeness" in dim_names, "Solution Judge 缺少 completeness 维度"
    assert "feasibility" in dim_names, "Solution Judge 缺少 feasibility 维度"
    assert "clarity" in dim_names, "Solution Judge 缺少 clarity 维度"
    assert "innovation" in dim_names, "Solution Judge 缺少 innovation 维度"
    print(f"✅ solution_quality_judge: {len(sol_judge.dimensions)} 个维度")

    # Ship Pro Judge
    ship_judge = ship_package_quality_judge()
    dim_names = {d.name for d in ship_judge.dimensions}
    assert "completeness" in dim_names, "Ship Judge 缺少 completeness 维度"
    assert "actionability" in dim_names, "Ship Judge 缺少 actionability 维度"
    assert "dependency_correctness" in dim_names, "Ship Judge 缺少 dependency_correctness 维度"
    assert "effort_estimation" in dim_names, "Ship Judge 缺少 effort_estimation 维度"
    print(f"✅ ship_package_quality_judge: {len(ship_judge.dimensions)} 个维度")


def test_parse_verdict():
    """检查 _parse_verdict 能正确解析 JSON 响应"""
    from core.quality_judge import QualityJudge, QualityDimension

    judge = QualityJudge(dimensions=[
        QualityDimension("test", 1.0, "测试"),
    ])

    # 测试标准 JSON 响应
    raw_json = '''
    这是一些前缀文本
    ```json
    {
        "overall_score": 8.5,
        "dimension_scores": {"test": 8.0},
        "strengths": ["结构清晰"],
        "weaknesses": ["缺少细节"],
        "recommendation": "PASS"
    }
    ```
    '''
    verdict = judge._parse_verdict(raw_json)
    assert verdict.overall_score == 8.5, f"overall_score 应为 8.5, 实际 {verdict.overall_score}"
    assert verdict.recommendation == "PASS"
    assert "结构清晰" in verdict.strengths
    print("✅ _parse_verdict 解析标准 JSON 正常")

    # 测试无 JSON 的响应（降级为 CONDITIONAL）
    bad_response = "这不是 JSON 格式"
    verdict2 = judge._parse_verdict(bad_response)
    assert verdict2.recommendation == "CONDITIONAL"
    assert "解析失败" in str(verdict2.weaknesses)
    print("✅ _parse_verdict 解析失败时降级为 CONDITIONAL")


if __name__ == "__main__":
    print("=" * 50)
    print("Quality Judge 框架契约验证")
    print("=" * 50)

    tests = [
        test_module_exists,
        test_classes_importable,
        test_quality_verdict_passed_property,
        test_quality_dimension_creation,
        test_judge_instantiation,
        test_build_judge_prompt,
        test_heuristic_evaluate,
        test_evaluate_without_spawn_fn,
        test_preset_judges,
        test_parse_verdict,
    ]

    failed = []
    for test_fn in tests:
        try:
            test_fn()
        except AssertionError as e:
            print(f"❌ {test_fn.__name__}: {e}")
            failed.append(test_fn.__name__)
        except Exception as e:
            print(f"❌ {test_fn.__name__} 异常: {e}")
            failed.append(test_fn.__name__)

    print("=" * 50)
    if failed:
        print(f"❌ {len(failed)} 项失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"✅ 全部通过 ({len(tests)} 项)")
        sys.exit(0)
