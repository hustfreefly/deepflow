"""
Tests for domains/ship_pro/ship_living_md.py

契约笼子: round-trip 无损（dict → MD → dict 核心字段保留率 ≥ 90%）
"""

import json
import pytest
from pathlib import Path

from domains.ship_pro.ship_living_md import (
    render_ship_package_md,
    parse_ship_package_md,
    validate_ship_package_md,
    REQUIRED_SECTIONS,
)


MINIMAL_PACKAGE = {
    "ship_package_version": "1.0",
    "solution": "Test Solution",
    "work_packages": [
        {
            "id": "WP-001",
            "title": "Setup project",
            "description": "Initialize the project structure",
            "acceptance_criteria": ["Project builds"],
            "deliverables": [{"name": "src/", "type": "directory"}],
            "effort_hours": 4,
            "requirement_ids": ["REQ-001"],
        }
    ],
    "dependency_graph": {
        "execution_layers": [["WP-001"]],
    },
    "statistics": {"total_wps": 1, "total_effort_hours": 4},
}

RICH_PACKAGE = {
    "ship_package_version": "v9",
    "solution": "Ship Pro V8 Output",
    "work_packages": [
        {
            "id": "WP-001", "title": "Core API", "description": "Build REST API",
            "acceptance_criteria": [{"criterion": "All endpoints respond"}],
            "deliverables": [{"name": "api.py", "type": "file"}],
            "effort_hours": 16, "requirement_ids": ["REQ-001", "REQ-002"],
            "dependencies": [],
        },
        {
            "id": "WP-002", "title": "Database Layer", "description": "Setup DB",
            "acceptance_criteria": [{"criterion": "Migrations pass"}],
            "deliverables": [{"name": "models.py", "type": "file"}],
            "effort_hours": 8, "requirement_ids": ["REQ-003"],
            "dependencies": ["WP-001"],
        },
    ],
    "dependency_graph": {
        "execution_layers": [["WP-001"], ["WP-002"]],
    },
    "statistics": {
        "total_wps": 2, "total_effort_hours": 24,
        "req_coverage_rate": "75%", "dependency_edges": 1,
    },
    "issues": [
        {"description": "Missing test coverage", "severity": "medium"},
    ],
    "pending_req_ids": ["REQ-004", "REQ-005"],
    "semantic_anchors": [
        {"name": "sessions_spawn", "category": "api", "constraint": "depth_limit=2"},
    ],
}


class TestRender:
    def test_minimal(self):
        md = render_ship_package_md(MINIMAL_PACKAGE)
        for s in REQUIRED_SECTIONS:
            assert f"## {s}" in md

    def test_rich_has_optional(self):
        md = render_ship_package_md(RICH_PACKAGE)
        assert "## req_traceability" in md
        assert "## issues" in md
        assert "## semantic_anchors" in md

    def test_frontmatter(self):
        md = render_ship_package_md(MINIMAL_PACKAGE)
        assert md.startswith("---")
        assert "domain: ship_pro" in md

    def test_double_encoded(self):
        md = render_ship_package_md(json.dumps(MINIMAL_PACKAGE))
        assert "## meta_info" in md

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            render_ship_package_md(123)

    def test_empty_dict(self):
        md = render_ship_package_md({})
        for s in REQUIRED_SECTIONS:
            assert f"## {s}" in md


class TestParse:
    def test_parse_minimal(self):
        md = render_ship_package_md(MINIMAL_PACKAGE)
        parsed = parse_ship_package_md(md)
        assert parsed.get("ship_package_version") == "1.0"

    def test_parse_work_packages(self):
        md = render_ship_package_md(RICH_PACKAGE)
        parsed = parse_ship_package_md(md)
        wps = parsed.get("work_packages", [])
        assert len(wps) >= 2
        assert wps[0]["id"] == "WP-001"

    def test_parse_execution_order(self):
        md = render_ship_package_md(RICH_PACKAGE)
        parsed = parse_ship_package_md(md)
        dg = parsed.get("dependency_graph", {})
        layers = dg.get("execution_layers", [])
        assert len(layers) >= 1

    def test_non_string_raises(self):
        with pytest.raises(TypeError):
            parse_ship_package_md(123)


class TestValidate:
    def test_valid_md(self):
        md = render_ship_package_md(MINIMAL_PACKAGE)
        passed, errors = validate_ship_package_md(md)
        assert passed, f"errors: {errors}"

    def test_empty_md(self):
        passed, _ = validate_ship_package_md("")
        assert not passed


class TestRoundTrip:
    def test_minimal_round_trip(self):
        md = render_ship_package_md(MINIMAL_PACKAGE)
        parsed = parse_ship_package_md(md)
        assert parsed["ship_package_version"] == "1.0"
        wps = parsed.get("work_packages", [])
        assert len(wps) >= 1
        assert wps[0]["id"] == "WP-001"

    def test_rich_round_trip(self):
        md = render_ship_package_md(RICH_PACKAGE)
        parsed = parse_ship_package_md(md)

        total = 0
        preserved = 0

        total += 1
        if parsed.get("ship_package_version") == "v9":
            preserved += 1

        total += 1
        wps = parsed.get("work_packages", [])
        if len(wps) >= 2:
            preserved += 1

        total += 1
        dg = parsed.get("dependency_graph", {})
        if dg.get("execution_layers") and len(dg["execution_layers"]) >= 1:
            preserved += 1

        total += 1
        anchors = parsed.get("semantic_anchors", [])
        if anchors and len(anchors) >= 1:
            preserved += 1

        rate = preserved / total
        assert rate >= 0.90, f"Round-trip rate {rate:.0%} < 90% ({preserved}/{total})"

    def test_real_data_round_trip(self):
        """用真实 ship_package.json"""
        real_path = Path(__file__).resolve().parent.parent.parent.parent / "blackboard" / "OpenClaw AI Native Loop Engineering Framework" / "ship_pro" / "stages" / "ship_package.json"
        if not real_path.exists():
            pytest.skip(f"Real data not found: {real_path}")

        with open(real_path) as f:
            data = json.load(f)
        if isinstance(data, str):
            data = json.loads(data)

        md = render_ship_package_md(data)
        passed, errors = validate_ship_package_md(md)
        assert passed, f"Validation failed: {errors}"

        parsed = parse_ship_package_md(md)
        assert len(parsed.get("work_packages", [])) >= len(data.get("work_packages", [])) * 0.9
