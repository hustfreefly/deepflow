#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')

from coordinator import Coordinator, ExecutionStatus

async def test():
    print('Testing Coordinator Mode D...')
    coord = Coordinator()
    
    # Test intent parsing
    assert coord._parse_intent('分析 AAPL 股票') == 'investment'
    assert coord._parse_intent('设计微服务架构') == 'architecture'
    print('✅ Intent parsing passed')
    
    # Test ExecutionStatus serialization
    status = ExecutionStatus(
        state='WAITING_AGENT',
        session_id='test_001',
        domain='investment',
        pending_requests=[{'agent_role': 'planner'}],
        completed_stages=['init'],
        iteration=1,
        quality_score=0.85,
    )
    data = status.to_dict()
    restored = ExecutionStatus.from_dict(data)
    assert restored.state == 'WAITING_AGENT'
    print('✅ ExecutionStatus serialization passed')
    
    print('\n🎉 All tests passed!')

if __name__ == '__main__':
    asyncio.run(test())
