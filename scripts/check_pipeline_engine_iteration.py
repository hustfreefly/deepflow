#!/usr/bin/env python3
"""
验证 PipelineEngine 迭代循环修复
"""
import sys
import os
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from unittest.mock import Mock, patch, MagicMock
from pipeline_engine import PipelineEngine, PipelineStage, PipelineState, PipelineResult, StageResult
from config_loader import DomainConfig, AgentConfig, DomainQualityConfig

def test_iteration_structure():
    """测试：PipelineEngine 是否有外部迭代循环"""
    print("=" * 60)
    print("测试 1: 外部迭代循环结构检查")
    print("=" * 60)
    
    # 检查 _run_pipeline 和 _run_iteration_stages 方法源码
    import inspect
    pipeline_source = inspect.getsource(PipelineEngine._run_pipeline)
    iteration_source = inspect.getsource(PipelineEngine._run_iteration_stages)
    combined_source = pipeline_source + iteration_source
    
    checks = {
        "外部迭代循环": "for iteration" in pipeline_source or "range(" in pipeline_source,
        "_run_iteration_stages 调用": "_run_iteration_stages" in pipeline_source,
        "_should_skip_stage_in_iteration 调用": "_should_skip_stage_in_iteration" in combined_source,
    }
    
    all_pass = True
    for name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {'通过' if result else '未找到'}")
        if not result:
            all_pass = False
    
    return all_pass

def test_skip_logic():
    """测试：_should_skip_stage_in_iteration 逻辑"""
    print("\n" + "=" * 60)
    print("测试 2: Stage 跳过逻辑")
    print("=" * 60)
    
    # 创建 mock engine
    mock_config = Mock()
    mock_config.max_iterations = 5
    mock_config.min_iterations = 2
    
    engine = PipelineEngine.__new__(PipelineEngine)
    engine._domain_config = mock_config
    
    # 检查方法是否存在
    if not hasattr(engine, '_should_skip_stage_in_iteration'):
        print("  ❌ _should_skip_stage_in_iteration 方法不存在")
        return False
    
    test_cases = [
        # (stage_id, iteration, expected_skip)
        ("data_manager", 0, False),   # 第一轮不跳过
        ("data_manager", 1, True),    # 后续轮跳过
        ("planner", 1, True),         # 后续轮跳过
        ("researcher", 2, True),      # 后续轮跳过
        ("auditor", 0, False),        # 第一轮执行
        ("auditor", 1, False),        # 后续轮执行
        ("fixer", 2, False),          # 后续轮执行
        ("verifier", 3, False),       # 后续轮执行
    ]
    
    all_pass = True
    for stage_id, iteration, expected in test_cases:
        stage = PipelineStage(id=stage_id, agent=stage_id)
        try:
            result = engine._should_skip_stage_in_iteration(stage, iteration)
            status = "✅" if result == expected else "❌"
            print(f"  {status} {stage_id} @ iteration {iteration}: skip={result} (期望={expected})")
            if result != expected:
                all_pass = False
        except Exception as e:
            print(f"  ❌ {stage_id} @ iteration {iteration}: 异常 {e}")
            all_pass = False
    
    return all_pass

def test_iteration_execution():
    """测试：迭代执行流程"""
    print("\n" + "=" * 60)
    print("测试 3: 迭代执行流程")
    print("=" * 60)
    
    if not hasattr(PipelineEngine, '_run_iteration_stages'):
        print("  ❌ _run_iteration_stages 方法不存在")
        return False
    
    # 创建 mock engine
    engine = PipelineEngine.__new__(PipelineEngine)
    engine._iteration = 0
    engine._scores = []
    engine._audit_findings = []
    
    # Mock _execute_stage_with_resilience
    def mock_execute(stage):
        return StageResult(
            stage_id=stage.id,
            success=True,
            output={"test": True},
            score=0.85
        )
    
    engine._execute_stage_with_resilience = mock_execute
    
    # 测试 stages
    stages = [
        PipelineStage(id="data_manager", agent="data_manager"),
        PipelineStage(id="auditor", agent="auditor"),
        PipelineStage(id="fixer", agent="fixer"),
    ]
    
    # 第一轮：所有 stages 执行
    result = engine._run_iteration_stages(stages, 0)
    print(f"  ✅ 第一轮执行: success={result}, iterations={engine._iteration}")
    
    # 第二轮：跳过 data_manager
    result = engine._run_iteration_stages(stages, 1)
    print(f"  ✅ 第二轮执行: success={result}, iterations={engine._iteration}")
    
    # 验证 iteration 计数
    if engine._iteration == 5:  # 第一轮3个 + 第二轮2个
        print(f"  ✅ Iteration 计数正确: {engine._iteration}")
        return True
    else:
        print(f"  ❌ Iteration 计数错误: 期望=5, 实际={engine._iteration}")
        return False

def test_convergence_flow():
    """测试：收敛检测流程"""
    print("\n" + "=" * 60)
    print("测试 4: 收敛检测流程")
    print("=" * 60)
    
    # Mock 配置
    mock_domain_config = Mock()
    mock_domain_config.max_iterations = 5
    mock_domain_config.min_iterations = 2
    mock_domain_config.target_score = 0.88
    mock_domain_config.convergence_threshold = 0.02
    
    # Mock pipeline
    mock_pipeline = Mock()
    mock_pipeline.stages = [
        PipelineStage(id="auditor", agent="auditor"),
        PipelineStage(id="fixer", agent="fixer"),
        PipelineStage(id="verifier", agent="verifier"),
    ]
    
    with patch.object(PipelineEngine, '_parse_pipeline_stages', return_value=mock_pipeline):
        with patch.object(PipelineEngine, '_init_data_manager'):
            engine = PipelineEngine(
                domain="investment",
                session_id="test_convergence",
                config={}
            )
            engine._domain_config = mock_domain_config
            engine._pipeline = mock_pipeline
            
            # Mock 方法
            call_count = [0]
            def mock_run_iteration(stages, iteration):
                call_count[0] += 1
                engine._scores.append(0.90)  # 高分
                return True
            
            def mock_check_convergence(target, threshold):
                # 第二轮后收敛
                if call_count[0] >= 2:
                    return True, "score above target"
                return False, "not enough iterations"
            
            engine._run_iteration_stages = mock_run_iteration
            engine._check_convergence_with_quality = mock_check_convergence
            
            result = engine._run_pipeline()
            
            print(f"  ✅ 执行轮次: {call_count[0]}")
            print(f"  ✅ 最终状态: {result.state.name}")
            print(f"  ✅ 迭代计数: {result.iterations}")
            
            if result.state == PipelineState.CONVERGED and call_count[0] >= 2:
                print("  ✅ 收敛检测正确工作")
                return True
            else:
                print("  ❌ 收敛检测未正常工作")
                return False

def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("PipelineEngine 迭代循环修复验证")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("结构检查", test_iteration_structure()))
    except Exception as e:
        print(f"  ❌ 结构检查异常: {e}")
        results.append(("结构检查", False))
    
    try:
        results.append(("跳过逻辑", test_skip_logic()))
    except Exception as e:
        print(f"  ❌ 跳过逻辑异常: {e}")
        results.append(("跳过逻辑", False))
    
    try:
        results.append(("迭代执行", test_iteration_execution()))
    except Exception as e:
        print(f"  ❌ 迭代执行异常: {e}")
        results.append(("迭代执行", False))
    
    try:
        results.append(("收敛流程", test_convergence_flow()))
    except Exception as e:
        print(f"  ❌ 收敛流程异常: {e}")
        results.append(("收敛流程", False))
    
    # 汇总
    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有验证通过！修复完成。")
    else:
        print("⚠️  有验证未通过，需要返工。")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
