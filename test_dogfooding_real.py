#!/usr/bin/env python3
"""
DeepFlow Solution Domain - Full Dogfooding Test
使用 Solution 模块分析 Solution 模块自身的设计

⚠️  重要：此脚本必须在 OpenClaw Agent Run 环境中执行
    独立 Python 环境无法调用 openclaw 模块
    
执行方式：
    1. 在 OpenClaw 对话中运行：python3 /Users/allen/.openclaw/workspace/.deepflow/test_dogfooding_real.py
    2. 或通过 sessions_spawn 启动子 Agent 执行
"""
import sys
import asyncio
import json
from datetime import datetime
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from domains.solution import SolutionOrchestrator

async def test_dogfooding():
    """
    Dogfooding测试：用Solution模块设计Solution模块
    真实调用模型，无Mock
    """
    context = {
        "topic": "设计一个通用的AI解决方案设计模块，支持软件架构设计、业务解决方案和技术方案",
        "type": "architecture",
        "constraints": [
            "必须适配OpenClaw平台",
            "支持6个Agent并行协作",
            "最大3个Worker同时运行",
            "Pipeline必须在10分钟内完成",
            "支持收敛检测和质量评估"
        ],
        "stakeholders": [
            "DeepFlow开发团队",
            "最终用户（需要方案设计的开发者）",
            "运维团队"
        ]
    }
    
    print("="*70)
    print("DEEPFLOW SOLUTION DOMAIN - REAL DOGFOODING TEST")
    print("="*70)
    print(f"Topic: {context['topic']}")
    print(f"Type: {context['type']}")
    print(f"Constraints: {len(context['constraints'])} items")
    print("="*70)
    
    try:
        orchestrator = SolutionOrchestrator(context)
        print(f"\n✅ Orchestrator initialized")
        print(f"Session ID: {orchestrator.session_id}")
        print(f"Concurrency limit: {orchestrator.concurrency_limit}")
        
        # 执行完整Pipeline
        print("\n" + "="*70)
        print("STARTING PIPELINE EXECUTION")
        print("="*70)
        
        result = await orchestrator.run()
        
        # 输出结果
        print("\n" + "="*70)
        print("PIPELINE COMPLETED")
        print("="*70)
        print(f"State: {result.get('state', 'UNKNOWN')}")
        print(f"Stages completed: {result.get('stages_completed', [])}")
        
        if 'final_score' in result:
            print(f"Final score: {result['final_score']:.2%}")
        if 'iterations' in result:
            print(f"Iterations: {result['iterations']}")
        if 'convergence_reason' in result:
            print(f"Convergence reason: {result['convergence_reason']}")
        
        # 保存完整结果到文件
        output_file = f"/Users/allen/.openclaw/workspace/.deepflow/test_results/solution_dogfooding_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import os
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # 简化输出，避免循环引用
            simplified = {
                "session_id": result.get("session_id"),
                "state": result.get("state"),
                "stages_completed": result.get("stages_completed"),
                "final_score": result.get("final_score"),
                "iterations": result.get("iterations"),
                "convergence_reason": result.get("convergence_reason"),
                "error": result.get("error")
            }
            json.dump(simplified, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Results saved to: {output_file}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    result = asyncio.run(test_dogfooding())
    
    # 最终判断
    if isinstance(result, dict) and result.get("state") in ["CONVERGED", "DONE"]:
        print("\n" + "="*70)
        print("🎉 DOGFOODING TEST PASSED")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("⚠️ DOGFOODING TEST NEEDS ATTENTION")
        print("="*70)
        if isinstance(result, dict):
            print(f"State: {result.get('state', 'UNKNOWN')}")
            if 'error' in result:
                print(f"Error: {result['error']}")
