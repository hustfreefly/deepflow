#!/usr/bin/env python3
"""
验证 PipelineEngine 单轮模式修复
"""
import sys
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from unittest.mock import Mock, patch
from pipeline_engine import PipelineEngine, PipelineState, PipelineResult

def test_single_pass_mode():
    """测试：max_iterations=1 时返回 DONE 状态"""
    print("=" * 60)
    print("测试 1: 单轮模式 (max_iterations=1)")
    print("=" * 60)
    
    mock_pipeline = Mock()
    mock_pipeline.stages = []
    
    mock_config = Mock()
    mock_config.max_iterations = 1
    mock_config.min_iterations = 1
    mock_config.target_score = 0.88
    mock_config.convergence_threshold = 0.02
    
    with patch.object(PipelineEngine, '_parse_pipeline_stages', return_value=mock_pipeline):
        with patch.object(PipelineEngine, '_init_data_manager'):
            engine = PipelineEngine(
                domain="investment",
                session_id="test_single",
                config={}
            )
            engine._domain_config = mock_config
            engine._pipeline = mock_pipeline
            
            result = engine._run_pipeline()
            
            status = "✅" if result.state == PipelineState.DONE else "❌"
            print(f"  {status} 最终状态: {result.state.name} (期望: DONE)")
            print(f"  ✅ 执行轮次: {result.iterations}")
            
            return result.state == PipelineState.DONE

def test_multi_iteration_mode():
    """测试：max_iterations>1 时保持原有逻辑"""
    print("\n" + "=" * 60)
    print("测试 2: 多轮模式 (max_iterations=5)")
    print("=" * 60)
    
    mock_pipeline = Mock()
    mock_pipeline.stages = []
    
    mock_config = Mock()
    mock_config.max_iterations = 5
    mock_config.min_iterations = 2
    mock_config.target_score = 0.92
    mock_config.convergence_threshold = 0.02
    
    call_count = [0]
    def mock_run_iteration(stages, iteration):
        call_count[0] += 1
        engine._scores.append(0.90)
        return True
    
    def mock_check_convergence(target, threshold):
        if call_count[0] >= 2:
            return True, "score above target"
        return False, "continue"
    
    with patch.object(PipelineEngine, '_parse_pipeline_stages', return_value=mock_pipeline):
        with patch.object(PipelineEngine, '_init_data_manager'):
            engine = PipelineEngine(
                domain="investment",
                session_id="test_multi",
                config={}
            )
            engine._domain_config = mock_config
            engine._pipeline = mock_pipeline
            engine._run_iteration_stages = mock_run_iteration
            engine._check_convergence_with_quality = mock_check_convergence
            
            result = engine._run_pipeline()
            
            status = "✅" if result.state == PipelineState.CONVERGED else "❌"
            print(f"  {status} 最终状态: {result.state.name} (期望: CONVERGED)")
            print(f"  ✅ 执行轮次: {call_count[0]}")
            
            return result.state == PipelineState.CONVERGED

def run_all_tests():
    print("\n" + "=" * 70)
    print("PipelineEngine 单轮模式修复验证")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("单轮模式", test_single_pass_mode()))
    except Exception as e:
        print(f"  ❌ 单轮模式异常: {e}")
        results.append(("单轮模式", False))
    
    try:
        results.append(("多轮模式", test_multi_iteration_mode()))
    except Exception as e:
        print(f"  ❌ 多轮模式异常: {e}")
        results.append(("多轮模式", False))
    
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
