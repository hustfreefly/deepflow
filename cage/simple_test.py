#!/usr/bin/env python3
"""
简单测试 - 直接调用 SolutionOrchestrator
"""

import sys
import os
import asyncio
import json
from datetime import datetime

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from domains.solution import SolutionOrchestrator

async def main():
    print("=" * 80)
    print("Solution Real E2E Test - Starting")
    print("=" * 80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    start_time = datetime.now()
    
    test_case = {
        "topic": "设计一个支持百万日订单的电商订单系统",
        "type": "architecture",
        "mode": "standard",
        "constraints": ["日均百万订单", "99.99%可用性", "<200ms响应时间"],
        "stakeholders": ["技术团队", "产品团队", "运维团队"]
    }
    
    print("Test case:")
    print(json.dumps(test_case, indent=2, ensure_ascii=False))
    print()
    
    try:
        orchestrator = SolutionOrchestrator(test_case)
        result = await orchestrator.run()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print()
        print("=" * 80)
        print("Test Completed Successfully")
        print("=" * 80)
        print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
        print()
        print(f"Pipeline state: {result.get('state', 'UNKNOWN')}")
        print(f"Final score: {result.get('final_score', 'N/A')}")
        print(f"Convergence reason: {result.get('convergence_reason', 'N/A')}")
        print(f"Blackboard path: {result.get('blackboard_path', 'N/A')}")
        
        # Save result
        report = {
            "success": True,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "result": result
        }
        
        with open('/Users/allen/.openclaw/workspace/.deepflow/cage/test_result.json', 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print()
        print("Result saved to: /Users/allen/.openclaw/workspace/.deepflow/cage/test_result.json")
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print()
        print("=" * 80)
        print("Test Failed")
        print("=" * 80)
        print(f"Error: {type(e).__name__}: {e}")
        
        import traceback
        traceback.print_exc()
        
        report = {
            "success": False,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        
        with open('/Users/allen/.openclaw/workspace/.deepflow/cage/test_result.json', 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        raise

if __name__ == "__main__":
    asyncio.run(main())
