#!/usr/bin/env python3
"""
测试 LLM Gate 集成

验证三层架构是否正确集成：
1. Layer 1: 确定性检查（gates.py）
2. Layer 2: LLM 语义检查（llm_gate_checks.py）
3. Layer 3: 合并结果（merge_gate_results）

测试数据：使用 V2 的 architect 输出（包含 principles）
"""

import sys
import json
from pathlib import Path

# 添加 .deepflow 到路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domains.ship_pro.eval.gates import gate_architect
from domains.ship_pro.eval.llm_gate_checks import (
    llm_check_architect_quality,
    merge_gate_results,
)
from domains.ship_pro.eval.llm_caller import create_llm_caller, set_default_caller


def test_layer1_deterministic():
    """测试 Layer 1: 确定性检查"""
    print("=" * 60)
    print("Layer 1: 确定性检查")
    print("=" * 60)
    
    # 加载 V2 architect 输出
    v2_path = Path("/Users/allen/.openclaw/workspace/.deepflow/projects/OpenClaw_AI_Native_L_architecture_v2/ship_output/blackboard/architect")
    if not v2_path.exists():
        print("❌ V2 architect 输出不存在")
        return False
    
    with open(v2_path) as f:
        architect_output = json.load(f)
    
    # 运行确定性检查
    result = gate_architect(architect_output)
    
    print(f"Decision: {result['decision']}")
    print(f"Critical checks: {result.get('critical_results', {})}")
    print(f"Major checks: {result.get('major_results', {})}")
    print(f"Feedback: {result.get('feedback', '')[:200]}")
    print()
    
    return result['decision'] in ('PASS', 'CONDITIONAL')


def test_layer2_llm_semantic():
    """测试 Layer 2: LLM 语义检查"""
    print("=" * 60)
    print("Layer 2: LLM 语义检查")
    print("=" * 60)
    
    # 加载 V2 architect 输出
    v2_path = Path("/Users/allen/.openclaw/workspace/.deepflow/projects/OpenClaw_AI_Native_L_architecture_v2/ship_output/blackboard/architect")
    if not v2_path.exists():
        print("❌ V2 architect 输出不存在")
        return False
    
    with open(v2_path) as f:
        architect_output = json.load(f)
    
    # 加载 principles
    principles = architect_output.get("architecture_principles", [])
    if not principles:
        print("⚠️  V2 architect 输出中没有 principles，跳过 LLM 检查")
        return True
    
    print(f"Principles 数量: {len(principles)}")
    for p in principles[:3]:
        print(f"  - {p['id']}: {p['name']}")
    print()
    
    # 初始化 LLM caller
    print("初始化 LLM caller...")
    caller = create_llm_caller(model="qwen3.7-max")
    set_default_caller(caller)
    
    # 运行 LLM 语义检查
    print("调用 LLM 进行语义检查...")
    semantic_result = llm_check_architect_quality(architect_output, principles)
    
    print(f"Decision: {semantic_result['decision']}")
    print(f"Issues: {len(semantic_result.get('issues', []))}")
    
    for issue in semantic_result.get('issues', [])[:3]:
        print(f"  - [{issue['severity']}] {issue['type']}: {issue['description'][:100]}")
    
    print(f"Reasoning: {semantic_result.get('reasoning', '')[:200]}")
    print()
    
    return True


def test_layer3_merge():
    """测试 Layer 3: 合并结果"""
    print("=" * 60)
    print("Layer 3: 合并结果")
    print("=" * 60)
    
    # 模拟确定性检查结果
    deterministic = {
        "passed": True,
        "decision": "PASS",
        "critical_results": {
            "modules_non_empty": True,
            "dependencies_acyclic": True,
            "requirements_non_empty": True,
        },
        "major_results": {},
        "minor_results": {},
        "feedback": "确定性检查通过"
    }
    
    # 模拟 LLM 语义检查结果（包含问题）
    semantic = {
        "decision": "FAIL",
        "issues": [
            {
                "type": "principle_violation",
                "severity": "BLOCKER",
                "description": "COMP-001 的 tech stack 包含'令牌桶限流'，违反'全 LLM 控制'原则",
                "affected_modules": ["COMP-001"],
                "suggestion": "将令牌桶限流改为 LLM 驱动的限流策略"
            }
        ],
        "reasoning": "COMP-001 使用确定性逻辑，不符合全 LLM 控制原则"
    }
    
    # 合并
    merged = merge_gate_results(deterministic, semantic)
    
    print(f"确定性决策: {deterministic['decision']}")
    print(f"语义决策: {semantic['decision']}")
    print(f"合并后决策: {merged['decision']}")
    print(f"合并后 feedback: {merged['feedback'][:200]}")
    print(f"LLM issues: {len(merged.get('llm_issues', []))}")
    print()
    
    # 验证：任一为 FAIL → FAIL
    assert merged['decision'] == 'FAIL', "合并逻辑错误：任一为 FAIL 应该导致 FAIL"
    
    return True


def test_full_integration():
    """测试完整集成（通过 run_pipeline.py check_gate）"""
    print("=" * 60)
    print("完整集成测试（check_gate）")
    print("=" * 60)
    
    # 使用 V2 的 output_dir
    output_dir = "/Users/allen/.openclaw/workspace/.deepflow/projects/OpenClaw_AI_Native_L_architecture_v2/ship_output"
    
    if not Path(output_dir).exists():
        print("❌ V2 output_dir 不存在")
        return False
    
    # 导入 check_gate
    from domains.ship_pro.scripts.run_pipeline import check_gate
    
    # 初始化 LLM caller
    print("初始化 LLM caller...")
    caller = create_llm_caller(model="qwen3.7-max")
    set_default_caller(caller)
    
    # 运行 check_gate
    print("运行 check_gate('architect', output_dir)...")
    result = check_gate("architect", output_dir)
    
    print(f"Agent: {result['agent']}")
    print(f"Decision: {result['decision']}")
    print(f"Critical failures: {result['critical_failures']}")
    print(f"Feedback: {result['feedback'][:200]}")
    
    # 检查是否包含 LLM issues
    if 'llm_issues' in result.get('gate_results', {}):
        llm_issues = result['gate_results']['llm_issues']
        print(f"LLM issues: {len(llm_issues)}")
        for issue in llm_issues[:3]:
            print(f"  - [{issue['severity']}] {issue['type']}: {issue['description'][:100]}")
    print()
    
    return True


def main():
    """运行所有测试"""
    print("\n")
    print("🧪 LLM Gate 集成测试")
    print("=" * 60)
    print()
    
    tests = [
        ("Layer 1: 确定性检查", test_layer1_deterministic),
        ("Layer 2: LLM 语义检查", test_layer2_llm_semantic),
        ("Layer 3: 合并结果", test_layer3_merge),
        ("完整集成", test_full_integration),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success))
            if success:
                print(f"✅ {name}: PASS")
            else:
                print(f"❌ {name}: FAIL")
        except Exception as e:
            print(f"❌ {name}: ERROR - {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
        print()
    
    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, s in results if s)
    print()
    print(f"总计: {passed}/{total} 通过")
    
    return all(s for _, s in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
