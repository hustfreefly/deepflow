"""
Solution Pro V2 Pipeline 异常层次定义

[R1-P0 采纳] ModuleFailure 异常已明确定义，替代现有 RuntimeError/ValueError
"""
from typing import Optional


class PipelineError(Exception):
    """Pipeline 级别异常基类"""
    def __init__(self, message: str, module_name: str = None, details: dict = None):
        super().__init__(message)
        self.module_name = module_name
        self.details = details or {}


class ModuleFailureError(PipelineError):
    """单个模块执行失败"""
    def __init__(self, module_name: str, stage_name: str, error: Exception,
                 retryable: bool = False):
        message = f"Module '{module_name}' failed at stage '{stage_name}': {error}"
        super().__init__(message, module_name, {
            "stage_name": stage_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "retryable": retryable,
        })
        self.stage_name = stage_name
        self.original_error = error
        self.retryable = retryable


class ModuleTimeoutError(PipelineError):
    """模块执行超时"""
    def __init__(self, module_name: str, timeout_seconds: int):
        message = f"Module '{module_name}' timed out after {timeout_seconds}s"
        super().__init__(message, module_name, {
            "timeout_seconds": timeout_seconds,
        })
        self.timeout_seconds = timeout_seconds


class ConvergenceFailureError(PipelineError):
    """收敛失败（Gate A/B 未通过）"""
    def __init__(self, module_name: str, gate_a_result: dict, gate_b_result: dict):
        message = f"Module '{module_name}' convergence failed: Gate A={gate_a_result.get('verdict')}, Gate B={gate_b_result.get('verdict')}"
        super().__init__(message, module_name, {
            "gate_a": gate_a_result,
            "gate_b": gate_b_result,
        })


class DegradedPipelineError(PipelineError):
    """Pipeline 降级执行"""
    def __init__(self, degraded_modules: list, reason: str):
        message = f"Pipeline running in degraded mode: {degraded_modules}. Reason: {reason}"
        super().__init__(message, details={
            "degraded_modules": degraded_modules,
            "reason": reason,
        })
