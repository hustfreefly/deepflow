#!/usr/bin/env python3
"""
DeepFlow Pipeline 测试初始化 Agent

任务：启动 Coordinator.start() 并返回初始状态
输入：研究"小米 SU7 市场反响"
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from coordinator import Coordinator
from blackboard_manager import BlackboardManager


async def main():
    user_input = "研究小米 SU7 市场反响"
    print(f"🚀 启动 DeepFlow Pipeline 测试")
    print(f"📝 输入: {user_input}")
    print(f"{'='*60}")

    coord = Coordinator()
    
    try:
        status = await coord.start(user_input)
        
        # 1. 保存状态到 blackboard
        blackboard = BlackboardManager(status.session_id)
        blackboard.write("init_status.json", json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
        blackboard.write("test_init_marker.md", f"# Test Init Marker\n\n- Task: {user_input}\n- Session: {status.session_id}\n- State: {status.state}")
        
        # 2. 保存 Coordinator 状态
        await coord.save_state(status.session_id)
        
        # 3. 输出结果
        print(f"\n✅ Pipeline 启动成功\n")
        print(f"session_id: {status.session_id}")
        print(f"domain: {status.domain}")
        print(f"状态: {status.state}")
        print(f"iteration: {status.iteration}")
        print(f"quality_score: {status.quality_score}")
        print(f"completed_stages: {status.completed_stages}")
        print(f"blackboard_path: {status.blackboard_path}")
        
        if status.pending_requests:
            print(f"\npending_agents ({len(status.pending_requests)}):")
            for req in status.pending_requests:
                print(f"  - [{req['agent_role']}] {req['instance_name']} ({req['angle']})")
                print(f"    request_id: {req['request_id']}")
                print(f"    model: {req['model']}")
                print(f"    timeout: {req['timeout']}s")
        else:
            print(f"\npending_agents: [] (pipeline completed or no agent stages reached yet)")
        
        # 输出 JSON 供上游解析
        result = {
            "session_id": status.session_id,
            "domain": status.domain,
            "state": status.state,
            "iteration": status.iteration,
            "quality_score": status.quality_score,
            "completed_stages": status.completed_stages,
            "pending_agents": [
                {
                    "request_id": r["request_id"],
                    "agent_role": r["agent_role"],
                    "instance_name": r["instance_name"],
                    "angle": r["angle"],
                    "model": r["model"],
                    "timeout": r["timeout"],
                }
                for r in status.pending_requests
            ],
            "blackboard_path": status.blackboard_path,
        }
        print(f"\n{'='*60}")
        print(f"📦 JSON Result:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"\n❌ Pipeline 启动失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 输出失败状态
        result = {
            "session_id": "unknown",
            "pending_agents": [],
            "state": "FAILED",
            "error": str(e),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
