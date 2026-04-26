#!/usr/bin/env python3
"""
Solution 模块真实端到端测试
测试用例：设计一个支持百万日订单的电商订单系统
"""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domains.solution import SolutionOrchestrator
import asyncio


async def run_test():
    """执行完整 Solution pipeline 测试"""
    
    # 测试配置
    context = {
        "topic": "设计一个支持百万日订单的电商订单系统",
        "type": "architecture",
        "mode": "standard",
        "constraints": ["日均百万订单", "99.99%可用性", "<200ms响应时间"],
        "stakeholders": ["技术团队", "产品团队", "运维团队"]
    }
    
    print("=" * 80)
    print("Solution 模块 - 真实端到端测试")
    print("=" * 80)
    print(f"测试主题: {context['topic']}")
    print(f"方案类型: {context['type']}")
    print(f"运行模式: {context['mode']}")
    print(f"约束条件: {', '.join(context['constraints'])}")
    print(f"利益相关者: {', '.join(context['stakeholders'])}")
    print("=" * 80)
    
    start_time = time.time()
    
    try:
        # Step 1: 创建 Orchestrator
        print("\n[Step 1] 创建 SolutionOrchestrator...")
        orch = SolutionOrchestrator(context)
        print(f"✓ Session ID: {orch.session_id}")
        print(f"✓ Pipeline 阶段: {[s.name for s in orch.domain_config.pipeline]}")
        print(f"✓ Blackboard 目录: {orch.blackboard_dir}")
        
        # Step 2: 运行 Pipeline
        print("\n[Step 2] 开始执行 Pipeline...")
        print("-" * 80)
        
        # 添加进度回调
        async def progress_callback(stage_name, status, message):
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] [{stage_name}] {status}: {message}")
        
        orch.progress_callback = progress_callback
        
        result = await orch.run()
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        print("-" * 80)
        print("\n[Step 3] Pipeline 执行完成")
        
        # Step 3: 记录结果
        print("\n" + "=" * 80)
        print("测试结果报告")
        print("=" * 80)
        
        print(f"\n1. 执行时间: {elapsed:.2f} 秒 ({elapsed/60:.2f} 分钟)")
        
        print(f"\n2. Pipeline 最终状态:")
        print(f"   - 状态: {result.state.value if hasattr(result.state, 'value') else result.state}")
        print(f"   - 收敛原因: {getattr(result, 'convergence_reason', 'N/A')}")
        
        print(f"\n3. 最终分数:")
        print(f"   - 总分: {result.score}")
        if hasattr(result, 'quality_scores'):
            print(f"   - 质量维度得分: {result.quality_scores}")
        
        print(f"\n4. 各阶段完成情况:")
        if hasattr(result, 'stage_results'):
            for stage_name, stage_data in result.stage_results.items():
                status = stage_data.get('status', 'unknown')
                duration = stage_data.get('duration', 0)
                print(f"   - {stage_name}: {status} ({duration:.1f}s)")
        
        print(f"\n5. 产出文件列表:")
        blackboard_dir = orch.blackboard_dir
        if os.path.exists(blackboard_dir):
            for root, dirs, files in os.walk(blackboard_dir):
                level = root.replace(blackboard_dir, '').count(os.sep)
                indent = '     ' * level
                print(f'{indent}{os.path.basename(root)}/')
                subindent = '     ' * (level + 1)
                for file in sorted(files):
                    filepath = os.path.join(root, file)
                    size = os.path.getsize(filepath)
                    print(f'{subindent}{file} ({size:,} bytes)')
        else:
            print("   ⚠ Blackboard 目录不存在")
        
        print(f"\n6. 产出质量评估:")
        if hasattr(result, 'quality_assessment'):
            print(f"   {result.quality_assessment}")
        else:
            print("   未提供质量评估信息")
        
        print(f"\n7. 遇到的问题:")
        if hasattr(result, 'errors') and result.errors:
            for error in result.errors:
                print(f"   ✗ {error}")
        else:
            print("   ✓ 无错误")
        
        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)
        
        return result
        
    except Exception as e:
        end_time = time.time()
        elapsed = end_time - start_time
        
        print(f"\n✗ 测试失败: {type(e).__name__}: {e}")
        print(f"执行时间: {elapsed:.2f} 秒")
        
        import traceback
        traceback.print_exc()
        
        return None


if __name__ == "__main__":
    result = asyncio.run(run_test())
    
    # 保存测试结果
    test_result = {
        "test_name": "solution_e2e_test",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "context": {
            "topic": "设计一个支持百万日订单的电商订单系统",
            "type": "architecture",
            "mode": "standard"
        },
        "success": result is not None,
        "result_summary": {
            "state": str(result.state.value) if result and hasattr(result, 'state') else None,
            "score": result.score if result else None,
        } if result else None
    }
    
    result_file = "/Users/allen/.openclaw/workspace/.deepflow/test_results/solution_e2e_test.json"
    os.makedirs(os.path.dirname(result_file), exist_ok=True)
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试结果已保存到: {result_file}")
