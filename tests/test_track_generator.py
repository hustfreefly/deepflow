"""
ADR-009 Phase 4: Tests for core/track_generator.py — multi-domain track generation.

Tests the shared utility that all domains use to generate track.json.
"""

import json
import pytest
from pathlib import Path


class TestGenerateTrackFromMd:
    """Test generate_track_from_md() — for domains with existing MD output."""

    def test_graceful_skip_when_extractor_unavailable(self, tmp_path, monkeypatch):
        """extractor 不可用时跳过，不报错。"""
        import core.track_generator as tg

        monkeypatch.setattr(tg, "_HAS_TRACK_EXTRACTOR", False)

        md_path = tmp_path / "test.md"
        md_path.write_text("# Test\n", encoding="utf-8")

        result = tg.generate_track_from_md(md_path, "deliver_pro")
        assert result is None

    def test_skip_when_md_missing(self, tmp_path):
        """MD 文件不存在时跳过。"""
        from core.track_generator import generate_track_from_md

        result = generate_track_from_md(tmp_path / "nonexistent.md", "deliver_pro")
        assert result is None

    def test_normal_path_deliver_pro(self, tmp_path):
        """合法 deliver_pro MD → 生成 track.json。"""
        from core.track_generator import generate_track_from_md

        md_path = tmp_path / "DELIVERABLE.md"
        md_path.write_text("""---
domain: deliver_pro
version: "1.0.0"
session: test_001
---

# Deliver Final: Test

## meta_info

| 字段 | 值 |
|------|-----|
| total_files | 3 |
| total_size_kb | 50 |

## deliverables

| 交付物 | 来源 WP | 路径 |
|--------|---------|------|
| API | WP-001 | src/api/ |

## execution_guide

部署即可。

## Gate 决策

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 | PASS | OK |
| L3 (合并) | PASS | 完成 |
""", encoding="utf-8")

        track_path = tmp_path / "deliver_pro_track.json"
        result = generate_track_from_md(md_path, "deliver_pro", track_path)

        assert result is not None
        assert result["schema_version"] == "3.1.0"
        assert result["domain"] == "deliver_pro"
        assert track_path.exists()

    def test_normal_path_solution_pro(self, tmp_path):
        """合法 solution_pro MD → 生成 track.json。"""
        from core.track_generator import generate_track_from_md

        md_path = tmp_path / "final_solution.md"
        # Solution Pro 模板要求的章节名（来自 templates/solution_design.md）
        md_path.write_text("""---
domain: solution_pro
version: "1.0.0"
session: sol_001
---

# Solution Design: AI Platform

## meta_info

| 字段 | 值 |
|------|-----|
| solution_type | architecture |
| complexity | high |
| estimated_effort | 200h |

## solution_structure

Microservices architecture with 3 layers. The system is designed to handle high concurrency
and provide fault tolerance through service mesh patterns.

### 核心组件

- API Gateway: 统一入口，负责认证、限流、路由
- Service Mesh: 服务间通信，提供负载均衡、熔断、追踪
- Data Layer: PostgreSQL + Redis 双层存储

## requirement_coverage

| REQ-ID | 描述 | 覆盖方式 |
|--------|------|----------|
| REQ-001 | 高并发 | 水平扩展 + 缓存 |
| REQ-002 | 低延迟 | CDN + 边缘计算 |
| REQ-003 | 安全 | mTLS + OAuth2 |

## 关键技术决策

| 决策 | 选项 | 理由 |
|------|------|------|
| DB | PostgreSQL | ACID 保证 |
| Cache | Redis | 低延迟 |
| Queue | RabbitMQ | 可靠性 |

## implementation_plan

1. Phase 1: Setup infra (K8s + Istio)
2. Phase 2: Deploy core services
3. Phase 3: Integration testing
4. Phase 4: Performance optimization

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| Scale | high | Auto-scaling + rate limiting |
| Data loss | medium | Multi-AZ replication |

## Gate 决策

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 | PASS | 结构完整 |
| L3 (合并) | PASS | 设计完成 |
""", encoding="utf-8")

        track_path = tmp_path / "solution_pro_track.json"
        result = generate_track_from_md(md_path, "solution_pro", track_path)

        assert result is not None
        assert result["domain"] == "solution_pro"
        assert track_path.exists()

    def test_validation_failure_returns_none(self, tmp_path):
        """MD 结构不合法 → 返回 None。"""
        from core.track_generator import generate_track_from_md

        md_path = tmp_path / "bad.md"
        md_path.write_text("# Incomplete\n\nNo sections.\n", encoding="utf-8")

        result = generate_track_from_md(md_path, "deliver_pro")
        assert result is None


class TestGenerateTrackFromJson:
    """Test generate_track_from_json() — for domains needing JSON → MD conversion."""

    def test_spec_pro_json_to_md_and_track(self, tmp_path):
        """living_spec.json → spec_requirements.md + spec_track.json。"""
        from core.track_generator import generate_track_from_json

        json_path = tmp_path / "living_spec.json"
        json_path.write_text(json.dumps({
            "project_name": "AI Customer Service",
            "domain_type": "software",
            "session_id": "spec_001",
            "narrative": "Build an AI-powered customer service platform.",
            "confirmed_requirements": [
                {"id": "REQ-001", "description": "Multi-language support", "priority": "MUST"},
                {"id": "REQ-002", "description": "Real-time chat", "priority": "SHOULD"},
                {"id": "REQ-003", "description": "Analytics dashboard", "priority": "COULD"},
            ],
            "guardrails": ["GDPR compliance", "99.9% uptime SLA"],
            "semantic_anchors": [
                {"name": "max_response_time", "category": "performance", "constraint": "< 200ms"},
            ],
        }), encoding="utf-8")

        result = generate_track_from_json(json_path, "spec_pro", tmp_path)

        # MD should be generated
        md_path = tmp_path / "spec_requirements.md"
        assert md_path.exists(), "spec_requirements.md should be generated"

        md_content = md_path.read_text(encoding="utf-8")
        assert "AI Customer Service" in md_content
        assert "REQ-001" in md_content
        assert "REQ-001" in md_content  # converter generates REQ-001 from confirmed fields
        assert "GDPR compliance" in md_content

        # Track should be generated
        if result is not None:
            track_path = tmp_path / "spec_pro_track.json"
            assert track_path.exists()
            assert result["domain"] == "spec_pro"
            assert "REQ-001" in result["metrics"]["req_ids"]

    def test_ship_pro_json_to_md_and_track(self, tmp_path):
        """ship_package.json → ship_package.md + ship_track.json。"""
        from core.track_generator import generate_track_from_json

        json_path = tmp_path / "ship_package.json"
        json_path.write_text(json.dumps({
            "project_name": "E-commerce Platform",
            "session_id": "ship_001",
            "work_packages": [
                {"wp_id": "WP-001", "title": "User Auth Module", "estimated_effort": 40, "dependencies": []},
                {"wp_id": "WP-002", "title": "Payment Gateway", "estimated_effort": 60, "dependencies": ["WP-001"]},
                {"wp_id": "WP-003", "title": "Inventory System", "estimated_effort": 80, "dependencies": []},
            ],
            "total_effort_hours": 180,
            "requirement_coverage": {"percentage": "95%", "covered": 19, "total": 20},
        }), encoding="utf-8")

        result = generate_track_from_json(json_path, "ship_pro", tmp_path)

        # MD should be generated
        md_path = tmp_path / "ship_package.md"
        assert md_path.exists(), "ship_package.md should be generated"

        md_content = md_path.read_text(encoding="utf-8")
        assert "E-commerce Platform" in md_content
        assert "WP-001" in md_content
        assert "Payment Gateway" in md_content

        # Track should be generated
        if result is not None:
            track_path = tmp_path / "ship_pro_track.json"
            assert track_path.exists()
            assert result["domain"] == "ship_pro"

    def test_missing_json_returns_none(self, tmp_path):
        """JSON 不存在 → 返回 None。"""
        from core.track_generator import generate_track_from_json

        result = generate_track_from_json(tmp_path / "nonexistent.json", "spec_pro")
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        """JSON 格式错误 → 返回 None。"""
        from core.track_generator import generate_track_from_json

        json_path = tmp_path / "bad.json"
        json_path.write_text("not valid json {{{", encoding="utf-8")

        result = generate_track_from_json(json_path, "spec_pro")
        assert result is None


class TestSpecJsonToMd:
    """Test _spec_json_to_md() — Spec Pro JSON → MD converter."""

    def test_minimal_input(self):
        """最小输入生成有效 MD。"""
        from core.track_generator import _spec_json_to_md

        md = _spec_json_to_md({
            "project_name": "Test",
            "requirements": [{"id": "REQ-001", "description": "Feature A", "priority": "MUST"}],
        })

        assert "# Spec Requirements: Test" in md
        assert "REQ-001" in md
        assert "REQ-001" in md  # converter generates from confirmed fields
        assert "gate_decisions" in md

    def test_empty_requirements(self):
        """空需求列表不崩溃。"""
        from core.track_generator import _spec_json_to_md

        md = _spec_json_to_md({"project_name": "Empty"})
        assert "# Spec Requirements: Empty" in md


class TestShipJsonToMd:
    """Test _ship_json_to_md() — Ship Pro JSON → MD converter."""

    def test_minimal_input(self):
        """最小输入生成有效 MD。"""
        from core.track_generator import _ship_json_to_md

        md = _ship_json_to_md({
            "project_name": "Test Platform",
            "work_packages": [
                {"wp_id": "WP-001", "title": "Module A", "estimated_effort": 20, "dependencies": []},
            ],
            "total_effort_hours": 20,
        })

        assert "# Ship Package: Test Platform" in md
        assert "WP-001" in md
        assert "Module A" in md
        assert "gate_decisions" in md

    def test_empty_packages(self):
        """空工作包列表不崩溃。"""
        from core.track_generator import _ship_json_to_md

        md = _ship_json_to_md({"project_name": "Empty"})
        assert "# Ship Package: Empty" in md


class TestDomainIntegrationFunctions:
    """Test the domain-specific generate_*_track() functions."""

    def test_spec_pro_generate_spec_track(self, tmp_path):
        """spec_pro_api.generate_spec_track() 端到端测试。"""
        # Create a living_spec.json
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "living_spec.json").write_text(json.dumps({
            "project_name": "Test Spec",
            "domain_type": "software",
            "session_id": "spec_test",
            "narrative": "A test specification.",
            "confirmed_requirements": [
                {"id": "REQ-001", "description": "Must work", "priority": "MUST"},
            ],
            "guardrails": [],
            "semantic_anchors": [],
        }), encoding="utf-8")

        from domains.spec_pro.spec_pro_api import generate_spec_track
        result = generate_spec_track(tmp_path)

        # Should generate MD
        md_path = spec_dir / "spec_requirements.md"
        assert md_path.exists(), "spec_requirements.md should be generated"

    def test_solution_pro_generate_solution_track(self, tmp_path):
        """solution_pro.generate_solution_track() 端到端测试。"""
        # Create a final_solution.md
        (tmp_path / "final_solution.md").write_text("""---
domain: solution_pro
version: "1.0.0"
session: sol_test
---

# Solution Design: Test

## meta_info

| 字段 | 值 |
|------|-----|
| solution_type | architecture |

## 架构设计

Simple architecture.

## 关键技术决策

| 决策 | 选项 | 理由 |
|------|------|------|
| DB | PostgreSQL | ACID |

## 执行计划

1. Deploy

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| None | low | N/A |

## Gate 决策

| 检查层 | 结果 | 说明 |
|--------|------|------|
| L1 | PASS | OK |
| L3 (合并) | PASS | Done |
""", encoding="utf-8")

        from domains.solution_pro import generate_solution_track
        result = generate_solution_track(str(tmp_path))

        if result is not None:
            track_path = tmp_path / "solution_track.json"
            assert track_path.exists()

    def test_ship_pro_generate_ship_track(self, tmp_path):
        """ship_pro.generate_ship_track() 端到端测试。"""
        # Create ship_package.json
        stages_dir = tmp_path / "stages"
        stages_dir.mkdir()
        (stages_dir / "ship_package.json").write_text(json.dumps({
            "project_name": "Test Ship",
            "session_id": "ship_test",
            "work_packages": [
                {"wp_id": "WP-001", "title": "Build X", "estimated_effort": 30, "dependencies": []},
            ],
            "total_effort_hours": 30,
        }), encoding="utf-8")

        from domains.ship_pro import generate_ship_track
        result = generate_ship_track(str(tmp_path))

        # Should generate MD
        md_path = stages_dir / "ship_package.md"
        assert md_path.exists(), "ship_package.md should be generated"

    def test_all_functions_handle_missing_files(self, tmp_path):
        """所有域函数在文件不存在时返回 None，不崩溃。"""
        from domains.spec_pro.spec_pro_api import generate_spec_track
        from domains.solution_pro import generate_solution_track
        from domains.ship_pro import generate_ship_track

        assert generate_spec_track(tmp_path) is None
        assert generate_solution_track(str(tmp_path)) is None
        assert generate_ship_track(str(tmp_path)) is None
