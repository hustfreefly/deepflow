#!/usr/bin/env python3
"""
端到端测试脚本 - Coordinator Mode D
"""

import asyncio
import sys
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

print('='*60)
print('🚀 端到端测试：Coordinator Mode D (ConfigLoader 修复后)')
print('='*60)

from coordinator import Coordinator, AgentResult

async def test():
    coordinator = Coordinator()
    
    # 第1轮：开始执行
    print('\n📍 Round 1: Coordinator.start()')
    status = await coordinator.start('分析贵州茅台股票')
    
    print(f'  状态: {status.state}')
    print(f'  会话ID: {status.session_id}')
    print(f'  领域: {status.domain}')
    
    round_num = 1
    max_rounds = 10
    
    while not status.is_completed and round_num < max_rounds:
        round_num += 1
        
        if status.is_waiting_agent:
            print(f'\n📍 Round {round_num}: 执行 {len(status.pending_requests)} 个 Agent')
            
            agent_results = []
            for req in status.pending_requests:
                print(f'  🎯 {req["agent_role"]} (stage: {req["stage_id"]})')
                # 模拟 Agent 执行
                result = AgentResult(
                    request_id=req['request_id'],
                    success=True,
                    output_file=f'/tmp/deepflow/{status.session_id}/{req["stage_id"]}.md',
                    score=0.85
                )
                agent_results.append(result)
                print(f'     ✅ 完成')
            
            print(f'\n💉 Coordinator.resume()')
            status = await coordinator.resume(status.session_id, agent_results)
            print(f'  状态: {status.state}')
            
        elif status.state == 'WAITING_HITL':
            print(f'\n⏸️ HITL 暂停')
            break
        else:
            print(f'\n📍 Round {round_num}: 继续执行')
            status = await coordinator._resume_execution(status.session_id)
            print(f'  状态: {status.state}')
    
    print('\n' + '='*60)
    if status.is_completed:
        print('✅ 测试完成！')
        print(f'最终分数: {status.final_result.quality_score:.2%}')
        print(f'总耗时: {status.final_result.elapsed_seconds:.1f}s')
    else:
        print(f'⏹️ 测试中止: {status.state}')
        if status.error:
            print(f'错误: {status.error}')
    print('='*60)
    
    return 0 if status.is_completed else 1

if __name__ == '__main__':
    exit_code = asyncio.run(test())
    sys.exit(exit_code)
