#!/usr/bin/env python3
"""
验证脚本: Pipeline Resume 暂停机制
详细诊断 resume 后为什么不进入 WAITING_AGENT
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coordinator import Coordinator, AgentResult


async def diagnose_resume_issue():
    """详细诊断 resume 问题"""
    print("="*70)
    print("Pipeline Resume 机制诊断")
    print("="*70)
    
    session_id = "diagnose-resume-001"
    coord = Coordinator()
    
    # Step 1: start
    print("\n[Step 1] 调用 start()...")
    try:
        status = await coord.start(
            user_input="测试 Hermes 架构分析",
            session_id=session_id
        )
        print(f"  → 状态: {status.state}")
        print(f"  → Pending: {len(status.pending_requests)}")
        
        if status.pending_requests:
            req = status.pending_requests[0]
            print(f"  → Request: {req.get('agent_role')} / {req.get('stage_id')}")
    except Exception as e:
        print(f"  ✗ start() 失败: {e}")
        return False
    
    if status.state != "WAITING_AGENT":
        print(f"\n  ✗ start() 后不是 WAITING_AGENT，无法继续诊断")
        return False
    
    # Step 2: save state
    print("\n[Step 2] 保存状态...")
    saved = await coord.save_state(session_id)
    print(f"  → 保存: {'成功' if saved else '失败'}")
    
    # Step 3: 模拟 agent 执行完成，resume
    print("\n[Step 3] 从保存状态恢复并 resume...")
    coord2 = await Coordinator.from_saved(session_id)
    if not coord2:
        print(f"  ✗ 无法恢复状态")
        return False
    print(f"  → 状态恢复成功")
    
    # 构造 agent result
    request_id = status.pending_requests[0].get('request_id', 'unknown')
    print(f"  → 准备注入结果: {request_id}")
    
    result = AgentResult(
        request_id=request_id,
        success=True,
        output_file=f"/tmp/{session_id}_plan.md",
        score=0.85
    )
    
    print(f"\n[Step 4] 调用 resume()...")
    try:
        status2 = await coord2.resume(session_id, [result])
        print(f"  → Resume 后状态: {status2.state}")
        print(f"  → 迭代: {status2.iteration}")
        print(f"  → 完成阶段: {status2.completed_stages}")
        print(f"  → Pending: {len(status2.pending_requests)}")
        print(f"  → 错误: {status2.error}")
        
        if status2.pending_requests:
            for i, req in enumerate(status2.pending_requests, 1):
                print(f"    {i}. {req.get('agent_role')} / {req.get('stage_id')} / {req.get('angle', 'default')}")
        
    except Exception as e:
        print(f"  ✗ resume() 异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 分析结果
    print("\n" + "="*70)
    print("诊断结果")
    print("="*70)
    
    if status2.state == "WAITING_AGENT":
        print("✓ PASS: resume 后正确进入 WAITING_AGENT")
        return True
    elif status2.state == "FAILED":
        print("✗ FAIL: resume 后返回 FAILED")
        print(f"\n可能原因:")
        print(f"  1. callback 未正确抛出 AgentPendingException")
        print(f"  2. 异常被 Pipeline 捕获后转为 FAILED")
        print(f"  3. stage 配置错误（如 agent 未定义）")
        return False
    else:
        print(f"? UNEXPECTED: resume 后状态为 {status2.state}")
        return False


if __name__ == "__main__":
    result = asyncio.run(diagnose_resume_issue())
    sys.exit(0 if result else 1)
