"""
ResilienceManager 契约测试

验证契约中定义的所有接口和边界条件。
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from resilience_manager import (
    CircuitBreaker,
    ErrorCategory,
    ErrorClassifier,
    ResilienceManager,
    Result,
)


class TestErrorClassifier:
    """测试错误分类器"""

    def test_classify_recoverable_errors(self):
        """测试可恢复错误分类"""
        rm = ResilienceManager()
        assert rm.classify_error(TimeoutError()) == ErrorCategory.RECOVERABLE
        assert rm.classify_error(ConnectionError()) == ErrorCategory.RECOVERABLE
        assert rm.classify_error(OSError()) == ErrorCategory.RECOVERABLE

    def test_classify_critical_errors(self):
        """测试严重错误分类"""
        rm = ResilienceManager()
        assert rm.classify_error(ValueError()) == ErrorCategory.CRITICAL
        assert rm.classify_error(TypeError()) == ErrorCategory.CRITICAL
        assert rm.classify_error(KeyError("key")) == ErrorCategory.CRITICAL

    def test_classify_unknown_errors(self):
        """测试未知错误分类"""
        rm = ResilienceManager()
        assert rm.classify_error(RuntimeError()) == ErrorCategory.UNKNOWN
        assert rm.classify_error(Exception()) == ErrorCategory.UNKNOWN


class TestCircuitBreaker:
    """测试熔断器"""

    def test_initial_state_closed(self):
        """测试初始状态为CLOSED"""
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_record_failure_opens_circuit(self):
        """测试连续失败打开熔断器"""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is True  # 未达阈值
        cb.record_failure()
        assert cb.allow_request() is False  # 已打开

    def test_record_success_resets_circuit(self):
        """测试成功重置熔断器"""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False
        cb.record_success()
        assert cb.allow_request() is True

    def test_half_open_after_timeout(self):
        """测试超时后进入半开状态"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.allow_request() is False
        time.sleep(0.2)
        assert cb.allow_request() is True  # HALF_OPEN


class TestResilienceManager:
    """测试韧性管理器"""

    def test_init_with_config(self):
        """测试带配置初始化"""
        config = {"circuit_failure_threshold": 3}
        rm = ResilienceManager(config)
        assert rm._config == config

    def test_init_without_config(self):
        """测试无配置初始化"""
        rm = ResilienceManager()
        assert rm._config == {}

    def test_get_error_classifier(self):
        """测试获取错误分类器"""
        rm = ResilienceManager()
        classifier = rm.get_error_classifier()
        assert isinstance(classifier, ErrorClassifier)


class TestRetryMechanism:
    """测试重试机制"""

    def test_successful_task_no_retry(self):
        """测试成功任务不重试"""
        rm = ResilienceManager()
        task = lambda: Result(success=True, output="ok")
        result = rm.execute_with_retry(task, max_retries=2)
        assert result.success is True
        assert result.output == "ok"

    def test_failed_task_retries_exhausted(self):
        """测试失败任务重试耗尽"""
        rm = ResilienceManager()
        task = lambda: Result(success=False, error="fail")
        result = rm.execute_with_retry(task, max_retries=1)
        assert result.success is False
        assert "Failed after" in result.error

    def test_task_raises_exception(self):
        """测试任务抛出异常"""
        rm = ResilienceManager()

        def failing_task():
            raise TimeoutError("timeout")

        result = rm.execute_with_retry(failing_task, max_retries=0)
        assert result.success is False
        assert "timeout" in result.error

    def test_negative_max_retries_treated_as_zero(self):
        """测试负max_retries视为0"""
        rm = ResilienceManager()
        task = lambda: Result(success=False, error="fail")
        result = rm.execute_with_retry(task, max_retries=-1)
        assert result.success is False


class TestCircuitBreakerIntegration:
    """测试熔断器集成"""

    def test_circuit_breaker_check_closed(self):
        """测试熔断器CLOSED状态检查"""
        rm = ResilienceManager()
        assert rm.circuit_breaker_check("test_service") is True

    def test_circuit_breaker_check_open(self):
        """测试熔断器OPEN状态检查"""
        rm = ResilienceManager({"circuit_failure_threshold": 1})
        rm.circuit_breaker_record("test_service", False)
        assert rm.circuit_breaker_check("test_service") is False

    def test_circuit_breaker_record_success(self):
        """测试熔断器记录成功"""
        rm = ResilienceManager({"circuit_failure_threshold": 2})
        rm.circuit_breaker_record("svc", False)
        assert rm.circuit_breaker_check("svc") is True
        rm.circuit_breaker_record("svc", True)
        # 成功重置


class TestCheckpoint:
    """测试检查点功能"""

    def test_checkpoint_save_and_load_memory(self):
        """测试内存检查点保存和加载"""
        rm = ResilienceManager()
        state = {"data": "value", "count": 42}
        rm.checkpoint_save("session1", "stage1", state)
        loaded = rm.checkpoint_load("session1", "stage1")
        assert loaded == state

    def test_checkpoint_load_nonexistent(self):
        """测试加载不存在的检查点"""
        rm = ResilienceManager()
        result = rm.checkpoint_load("session1", "nonexistent")
        assert result is None

    def test_checkpoint_save_to_disk(self):
        """测试检查点保存到磁盘"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rm = ResilienceManager({"checkpoint_dir": tmpdir})
            state = {"key": "value"}
            path = rm.checkpoint_save("sess", "stage", state)
            assert path is not None
            assert path.exists()
            loaded = rm.checkpoint_load("sess", "stage")
            assert loaded == state


class TestRollback:
    """测试回滚功能"""

    def test_rollback_success(self):
        """测试成功回滚"""
        rm = ResilienceManager()
        rm.checkpoint_save("sess", "target_stage", {"data": "old"})
        assert rm.rollback("sess", "target_stage") is True

    def test_rollback_failure_no_checkpoint(self):
        """测试回滚失败（无检查点）"""
        rm = ResilienceManager()
        assert rm.rollback("sess", "nonexistent") is False


class TestShouldRetry:
    """测试重试判断"""

    def test_should_retry_recoverable(self):
        """测试可恢复错误应重试"""
        rm = ResilienceManager()
        assert rm.should_retry(TimeoutError(), 0, 3) is True

    def test_should_not_retry_critical(self):
        """测试严重错误不应重试"""
        rm = ResilienceManager()
        assert rm.should_retry(ValueError(), 0, 3) is False

    def test_should_not_retry_at_limit(self):
        """测试达到重试次数限制"""
        rm = ResilienceManager()
        assert rm.should_retry(TimeoutError(), 2, 2) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
