#!/usr/bin/env python3
"""
Simple test for Solution Domain
"""
import sys
import asyncio
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from domains.solution import SolutionOrchestrator

async def test_simple():
    """Test with a simple architecture design task"""
    context = {
        "topic": "设计一个个人博客系统",
        "type": "architecture",
        "constraints": ["低成本", "易维护"],
        "stakeholders": ["个人开发者"]
    }
    
    print("="*60)
    print("SOLUTION DOMAIN TEST - Personal Blog System")
    print("="*60)
    
    orchestrator = SolutionOrchestrator(context)
    
    print(f"\nConfig loaded: {orchestrator.domain_config.name}")
    print(f"Pipeline stages: {[s.name for s in orchestrator.domain_config.pipeline]}")
    print(f"Convergence: max={orchestrator.domain_config.convergence.max_iterations}, target={orchestrator.domain_config.convergence.target_score}")
    
    # Note: Full run would take ~10-15 minutes, so we just test initialization
    print("\n✅ Initialization successful!")
    print(f"Session ID: {orchestrator.session_id}")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_simple())
