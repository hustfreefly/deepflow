"""
DeepFlow 测试全局配置和共享 fixtures.

此文件包含 pytest 全局配置和跨所有测试目录共享的 fixtures。
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Generator, Any
from unittest.mock import Mock, MagicMock

# 项目根目录
ROOT = Path(__file__).parent.parent


# =============================================================================
# Pytest 配置
# =============================================================================

def pytest_configure(config):
    """配置 pytest 运行环境."""
    # 添加自定义标记
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "regression: marks tests as regression tests")
    config.addinivalue_line("markers", "contract: marks tests as contract tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")


# =============================================================================
# 基础 Fixtures
# =============================================================================

@pytest.fixture
async def async_context():
    """提供异步测试上下文."""
    yield {}


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    创建临时目录，测试结束后自动清理.
    
    Yields:
        Path: 临时目录路径
    """
    tmp_path = tempfile.mkdtemp(prefix="deepflow_test_")
    yield Path(tmp_path)
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """
    提供标准 mock 配置.
    
    Returns:
        包含标准配置项的字典
    """
    return {
        "coordinator": {
            "max_rounds": 10,
            "timeout_seconds": 300,
            "hitl_threshold": 0.75,
        },
        "quality_gate": {
            "weights": {
                "accuracy": 0.25,
                "completeness": 0.25,
                "depth": 0.25,
                "elegance": 0.25,
            },
            "thresholds": {
                "auto_pass": 0.90,
                "hitl": 0.75,
                "dimension": 0.60,
            },
        },
        "pipeline": {
            "default_domain": "default",
            "output_dir": "./output",
        },
    }


@pytest.fixture
def sample_domain() -> str:
    """提供示例领域名称."""
    return "stock_analysis"


@pytest.fixture
def sample_task() -> str:
    """提供示例任务描述."""
    return "分析贵州茅台股票的投资价值"


@pytest.fixture
def sample_session_id() -> str:
    """提供示例会话ID."""
    return "test-session-001"


# =============================================================================
# 模拟 Fixtures
# =============================================================================

@pytest.fixture
def mock_coordinator() -> Mock:
    """提供模拟的 Coordinator 实例."""
    from coordinator import Coordinator
    mock = Mock(spec=Coordinator)
    mock.start = Mock(return_value=Mock(
        state="RUNNING",
        session_id="test-session-001",
        is_completed=False,
        is_waiting_agent=False,
    ))
    mock.resume = Mock(return_value=Mock(
        state="COMPLETED",
        session_id="test-session-001",
        is_completed=True,
    ))
    return mock


@pytest.fixture
def mock_quality_gate() -> Mock:
    """提供模拟的 QualityGate 实例."""
    from quality_gate import QualityGate, QualityReport, GateDecision
    mock = Mock(spec=QualityGate)
    mock.evaluate = Mock(return_value=QualityReport(
        overall_score=0.85,
        dimensions={"accuracy": 0.9, "completeness": 0.8, "depth": 0.85, "elegance": 0.8},
        decision=GateDecision.PASS,
        reasoning="测试通过",
    ))
    return mock


@pytest.fixture
def mock_blackboard_manager() -> Mock:
    """提供模拟的 BlackboardManager 实例."""
    mock = Mock()
    mock.create_session = Mock(return_value="test-session-001")
    mock.get_session = Mock(return_value={
        "session_id": "test-session-001",
        "state": "RUNNING",
        "tasks": [],
    })
    mock.update_session = Mock(return_value=True)
    mock.delete_session = Mock(return_value=True)
    return mock


# =============================================================================
# 领域相关 Fixtures
# =============================================================================

@pytest.fixture
def domain_config() -> dict[str, Any]:
    """提供领域配置示例."""
    return {
        "name": "stock_analysis",
        "description": "股票分析领域",
        "stages": [
            {
                "id": "data_collection",
                "name": "数据收集",
                "agent_role": "data_collector",
            },
            {
                "id": "analysis",
                "name": "分析阶段",
                "agent_role": "analyst",
            },
            {
                "id": "report",
                "name": "报告生成",
                "agent_role": "report_writer",
            },
        ],
    }


@pytest.fixture
def sample_agent_result() -> dict[str, Any]:
    """提供示例 Agent 执行结果."""
    return {
        "request_id": "req-001",
        "success": True,
        "output_file": "/tmp/test/output.md",
        "score": 0.85,
        "error": None,
    }


@pytest.fixture
def sample_pipeline_state() -> dict[str, Any]:
    """提供示例流水线状态."""
    return {
        "session_id": "test-session-001",
        "state": "RUNNING",
        "current_stage": 1,
        "total_stages": 3,
        "completed_stages": ["data_collection"],
        "scores": [0.85],
    }


# =============================================================================
# 异步 Fixtures
# =============================================================================

@pytest.fixture
def event_loop():
    """提供事件循环."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_mock_coordinator():
    """提供异步模拟 Coordinator."""
    from coordinator import Coordinator
    mock = Mock(spec=Coordinator)
    
    async def async_start(*args, **kwargs):
        return Mock(
            state="RUNNING",
            session_id="test-session-001",
            is_completed=False,
            is_waiting_agent=True,
            pending_requests=[],
        )
    
    async def async_resume(*args, **kwargs):
        return Mock(
            state="COMPLETED",
            session_id="test-session-001",
            is_completed=True,
        )
    
    mock.start = async_start
    mock.resume = async_resume
    return mock
