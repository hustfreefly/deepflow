#!/usr/bin/env python3
"""ResilienceManager 单元测试套件 - V3.0（修复版）"""

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent))

from resilience_manager import (
    ResilienceManager,
    CircuitBreaker,
    Task,
    Result,
    CircuitState,
)


class TestCircuitBreaker:
    """测试熔断器状态机"""
    
    def test_initial_state(self):
        cb = CircuitBreaker("test_task")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        print("✅ test_initial_state passed")
    
    def test_record_success(self):
        cb = CircuitBreaker("test_task")
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        print("✅ test_record_success passed")
    
    def test_record_failure_open(self):
        cb = CircuitBreaker("test_task", failure_threshold=2)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        print("✅ test_record_failure_open passed")
    
    def test_allow_request(self):
        cb = CircuitBreaker("test_task")
        assert cb.allow_request() == True
        
        # 触发熔断
        for _ in range(cb.failure_threshold):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() == False
        print("✅ test_allow_request passed")
    
    def test_reset(self):
        cb = CircuitBreaker("test_task")
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        print("✅ test_reset passed")


class TestResilienceManager:
    """测试ResilienceManager功能"""
    
    async def test_execute_with_resilience_success(self):
        mgr = ResilienceManager()
        
        async def mock_executor(task: Task) -> Result:
            return Result(success=True, output="success", model_used=task.model)
        
        task = Task(agent_id="test_1", task_prompt="Test prompt", model="default")
        result = await mgr.execute_with_resilience(task, mock_executor)
        
        assert result.success == True
        assert result.output == "success"
        print("✅ test_execute_with_resilience_success passed")
    
    async def test_execute_with_resilience_failure(self):
        mgr = ResilienceManager()
        
        async def fail_executor(task: Task) -> Result:
            raise ValueError("Test error")
        
        task = Task(agent_id="test_2", task_prompt="Test prompt", model="default")
        result = await mgr.execute_with_resilience(task, fail_executor)
        
        assert result.success == False
        assert "Test error" in result.error
        print("✅ test_execute_with_resilience_failure passed")
    
    async def test_execute_with_resilience_retry(self):
        mgr = ResilienceManager()
        
        call_count = 0
        async def retry_executor(task: Task) -> Result:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError(f"Attempt {call_count} failed")
            return Result(success=True, output=f"Success on attempt {call_count}")
        
        task = Task(agent_id="test_3", task_prompt="Test prompt", model="default")
        result = await mgr.execute_with_resilience(task, retry_executor)
        
        assert result.success == True
        assert call_count == 2  # 重试1次后成功
        print(f"✅ test_execute_with_resilience_retry passed (retried {call_count} times)")
    
    async def test_circuit_breaker_isolation(self):
        mgr = ResilienceManager()
        
        # Task A 连续失败
        async def fail_executor(task: Task) -> Result:
            raise ValueError("Always fails")
        
        for _ in range(5):
            task_a = Task(agent_id="task_a", task_prompt="Test", model="default")
            await mgr.execute_with_resilience(task_a, fail_executor)
        
        # Task A 应该熔断
        assert mgr.is_circuit_open("task_a") == True
        
        # Task B 应该不受影响
        async def success_executor(task: Task) -> Result:
            return Result(success=True)
        
        task_b = Task(agent_id="task_b", task_prompt="Test", model="default")
        result_b = await mgr.execute_with_resilience(task_b, success_executor)
        
        assert result_b.success == True
        print("✅ test_circuit_breaker_isolation passed")
    
    async def test_checkpoint_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ResilienceManager({"checkpoint_dir": tmpdir})
            
            # 保存检查点
            test_state = {"iteration": 5, "score": 0.85}
            mgr.save_checkpoint("test_stage", test_state)
            
            # 加载检查点
            restored = mgr.load_checkpoint("test_stage")
            assert restored == test_state
            print("✅ test_checkpoint_save_load passed")
    
    async def test_rollback_to_safe_state(self):
        mgr = ResilienceManager()
        
        # 保存几个状态
        mgr.save_safe_state({"data": 1})
        mgr.save_safe_state({"data": 2})
        mgr.save_safe_state({"data": 3})
        
        # 回滚
        result = mgr.rollback_to_safe_state()
        assert result == {"data": 3}
        
        result2 = mgr.rollback_to_safe_state()
        assert result2 == {"data": 2}
        print("✅ test_rollback_to_safe_state passed")
    
    async def test_degradation(self):
        mgr = ResilienceManager({"enable_degradation": True})
        
        call_count = 0
        async def fail_then_degrade(task: Task) -> Result:
            nonlocal call_count
            call_count += 1
            if task.model == "default":
                raise ValueError("Primary model failed")
            return Result(success=True, output="degraded result", model_used=task.model)
        
        task = Task(
            agent_id="test_degrade",
            task_prompt="Test",
            model="default",
            fallback_model="lightweight"
        )
        result = await mgr.execute_with_resilience(task, fail_then_degrade)
        
        assert result.success == True
        assert result.degraded == True
        assert result.model_used == "lightweight"
        print("✅ test_degradation passed")
    
    def test_get_stats(self):
        mgr = ResilienceManager()
        stats = mgr.get_resilience_stats()
        
        assert "total_executions" in stats
        assert "circuit_breakers" in stats
        assert "checkpoints" in stats
        print("✅ test_get_stats passed")


async def run_all_tests():
    """运行所有测试"""
    print("\n=== ResilienceManager 测试套件（修复版）===\n")
    
    # CircuitBreaker测试
    print("--- CircuitBreaker 测试 ---")
    cb_tests = TestCircuitBreaker()
    cb_tests.test_initial_state()
    cb_tests.test_record_success()
    cb_tests.test_record_failure_open()
    cb_tests.test_allow_request()
    cb_tests.test_reset()
    
    # ResilienceManager测试
    print("\n--- ResilienceManager 测试 ---")
    mgr_tests = TestResilienceManager()
    await mgr_tests.test_execute_with_resilience_success()
    await mgr_tests.test_execute_with_resilience_failure()
    await mgr_tests.test_execute_with_resilience_retry()
    await mgr_tests.test_circuit_breaker_isolation()
    await mgr_tests.test_checkpoint_save_load()
    await mgr_tests.test_rollback_to_safe_state()
    await mgr_tests.test_degradation()
    mgr_tests.test_get_stats()
    
    print("\n=== 🎉 所有测试通过！===\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
