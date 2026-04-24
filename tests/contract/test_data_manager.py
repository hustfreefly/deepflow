#!/usr/bin/env python3
"""
test_data_manager.py - DataManager 契约测试
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 添加路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_manager import (
    DataProvider, DataQuery, DataResult, DataRequest, DataFinding,
    ProviderRegistry, ConfigDrivenCollector, DataEvolutionLoop,
    ConditionEvaluator
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_blackboard(temp_dir):
    bb = MagicMock()
    bb.session_dir = str(temp_dir)
    return bb


@pytest.fixture
def mock_provider():
    class MockProvider(DataProvider):
        def fetch(self, query: DataQuery) -> DataResult:
            return DataResult(
                data={"mock_key": "mock_value", "query": query.source_id},
                metadata={"source": "mock"}
            )

        def validate_finding(self, finding: DataFinding) -> bool:
            # 调用父类默认验证（source + confidence 检查）
            if not finding.source or finding.source == "unknown":
                return False
            if finding.confidence < 0.7:
                return False
            return True

    return MockProvider()


@pytest.fixture
def sample_config(temp_dir):
    config_file = temp_dir / "test_config.yaml"
    config_file.write_text("""
domain: test
bootstrap:
  - id: test_data
    provider: mock_provider
    config:
      key: value
    ttl: "30d"
    output: "01_test/"
dynamic_rules:
  - trigger: "test rule"
    condition:
      eq: ["data_request.type", "test"]
    action:
      provider: mock_provider
      config:
        key: dynamic_value
""")
    return str(config_file)


# ============================================================
# Test DataProvider Interface
# ============================================================

class TestDataProvider:
    def test_interface_is_abstract(self):
        """DataProvider 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            DataProvider()

    def test_concrete_implementation(self, mock_provider):
        """具体实现可以工作"""
        query = DataQuery(source_id="test", params={"key": "value"})
        result = mock_provider.fetch(query)
        assert isinstance(result, DataResult)
        assert result.data["mock_key"] == "mock_value"


# ============================================================
# Test ProviderRegistry
# ============================================================

class TestProviderRegistry:
    def setup_method(self):
        ProviderRegistry._providers = {}

    def test_register_and_get(self, mock_provider):
        ProviderRegistry.register("test", mock_provider)
        provider = ProviderRegistry.get("test")
        assert provider is mock_provider

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError):
            ProviderRegistry.get("nonexistent")

    def test_list_all(self, mock_provider):
        ProviderRegistry.register("a", mock_provider)
        ProviderRegistry.register("b", mock_provider)
        assert set(ProviderRegistry.list_all()) == {"a", "b"}


# ============================================================
# Test ConditionEvaluator
# ============================================================

class TestConditionEvaluator:
    def test_string_eq(self):
        result = ConditionEvaluator.evaluate(
            "data_request.type == 'competitor'",
            {"data_request": {"type": "competitor"}}
        )
        assert result == True

    def test_string_neq(self):
        result = ConditionEvaluator.evaluate(
            "data_request.type == 'competitor'",
            {"data_request": {"type": "other"}}
        )
        assert result == False

    def test_dict_eq(self):
        result = ConditionEvaluator.evaluate(
            {"eq": ["data_request.type", "test"]},
            {"data_request": {"type": "test"}}
        )
        assert result == True

    def test_dict_and(self):
        result = ConditionEvaluator.evaluate(
            {"and": [
                {"eq": ["a", 1]},
                {"eq": ["b", 2]},
            ]},
            {"a": 1, "b": 2}
        )
        assert result == True

    def test_dict_or(self):
        result = ConditionEvaluator.evaluate(
            {"or": [
                {"eq": ["a", 1]},
                {"eq": ["a", 2]},
            ]},
            {"a": 2}
        )
        assert result == True


# ============================================================
# Test ConfigDrivenCollector
# ============================================================

class TestConfigDrivenCollector:
    def test_load_config(self, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        assert collector.config["domain"] == "test"

    def test_load_missing_config(self):
        with pytest.raises(ValueError):
            ConfigDrivenCollector("/nonexistent/path.yaml")

    def test_get_bootstrap_tasks(self, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        tasks = collector.get_bootstrap_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == "test_data"

    def test_get_dynamic_rules(self, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        rules = collector.get_dynamic_rules()
        assert len(rules) == 1

    def test_resolve_placeholders(self, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        config = {"url": "http://example.com/{code}/data"}
        context = {"code": "300604"}
        resolved = collector.resolve_placeholders(config, context)
        assert resolved["url"] == "http://example.com/300604/data"

    def test_resolve_missing_placeholder(self, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        config = {"url": "http://example.com/{code}/data"}
        context = {}  # 缺少 code
        resolved = collector.resolve_placeholders(config, context)
        # 占位符无法替换，保留原文
        assert "{code}" in resolved["url"]


# ============================================================
# Test DataEvolutionLoop
# ============================================================

class TestDataEvolutionLoop:
    def test_bootstrap_phase(self, mock_blackboard, mock_provider, sample_config):
        ProviderRegistry.register("mock_provider", mock_provider)
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        result = loop.bootstrap_phase({"code": "300604"})
        assert "test_data" in result
        assert loop.data_version == 1

    def test_collect_requests(self, mock_blackboard, mock_provider, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        agent_outputs = [
            {
                "agent_role": "analyst",
                "data_requests": [
                    {"type": "competitor", "query": "华峰测控", "priority": "high", "reason": "对比"},
                ]
            }
        ]

        requests = loop.collect_requests(agent_outputs)
        assert len(requests) == 1
        assert requests[0].data_type == "competitor"

    def test_collect_requests_dedup(self, mock_blackboard, sample_config):
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        agent_outputs = [
            {"agent_role": "A", "data_requests": [{"type": "news", "query": "AI", "priority": "high", "reason": "x"}]},
            {"agent_role": "B", "data_requests": [{"type": "news", "query": "AI", "priority": "medium", "reason": "y"}]},
        ]

        requests = loop.collect_requests(agent_outputs)
        assert len(requests) == 1  # 去重

    def test_ingest_findings(self, mock_blackboard, mock_provider, sample_config):
        ProviderRegistry.register("mock_provider", mock_provider)
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        # 确保 provider 在 collector 配置中被识别
        collector.config["domain"] = "mock_provider"

        agent_outputs = [
            {
                "agent_role": "analyst",
                "findings": {
                    "competitor_margin": {
                        "type": "financial_comparison",
                        "value": {"毛利率": "55%"},
                        "source": "https://example.com",
                        "confidence": 0.85,
                    }
                }
            }
        ]

        findings = loop.ingest_findings(agent_outputs)
        assert "competitor_margin" in findings

    def test_is_data_fresh(self, mock_blackboard, mock_provider, sample_config):
        ProviderRegistry.register("mock_provider", mock_provider)
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        # 先写入数据
        loop.bootstrap_phase({"code": "300604"})

        # 新数据应该是新鲜的
        assert loop.is_data_fresh("test_data", max_age_hours=720) == True

    def test_list_datasets(self, mock_blackboard, mock_provider, sample_config):
        ProviderRegistry.register("mock_provider", mock_provider)
        collector = ConfigDrivenCollector(sample_config)
        loop = DataEvolutionLoop(collector, mock_blackboard, ProviderRegistry)

        loop.bootstrap_phase({"code": "300604"})
        datasets = loop.list_datasets()
        assert "test_data" in datasets


# ============================================================
# Test DataFinding Validation
# ============================================================

class TestDataFindingValidation:
    def test_valid_finding(self, mock_provider):
        finding = DataFinding(
            discoverer="analyst",
            data_type="financial",
            key="revenue",
            value=100,
            source="https://example.com",
            confidence=0.9,
        )
        assert mock_provider.validate_finding(finding) == True

    def test_invalid_source(self, mock_provider):
        finding = DataFinding(
            discoverer="analyst",
            data_type="financial",
            key="revenue",
            value=100,
            source="unknown",
            confidence=0.9,
        )
        assert mock_provider.validate_finding(finding) == False

    def test_low_confidence(self, mock_provider):
        finding = DataFinding(
            discoverer="analyst",
            data_type="financial",
            key="revenue",
            value=100,
            source="https://example.com",
            confidence=0.5,  # 低于 0.7 阈值
        )
        assert mock_provider.validate_finding(finding) == False


# ============================================================
# Test P0-2: YAML depends_on Mechanism
# ============================================================

class TestDependsOnMechanism:
    def test_get_task_dependencies(self, temp_dir):
        """P0-2: 获取任务依赖关系"""
        config_file = temp_dir / "test_depends.yaml"
        config_file.write_text("""
domain: test
bootstrap:
  - id: task_a
    provider: mock
  - id: task_b
    provider: mock
    depends_on: task_a
  - id: task_c
    provider: mock
    depends_on: [task_a, task_b]
""")
        collector = ConfigDrivenCollector(str(config_file))
        deps = collector.get_task_dependencies()
        
        assert deps["task_a"] == []
        assert deps["task_b"] == ["task_a"]
        assert deps["task_c"] == ["task_a", "task_b"]

    def test_execution_order_no_deps(self, temp_dir):
        """P0-2: 无依赖时按配置顺序执行"""
        config_file = temp_dir / "test_order.yaml"
        config_file.write_text("""
domain: test
bootstrap:
  - id: first
    provider: mock
  - id: second
    provider: mock
""")
        collector = ConfigDrivenCollector(str(config_file))
        order = collector.get_execution_order()
        
        assert len(order) == 2
        assert set(order) == {"first", "second"}

    def test_execution_order_with_deps(self, temp_dir):
        """P0-2: 有依赖时按拓扑顺序执行"""
        config_file = temp_dir / "test_order_deps.yaml"
        config_file.write_text("""
domain: test
bootstrap:
  - id: base
    provider: mock
  - id: dependent
    provider: mock
    depends_on: base
""")
        collector = ConfigDrivenCollector(str(config_file))
        order = collector.get_execution_order()
        
        assert order.index("base") < order.index("dependent")

    def test_circular_dependency_detection(self, temp_dir):
        """P0-2: 检测循环依赖"""
        config_file = temp_dir / "test_circular.yaml"
        config_file.write_text("""
domain: test
bootstrap:
  - id: a
    provider: mock
    depends_on: b
  - id: b
    provider: mock
    depends_on: a
""")
        collector = ConfigDrivenCollector(str(config_file))
        with pytest.raises(ValueError, match="循环依赖"):
            collector.get_execution_order()


# ============================================================
# Test P0-3: Summary Template Fault Tolerance
# ============================================================

class TestSummaryTemplates:
    def test_render_template_with_all_vars(self, temp_dir):
        """P0-3: 渲染模板，所有变量都存在"""
        config_file = temp_dir / "test_template.yaml"
        config_file.write_text("""
domain: test
summary_templates:
  test_summary: |
    Name: {{ data.name | default('N/A') }}
    Value: {{ data.value | default('N/A') }}
""")
        collector = ConfigDrivenCollector(str(config_file))
        
        result = collector.render_summary_template("test_summary", {
            "data": {"name": "Test", "value": 100}
        })
        
        assert "Name: Test" in result
        assert "Value: 100" in result

    def test_render_template_missing_vars(self, temp_dir):
        """P0-3: 渲染模板，变量缺失时使用默认值"""
        config_file = temp_dir / "test_template_default.yaml"
        config_file.write_text("""
domain: test
summary_templates:
  test_summary: |
    Name: {{ data.name | default('N/A') }}
    Value: {{ data.value | default('未知') }}
""")
        collector = ConfigDrivenCollector(str(config_file))
        
        result = collector.render_summary_template("test_summary", {})
        
        assert "Name: N/A" in result
        assert "Value: 未知" in result

    def test_render_template_nested_path(self, temp_dir):
        """P0-3: 渲染模板，支持嵌套路径"""
        config_file = temp_dir / "test_template_nested.yaml"
        config_file.write_text("""
domain: test
summary_templates:
  test_summary: |
    Industry: {{ financials.industry | default('未知行业') }}
""")
        collector = ConfigDrivenCollector(str(config_file))
        
        result = collector.render_summary_template("test_summary", {
            "financials": {"industry": "Technology"}
        })
        
        assert "Industry: Technology" in result

    def test_render_template_nonexistent(self, temp_dir):
        """P0-3: 渲染不存在的模板应抛出异常"""
        config_file = temp_dir / "test_template_nonexist.yaml"
        config_file.write_text("""
domain: test
summary_templates:
  existing_template: "Hello"
""")
        collector = ConfigDrivenCollector(str(config_file))
        
        with pytest.raises(ValueError, match="模板 'nonexistent' 不存在"):
            collector.render_summary_template("nonexistent", {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
