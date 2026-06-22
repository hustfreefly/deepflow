"""
Pytest 配置文件。
"""

import pytest

def pytest_configure(config):
    """Pytest 配置钩子。"""
    # 添加自定义标记
    config.addinivalue_line(
        "markers", "integration: integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: performance tests"
    )
