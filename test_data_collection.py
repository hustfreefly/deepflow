#!/usr/bin/env python3
"""
测试 Solution 模块数据采集功能
"""
import sys
import os
import asyncio

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from domains.solution import SolutionOrchestrator

async def test_standard_mode():
    """测试 standard 模式的数据采集"""
    print("\n" + "="*60)
    print("TEST: Standard Mode Data Collection")
    print("="*60)
    
    orch = SolutionOrchestrator({
        "topic": "高并发电商系统",
        "type": "architecture",
        "mode": "standard"
    })
    
    # 验证 _execute_data_collection 方法存在
    assert hasattr(orch, '_execute_data_collection'), "_execute_data_collection 方法不存在"
    print("✅ _execute_data_collection 方法存在")
    
    # 验证 pipeline 包含 data_collection
    stage_names = [s.name for s in orch.domain_config.pipeline]
    assert 'data_collection' in stage_names, f"data_collection 不在 pipeline 中: {stage_names}"
    print(f"✅ Pipeline 包含 data_collection: {stage_names}")
    
    # 验证 quick 模式跳过 data_collection
    print("\n" + "-"*60)
    print("TEST: Quick Mode Skips Data Collection")
    print("-"*60)
    
    orch_quick = SolutionOrchestrator({
        "topic": "高并发电商系统",
        "type": "architecture",
        "mode": "quick"
    })
    
    quick_stage_names = [s.name for s in orch_quick.domain_config.pipeline]
    assert 'data_collection' not in quick_stage_names, f"quick 模式不应包含 data_collection: {quick_stage_names}"
    print(f"✅ Quick mode pipeline (跳过 data_collection): {quick_stage_names}")
    
    # 执行数据采集（仅测试方法调用，不实际执行网络请求）
    print("\n" + "-"*60)
    print("TEST: Execute Data Collection Method")
    print("-"*60)
    
    # 创建一个 mock stage
    from core.orchestrator_base import StageConfig
    
    mock_stage = StageConfig(
        name="data_collection",
        stage_type="custom",
        custom_handler="_execute_data_collection"
    )
    
    result = await orch._execute_data_collection(mock_stage)
    print(f"✅ Data collection result: {result}")
    
    # 验证结果结构
    assert 'success' in result, "结果缺少 success 字段"
    assert 'output' in result, "结果缺少 output 字段"
    
    output = result['output']
    if not output.get('skipped'):
        assert 'datasets' in output, "输出缺少 datasets 字段"
        assert 'count' in output, "输出缺少 count 字段"
        assert 'verification' in output, "输出缺少 verification 字段"
        print(f"✅ Output structure valid: {len(output.get('datasets', []))} datasets")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED ✅")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_standard_mode())
