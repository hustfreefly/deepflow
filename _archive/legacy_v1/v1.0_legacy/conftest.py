"""
DeepFlow 集成测试配置.

此文件包含集成测试特有的 fixtures 和配置。
集成测试验证多个组件的协同工作。
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Generator, Any
from unittest.mock import Mock, patch

# 项目根目录
ROOT = Path(__file__).parent.parent


# =============================================================================
# 集成测试配置
# =============================================================================

# 标记所有测试为集成测试
pytestmark = pytest.mark.integration


def pytest_configure(config):
    """配置集成测试环境."""
    # 确保集成测试标记已注册
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")


# =============================================================================
# 集成测试 Fixtures
# =============================================================================

@pytest.fixture
def integration_temp_dir() -> Generator[Path, None, None]:
    """
    创建集成测试专用临时目录.
    
    Yields:
        Path: 临时目录路径
    """
    tmp_path = tempfile.mkdtemp(prefix="deepflow_integration_")
    yield Path(tmp_path)
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def test_config_path(integration_temp_dir: Path) -> Path:
    """
    创建测试配置文件.
    
    Args:
        integration_temp_dir: 临时目录
    
    Returns:
        配置文件路径
    """
    config_file = integration_temp_dir / "test_config.yaml"
    config_content = """
coordinator:
  max_rounds: 5
  timeout_seconds: 60
  hitl_threshold: 0.75

quality_gate:
  weights:
    accuracy: 0.25
    completeness: 0.25
    depth: 0.25
    elegance: 0.25
  thresholds:
    auto_pass: 0.90
    hitl: 0.75
    dimension: 0.60

pipeline:
  default_domain: "default"
  output_dir: "./output"
  
blackboard:
  storage_dir: "./blackboard"
  
resilience:
  timeout_seconds: 30
  max_retries: 3
"""
    config_file.write_text(config_content, encoding='utf-8')
    return config_file


@pytest.fixture
def mock_external_services() -> dict[str, Mock]:
    """
    提供模拟的外部服务.
    
    Returns:
        包含模拟服务的字典
    """
    return {
        "llm": Mock(),
        "file_storage": Mock(),
        "notification": Mock(),
    }


@pytest.fixture
def integration_test_data() -> dict[str, Any]:
    """
    提供集成测试数据.
    
    Returns:
        测试数据字典
    """
    return {
        "tasks": [
            "分析贵州茅台股票",
            "评估腾讯控股投资价值",
            "研究宁德时代行业地位",
        ],
        "domains": [
            "stock_analysis",
            "market_research",
            "industry_analysis",
        ],
        "expected_stages": [
            "data_collection",
            "analysis",
            "report",
        ],
    }


@pytest.fixture
async def coordinator_instance(integration_temp_dir: Path):
    """
    提供初始化的 Coordinator 实例.
    
    Args:
        integration_temp_dir: 临时目录
    
    Yields:
        Coordinator 实例
    """
    from coordinator import Coordinator
    
    coordinator = Coordinator()
    
    # 设置测试输出目录
    coordinator._output_dir = integration_temp_dir / "output"
    coordinator._output_dir.mkdir(exist_ok=True)
    
    yield coordinator
    
    # 清理
    await coordinator._cleanup_test_resources()


@pytest.fixture
def pipeline_engine_instance(integration_temp_dir: Path):
    """
    提供初始化的 PipelineEngine 实例.
    
    Args:
        integration_temp_dir: 临时目录
    
    Yields:
        PipelineEngine 实例
    """
    from pipeline_engine import PipelineEngine
    
    engine = PipelineEngine()
    engine.output_dir = integration_temp_dir / "pipeline_output"
    engine.output_dir.mkdir(exist_ok=True)
    
    yield engine


@pytest.fixture
def quality_gate_instance():
    """
    提供初始化的 QualityGate 实例.
    
    Yields:
        QualityGate 实例
    """
    from quality_gate import QualityGate
    
    gate = QualityGate()
    yield gate


# =============================================================================
# E2E 测试 Fixtures
# =============================================================================

@pytest.fixture
def e2e_test_config() -> dict[str, Any]:
    """
    提供端到端测试配置.
    
    Returns:
        E2E 测试配置字典
    """
    return {
        "mode": "D",
        "max_rounds": 3,
        "expected_completion": True,
        "expected_min_score": 0.60,
    }


@pytest.fixture
def e2e_session_flow() -> list[dict]:
    """
    提供端到端会话流程数据.
    
    Returns:
        会话流程步骤列表
    """
    return [
        {
            "action": "start",
            "input": "分析贵州茅台股票",
            "expected_state": "RUNNING",
        },
        {
            "action": "execute_agents",
            "expected_state": "RUNNING",
        },
        {
            "action": "evaluate",
            "expected_state": "COMPLETED",
        },
    ]


# =============================================================================
# 契约 Fixtures
# =============================================================================

@pytest.fixture
def contract_test_data() -> dict[str, Any]:
    """
    提供契约测试数据.
    
    Returns:
        契约测试数据字典
    """
    return {
        "valid_inputs": {
            "task": "有效的任务描述",
            "domain": "stock_analysis",
            "config": {"max_rounds": 10},
        },
        "invalid_inputs": {
            "empty_task": "",
            "invalid_domain": "nonexistent_domain",
            "negative_rounds": -1,
        },
        "boundary_cases": {
            "min_task_length": "a",
            "max_task_length": "x" * 10000,
            "threshold_boundary": [0.749, 0.75, 0.751],
        },
    }


# =============================================================================
# 并发测试 Fixtures
# =============================================================================

@pytest.fixture
def concurrent_test_config() -> dict[str, Any]:
    """
    提供并发测试配置.
    
    Returns:
        并发测试配置字典
    """
    return {
        "num_concurrent_sessions": 3,
        "timeout_seconds": 120,
        "expected_all_complete": True,
    }


@pytest.fixture
async def concurrent_sessions(integration_temp_dir: Path):
    """
    提供并发会话管理器.
    
    Args:
        integration_temp_dir: 临时目录
    
    Yields:
        会话管理字典
    """
    from coordinator import Coordinator
    
    sessions = {}
    coordinators = []
    
    for i in range(3):
        coordinator = Coordinator()
        coordinator._output_dir = integration_temp_dir / f"session_{i}"
        coordinator._output_dir.mkdir(exist_ok=True)
        coordinators.append(coordinator)
        sessions[f"session_{i}"] = {
            "coordinator": coordinator,
            "task": f"测试任务 {i}",
        }
    
    yield sessions
    
    # 清理
    for coordinator in coordinators:
        await coordinator._cleanup_test_resources()
