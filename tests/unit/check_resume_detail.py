#!/usr/bin/env python3
"""
验证脚本: Pipeline Resume 机制诊断（详细版）
显示每个 stage 的执行详情
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from coordinator import Coordinator, AgentResult


async def diagnose_with_details():
    """详细诊断"""
    print("="*70)
    print("Pipeline Resume 详细诊断")
    print("="*70)
    
    # 清理旧 session
    import shutil
    bb_dir = Path("/Users/allen/.openclaw/workspace/.v3/blackboard/diagnose-detail-001")
    if bb_dir.exists():
        shutil.rmtree(bb_dir)
    
    session_id = "diagnose-detail-001"
    coord = Coordinator()
    
    # Step 1: start
    print("\n[Step 1] start()...")
    status = await coord.start("测试", session_id=session_id)
    print(f"  → {status.state} | pending: {len(status.pending_requests)}")
    
    if status.state != "WAITING_AGENT":
        print(f"✗ start() 未进入 WAITING_AGENT")
        return False
    
    req = status.pending_requests[0]
    request_id = req.get('request_id')
    print(f"  → request_id: {request_id}")
    
    # Step 2: save
    await coord.save_state(session_id)
    
    # Step 3: resume with mock result
    print(f"\n[Step 2] resume() with result...")
    coord2 = await Coordinator.from_saved(session_id)
    
    result = AgentResult(
        request_id=request_id,
        success=True,
        output_file=f"/tmp/{session_id}_plan.md",
        score=0.85
    )
    
    # 捕获所有日志输出
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    
    status2 = await coord2.resume(session_id, [result])
    
    print(f"\n[Result]")
    print(f"  → state: {status2.state}")
    print(f"  → iteration: {status2.iteration}")
    print(f"  → completed_stages: {status2.completed_stages}")
    print(f"  → pending_requests: {len(status2.pending_requests)}")
    print(f"  → error: {status2.error}")
    print(f"  → quality_score: {status2.quality_score}")
    
    # 检查 blackboard 文件
    print(f"\n[Blackboard files]")
    if bb_dir.exists():
        for f in bb_dir.iterdir():
            print(f"  - {f.name}")
    
    # 判断是否成功
    success = status2.state == "WAITING_AGENT" and len(status2.pending_requests) > 0
    
    print(f"\n{'='*70}")
    if success:
        print("✓ PASS: resume 正确进入 WAITING_AGENT 且有 pending requests")
    else:
        print(f"✗ FAIL: resume 后状态为 {status2.state}")
        print(f"\n可能原因分析:")
        if status2.state == "FAILED":
            print(f"  1. Pipeline 执行中某 stage 失败")
            print(f"  2. 所有 stage 执行完毕但 success=False")
        elif status2.state == "COMPLETED":
            print(f"  - Pipeline 直接完成（无中间暂停）")
        elif status2.state == "WAITING_HITL":
            print(f"  - 遇到 HITL gate（配置问题）")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(diagnose_with_details())
    sys.exit(0 if result else 1)
