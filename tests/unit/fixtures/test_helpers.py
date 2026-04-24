"""
单元测试辅助工具和 fixtures.

提供常用的测试辅助函数和模拟数据生成器。
"""

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional
from unittest.mock import Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from coordinator import AgentResult, SessionStatus
from quality_gate import QualityReport, GateDecision


# =============================================================================
# 模拟数据生成器
# =============================================================================

def create_mock_agent_result(
    request_id: str = "req-001",
    success: bool = True,
    output_file: Optional[str] = None,
    score: float = 0.85,
    error: Optional[str] = None,
) -> AgentResult:
    """
    创建模拟 Agent 执行结果.
    
    Args:
        request_id: 请求ID
        success: 是否成功
        output_file: 输出文件路径
        score: 质量分数
        error: 错误信息
    
    Returns:
        AgentResult 实例
    """
    if output_file is None:
        output_file = f"/tmp/test/{request_id}.md"
    return AgentResult(
        request_id=request_id,
        success=success,
        output_file=output_file,
        score=score,
        error=error,
    )


def create_mock_session_status(
    session_id: str = "test-session-001",
    state: str = "RUNNING",
    is_completed: bool = False,
    is_waiting_agent: bool = False,
    pending_requests: Optional[list] = None,
    final_result: Optional[Any] = None,
) -> Mock:
    """
    创建模拟会话状态.
    
    Args:
        session_id: 会话ID
        state: 当前状态
        is_completed: 是否已完成
        is_waiting_agent: 是否等待Agent执行
        pending_requests: 待执行的Agent请求列表
        final_result: 最终结果
    
    Returns:
        模拟的 SessionStatus
    """
    mock = Mock(spec=SessionStatus)
    mock.session_id = session_id
    mock.state = state
    mock.is_completed = is_completed
    mock.is_waiting_agent = is_waiting_agent
    mock.pending_requests = pending_requests or []
    mock.final_result = final_result
    mock.error = None
    return mock


def create_mock_quality_report(
    overall_score: float = 0.85,
    dimensions: Optional[dict] = None,
    decision: GateDecision = GateDecision.PASS,
    reasoning: str = "测试通过",
) -> QualityReport:
    """
    创建模拟质量报告.
    
    Args:
        overall_score: 总体分数
        dimensions: 各维度分数
        decision: 决策结果
        reasoning: 决策理由
    
    Returns:
        QualityReport 实例
    """
    if dimensions is None:
        dimensions = {
            "accuracy": 0.9,
            "completeness": 0.8,
            "depth": 0.85,
            "elegance": 0.8,
        }
    return QualityReport(
        overall_score=overall_score,
        dimensions=dimensions,
        decision=decision,
        reasoning=reasoning,
    )


def create_mock_pipeline_state(
    session_id: str = "test-session-001",
    state: str = "RUNNING",
    current_stage: int = 1,
    total_stages: int = 3,
    completed_stages: Optional[list] = None,
    scores: Optional[list] = None,
) -> dict:
    """
    创建模拟流水线状态字典.
    
    Args:
        session_id: 会话ID
        state: 当前状态
        current_stage: 当前阶段索引
        total_stages: 总阶段数
        completed_stages: 已完成阶段列表
        scores: 阶段分数列表
    
    Returns:
        流水线状态字典
    """
    return {
        "session_id": session_id,
        "state": state,
        "current_stage": current_stage,
        "total_stages": total_stages,
        "completed_stages": completed_stages or [],
        "scores": scores or [],
    }


# =============================================================================
# 断言辅助函数
# =============================================================================

def assert_valid_session_id(session_id: Any) -> None:
    """
    断言 session_id 格式有效.
    
    Args:
        session_id: 要验证的会话ID
    
    Raises:
        AssertionError: 如果格式无效
    """
    assert isinstance(session_id, str), f"session_id 必须是字符串，实际为 {type(session_id)}"
    assert len(session_id) > 0, "session_id 不能为空"
    assert re.match(r'^[\w\-]+$', session_id), f"session_id 包含非法字符: {session_id}"


def assert_valid_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> None:
    """
    断言分数在有效范围内.
    
    Args:
        score: 要验证的分数
        min_val: 最小允许值
        max_val: 最大允许值
    
    Raises:
        AssertionError: 如果分数无效
    """
    assert isinstance(score, (int, float)), f"分数必须是数字，实际为 {type(score)}"
    assert min_val <= score <= max_val, f"分数 {score} 不在范围 [{min_val}, {max_val}] 内"


def assert_valid_state_transition(
    old_state: str,
    new_state: str,
    valid_transitions: dict[str, list[str]],
) -> None:
    """
    断言状态转换有效.
    
    Args:
        old_state: 原状态
        new_state: 新状态
        valid_transitions: 允许的状态转换字典
    
    Raises:
        AssertionError: 如果转换无效
    """
    valid_next = valid_transitions.get(old_state, [])
    assert new_state in valid_next, (
        f"无效状态转换: {old_state} -> {new_state}，"
        f"允许的转换: {valid_next}"
    )


# =============================================================================
# 异步辅助函数
# =============================================================================

def wait_for_async(coro, timeout: float = 5.0):
    """
    同步方式等待异步协程完成.
    
    Args:
        coro: 异步协程
        timeout: 超时时间（秒）
    
    Returns:
        协程返回值
    
    Raises:
        TimeoutError: 如果超时
    """
    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


async def async_assert_raises(func, exception_type, *args, **kwargs):
    """
    异步断言函数抛出指定异常.
    
    Args:
        func: 要测试的异步函数
        exception_type: 期望的异常类型
        *args: 函数参数
        **kwargs: 函数关键字参数
    
    Returns:
        抛出的异常实例
    
    Raises:
        AssertionError: 如果没有抛出期望的异常
    """
    try:
        await func(*args, **kwargs)
        raise AssertionError(f"期望抛出 {exception_type.__name__}，但未抛出")
    except exception_type as e:
        return e


# =============================================================================
# 环境管理
# =============================================================================

class MockFileSystem:
    """
    模拟文件系统，用于测试文件操作.
    
    在临时目录中创建模拟文件结构，测试结束后自动清理。
    """
    
    def __init__(self):
        self.temp_dir = None
        self.files = {}
    
    def setup(self):
        """初始化临时目录."""
        self.temp_dir = tempfile.mkdtemp(prefix="deepflow_mock_fs_")
        return Path(self.temp_dir)
    
    def teardown(self):
        """清理临时目录."""
        import shutil
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_file(self, path: str, content: str = "") -> Path:
        """
        在模拟文件系统中创建文件.
        
        Args:
            path: 相对路径
            content: 文件内容
        
        Returns:
            文件的绝对路径
        """
        assert self.temp_dir, "需要先调用 setup()"
        full_path = Path(self.temp_dir) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        self.files[path] = str(full_path)
        return full_path
    
    def create_json(self, path: str, data: dict) -> Path:
        """
        创建 JSON 文件.
        
        Args:
            path: 相对路径
            data: JSON 数据
        
        Returns:
            文件的绝对路径
        """
        return self.create_file(path, json.dumps(data, indent=2))
    
    def get_path(self, path: str) -> Path:
        """
        获取文件的绝对路径.
        
        Args:
            path: 相对路径
        
        Returns:
            文件的绝对路径
        """
        assert self