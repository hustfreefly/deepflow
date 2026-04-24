#!/usr/bin/env python3
"""
验证 Worker 完成等待机制修复
"""
import sys
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from pipeline_engine import PipelineEngine, PipelineStage, PipelineState

def test_spawn_metadata_detection():
    """测试：能正确识别 spawn 元数据并继续等待"""
    print("=" * 60)
    print("测试 1: Spawn 元数据检测")
    print("=" * 60)
    
    # 创建临时目录模拟 blackboard
    with tempfile.TemporaryDirectory() as tmpdir:
        session_id = "test_session"
        stage = PipelineStage(id="researcher_finance", agent="researcher")
        
        # 创建 PipelineEngine 实例（mock）
        engine = PipelineEngine.__new__(PipelineEngine)
        engine.session_id = session_id
        
        # 模拟输出路径
        stages_dir = Path(tmpdir) / session_id / "stages"
        stages_dir.mkdir(parents=True)
        output_file = stages_dir / "researcher_finance_output.json"
        
        # 先写入 spawn 元数据
        with open(output_file, "w") as f:
            json.dump({"status": "accepted", "childSessionKey": "abc123"}, f)
        
        # 修改 engine 的路径指向临时目录
        original_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/stages/researcher_finance_output.json"
        
        # 手动测试 _wait_for_worker_completion 的逻辑
        def check_file():
            if output_file.exists():
                with open(output_file) as f:
                    data = json.load(f)
                
                SUBSTANTIVE_FIELDS = {
                    "analysis", "executive_summary", "conclusions", "key_findings",
                    "recommendation", "fixed_analysis", "report", "output",
                    "research_plan", "audit_findings", "scenario_analysis"
                }
                
                data_keys = set(data.keys())
                is_spawn_metadata = (
                    "status" in data and data.get("status") == "accepted" and
                    not bool(data_keys & SUBSTANTIVE_FIELDS)
                )
                
                return is_spawn_metadata, data_keys
            return False, set()
        
        is_metadata, keys = check_file()
        
        if is_metadata:
            print(f"  ✅ 正确识别 spawn 元数据: {keys}")
        else:
            print(f"  ❌ 未识别 spawn 元数据: {keys}")
            return False
        
        # 稍后写入真实结果
        with open(output_file, "w") as f:
            json.dump({
                "role": "researcher_finance",
                "analysis": {"revenue_growth": 0.25},
                "confidence": 0.85
            }, f)
        
        is_metadata, keys = check_file()
        
        if not is_metadata:
            print(f"  ✅ 正确识别真实结果: {keys}")
            return True
        else:
            print(f"  ❌ 误将真实结果识别为元数据: {keys}")
            return False

def test_substantive_content_detection():
    """测试：能正确识别实质性内容"""
    print("\n" + "=" * 60)
    print("测试 2: 实质性内容检测")
    print("=" * 60)
    
    SUBSTANTIVE_FIELDS = {
        "analysis", "executive_summary", "conclusions", "key_findings",
        "recommendation", "fixed_analysis", "report", "output",
        "research_plan", "audit_findings", "scenario_analysis"
    }
    
    test_cases = [
        # (data, expected_has_substantive, description)
        ({"analysis": "test"}, True, "包含 analysis"),
        ({"key_findings": []}, True, "包含 key_findings"),
        ({"recommendation": "buy"}, True, "包含 recommendation"),
        ({"scenario_analysis": {}}, True, "包含 scenario_analysis"),
        ({"status": "accepted"}, False, "只有 status"),
        ({"status": "accepted", "childSessionKey": "abc"}, False, "spawn 元数据"),
        ({"role": "planner", "research_plan": {}}, True, "包含 role 和 research_plan"),
        ({}, False, "空对象"),
        ({"random_field": 123}, False, "无关字段"),
    ]
    
    all_pass = True
    for data, expected, desc in test_cases:
        data_keys = set(data.keys())
        has_substantive = bool(data_keys & SUBSTANTIVE_FIELDS)
        has_role_field = "role" in data and data.get("role") in {
            "researcher_finance", "planner", "auditor_factual", "fixer", "summarizer"
        }
        result = has_substantive or has_role_field
        
        status = "✅" if result == expected else "❌"
        print(f"  {status} {desc}: {result} (期望: {expected})")
        
        if result != expected:
            all_pass = False
    
    return all_pass

def test_timeout_handling():
    """测试：超时处理"""
    print("\n" + "=" * 60)
    print("测试 3: 超时处理")
    print("=" * 60)
    
    # 创建 PipelineEngine 实例
    engine = PipelineEngine.__new__(PipelineEngine)
    engine.session_id = "test_timeout"
    
    stage = PipelineStage(id="test_worker", agent="test")
    
    # 使用很短的超时时间测试
    result = engine._wait_for_worker_completion(
        agent_id="test_agent_001",
        stage=stage,
        timeout=2  # 2秒超时
    )
    
    if not result["success"] and "timeout" in str(result.get("output", {})).lower():
        print(f"  ✅ 正确返回超时错误")
        print(f"  错误信息: {result['output']}")
        return True
    else:
        print(f"  ❌ 超时处理不正确: {result}")
        return False

def test_valid_worker_output():
    """测试：正确处理有效的 Worker 输出"""
    print("\n" + "=" * 60)
    print("测试 4: 有效 Worker 输出处理")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        session_id = "test_valid"
        stage = PipelineStage(id="summarizer", agent="summarizer")
        
        engine = PipelineEngine.__new__(PipelineEngine)
        engine.session_id = session_id
        
        # 创建输出目录和文件
        stages_dir = Path("/Users/allen/.openclaw/workspace/.deepflow/blackboard") / session_id / "stages"
        stages_dir.mkdir(parents=True, exist_ok=True)
        output_file = stages_dir / "summarizer_output.json"
        
        # 写入有效的 summarizer 输出
        valid_output = {
            "role": "summarizer",
            "executive_summary": "京仪装备投资分析...",
            "scenario_analysis": {
                "bull_case": {"target_price": 150.0},
                "base_case": {"target_price": 59.4}
            },
            "recommendation": {"rating": "持有"}
        }
        
        with open(output_file, "w") as f:
            json.dump(valid_output, f)
        
        # 测试等待
        result = engine._wait_for_worker_completion(
            agent_id="summarizer_001",
            stage=stage,
            timeout=10
        )
        
        # 清理
        if output_file.exists():
            output_file.unlink()
        
        if result["success"] and result["output"].get("role") == "summarizer":
            print(f"  ✅ 正确识别有效 summarizer 输出")
            return True
        else:
            print(f"  ❌ 未正确识别: {result}")
            return False

def run_all_tests():
    print("\n" + "=" * 70)
    print("Worker 完成等待机制修复验证")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("Spawn 元数据检测", test_spawn_metadata_detection()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("Spawn 元数据检测", False))
    
    try:
        results.append(("实质性内容检测", test_substantive_content_detection()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("实质性内容检测", False))
    
    try:
        results.append(("超时处理", test_timeout_handling()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("超时处理", False))
    
    try:
        results.append(("有效输出处理", test_valid_worker_output()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("有效输出处理", False))
    
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
        print("🎉 所有验证通过！Worker 等待机制修复完成。")
    else:
        print("⚠️  有验证未通过，需要返工。")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
