#!/usr/bin/env python3
"""
Tests for Ship Pro V3 L2 Code-Based Eval Checks.

Run with:
    pytest test_eval_checks.py -v
    pytest test_eval_checks.py -v -k "test_good_package"
"""

import json
import os
import pytest

# Add parent directory to path for imports

from eval_code_checks import (
    check_schema_compliance,
    score_ac_verifiability,
    score_all_acs,
    check_dependency_graph,
    check_ac_dedup,
    check_field_completeness,
    run_all_checks,
    format_report,
)

# ===========================================================================
# Test Fixtures — Sample Data
# ===========================================================================

def _make_budget(tokens=5000, time_minutes=120):
    """Helper to create a budget object matching the schema."""
    return {"tokens": tokens, "time_minutes": time_minutes}

@pytest.fixture
def good_ship_package():
    """A well-formed ship_package that should pass all checks."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Setup project scaffolding",
                "objective": "Initialize the project with proper directory structure and dependencies",
                "budget": _make_budget(3000, 60),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "outputs": ["project scaffold"],
                "acceptance_criteria": [
                    "npm run build completes with exit code 0",
                    "pytest tests/test_scaffold.py passes with 0 failures",
                    "curl http://localhost:3000/health returns 200 status code",
                ],
                "model_tier": "fast",
                "context_files": ["package.json"],
            },
            {
                "id": "WP-002",
                "title": "Implement authentication module",
                "objective": "Build JWT-based authentication with login/logout endpoints",
                "budget": _make_budget(8000, 240),
                "complexity": "medium",
                "dependencies": ["WP-001"],
                "priority": "high",
                "outputs": ["auth module"],
                "acceptance_criteria": [
                    "POST /api/login returns 200 status with JWT token in response body",
                    "Token expiry is set to 3600 seconds and refresh works within 300ms",
                    "Invalid credentials return 401 status code with error message",
                    "pytest tests/test_auth.py passes with coverage > 80%",
                ],
                "model_tier": "standard",
                "context_files": ["src/auth/"],
            },
            {
                "id": "WP-003",
                "title": "Build user dashboard API",
                "objective": "Create REST endpoints for user dashboard data aggregation",
                "budget": _make_budget(12000, 360),
                "complexity": "complex",
                "dependencies": ["WP-002"],
                "priority": "medium",
                "outputs": ["dashboard API"],
                "acceptance_criteria": [
                    "GET /api/dashboard returns aggregated data in < 200ms response time",
                    "Response includes user_stats, recent_activity, and notifications fields",
                    "curl -H 'Authorization: Bearer <token>' http://localhost:3000/api/dashboard returns 200",
                    "Load test: 100 QPS sustained for 60 seconds with < 1% error rate",
                ],
                "model_tier": "standard",
                "acceptance_tests": ["load_test.sh"],
            }
        ]
    }

@pytest.fixture
def bad_ship_package():
    """A ship_package with multiple issues that should fail checks."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Setup project",
                "objective": "Initialize project",
                "budget": _make_budget(3000),
                "complexity": "simple",
                "dependencies": ["WP-003"],  # Creates cycle: WP-001 -> WP-003 -> WP-001
                "priority": "high",
                "outputs": ["scaffold"],
                "acceptance_criteria": [
                    "功能实现完成",
                    "测试通过",
                ]
            },
            {
                "id": "WP-002",
                "title": "",  # Empty title — schema violation
                "objective": "Do something",
                "budget": _make_budget(5000),
                "complexity": "invalid_value",  # Invalid enum
                "dependencies": ["WP-999"],  # Invalid reference
                "priority": "medium",
                "outputs": ["feature"],
                "acceptance_criteria": [
                    "功能实现完成",  # Vague — Level 1
                    "满足设计规格",  # Vague — Level 1
                ]
            },
            {
                "id": "WP-003",
                "title": "Build feature",
                "objective": "Build a feature",
                "budget": _make_budget(4000),
                "complexity": "medium",
                "dependencies": ["WP-001"],  # Creates cycle: WP-003 -> WP-001 -> WP-003
                "priority": "low",
                "outputs": ["feature"],
                "acceptance_criteria": [
                    "功能实现完成",  # Duplicate of WP-001 AC
                    "The system should work properly and meet all requirements as expected",
                ]
            },
            {
                # Missing required fields: title, objective, budget, complexity, outputs
                "id": "WP-004",
                "dependencies": [],
                "priority": "low",
                "acceptance_criteria": []
            }
        ]
    }

@pytest.fixture
def single_wp_package():
    """Edge case: single work package with no dependencies."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Standalone task",
                "objective": "Complete a single independent task",
                "budget": _make_budget(2000, 60),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "outputs": ["result"],
                "acceptance_criteria": [
                    "pytest test_standalone.py passes with 0 failures",
                    "Output file exists at ./output/result.json with exit code 0"
                ]
            }
        ]
    }

@pytest.fixture
def large_wp_package():
    """Edge case: 10+ work packages with complex dependency chain."""
    wps = []
    for i in range(1, 13):
        wp = {
            "id": f"WP-{i:03d}",
            "title": f"Task {i}",
            "objective": f"Complete task number {i} in the pipeline",
            "budget": _make_budget(2000 * i, 60 * i),
            "complexity": "simple" if i <= 4 else ("medium" if i <= 8 else "complex"),
            "dependencies": [f"WP-{i-1:03d}"] if i > 1 else [],
            "priority": "critical" if i <= 3 else ("high" if i <= 6 else "medium"),
            "outputs": [f"output_{i}"],
            "acceptance_criteria": [
                f"pytest tests/test_task_{i}.py passes with 0 failures",
                f"Output of task {i} validated with assert result is not None"
            ]
        }
        wps.append(wp)
    return {"work_packages": wps}

@pytest.fixture
def orphan_wp_package():
    """Package with orphan nodes (disconnected graph)."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "First task",
                "objective": "Do first thing",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "outputs": ["first"],
                "acceptance_criteria": ["pytest tests/test_first.py passes"]
            },
            {
                "id": "WP-002",
                "title": "Second task",
                "objective": "Do second thing",
                "budget": _make_budget(3000),
                "complexity": "medium",
                "dependencies": ["WP-001"],
                "priority": "medium",
                "outputs": ["second"],
                "acceptance_criteria": ["pytest tests/test_second.py passes"]
            },
            {
                # Orphan: no deps, not depended on
                "id": "WP-003",
                "title": "Isolated task",
                "objective": "Do something unrelated",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "low",
                "outputs": ["isolated"],
                "acceptance_criteria": ["curl http://localhost:8080/health returns 200 status"]
            },
            {
                # Another orphan
                "id": "WP-004",
                "title": "Another isolated task",
                "objective": "Do yet another unrelated thing",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "low",
                "outputs": ["another"],
                "acceptance_criteria": ["assert 1 + 1 == 2 in final validation"]
            }
        ]
    }

@pytest.fixture
def duplicate_ac_package():
    """Package with highly similar/duplicate ACs."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "Auth module",
                "objective": "Build authentication",
                "budget": _make_budget(5000),
                "complexity": "medium",
                "dependencies": [],
                "priority": "high",
                "outputs": ["auth"],
                "acceptance_criteria": [
                    "User can login with valid credentials and receive a JWT token",
                    "User can login with valid email and password and get a JWT token back",
                    "The system should process login requests and return authentication tokens",
                ]
            },
            {
                "id": "WP-002",
                "title": "API endpoints",
                "objective": "Build API",
                "budget": _make_budget(3000),
                "complexity": "simple",
                "dependencies": ["WP-001"],
                "priority": "medium",
                "outputs": ["api"],
                "acceptance_criteria": [
                    "User can login with valid credentials and receive a JWT token",  # Exact duplicate
                    "GET /api/users returns list of users with 200 status code",
                ]
            }
        ]
    }

# ===========================================================================
# 1. Schema Compliance Tests
# ===========================================================================

class TestSchemaCompliance:
    def test_good_package_passes(self, good_ship_package):
        result = check_schema_compliance(good_ship_package)
        assert result["passed"] is True, f"Errors: {result['errors']}"
        assert len(result["errors"]) == 0
        assert result["field_completeness"] > 0.8

    def test_bad_package_fails(self, bad_ship_package):
        result = check_schema_compliance(bad_ship_package)
        assert result["passed"] is False
        assert len(result["errors"]) > 0

    def test_empty_work_packages(self):
        result = check_schema_compliance({"work_packages": []})
        assert result["passed"] is False
        assert result["field_completeness"] == 0.0

    def test_missing_work_packages_key(self):
        result = check_schema_compliance({})
        assert result["passed"] is False

    def test_invalid_wp_id_format(self):
        pkg = {
            "work_packages": [{
                "id": "wp-1",  # Should be WP-001
                "title": "Test",
                "objective": "Test objective",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "outputs": ["test"],
                "acceptance_criteria": ["test passes"]
            }]
        }
        result = check_schema_compliance(pkg)
        assert result["passed"] is False
        assert any("pattern" in e.lower() or "WP-" in e for e in result["errors"])

    def test_invalid_complexity_enum(self):
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                "objective": "Test objective",
                "budget": _make_budget(2000),
                "complexity": "extreme",  # Not in enum
                "dependencies": [],
                "priority": "high",
                "outputs": ["test"],
                "acceptance_criteria": ["test passes"]
            }]
        }
        result = check_schema_compliance(pkg)
        assert result["passed"] is False

    def test_invalid_priority_enum(self):
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                "objective": "Test objective",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "urgent",  # Not in enum
                "outputs": ["test"],
                "acceptance_criteria": ["test passes"]
            }]
        }
        result = check_schema_compliance(pkg)
        assert result["passed"] is False

    def test_budget_as_string_fails(self):
        """Budget must be an object with tokens, not a string."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                "objective": "Test objective",
                "budget": "2h",  # Wrong type
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "outputs": ["test"],
                "acceptance_criteria": ["test passes"]
            }]
        }
        result = check_schema_compliance(pkg)
        assert result["passed"] is False

    def test_field_completeness_partial(self):
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                # Missing: objective, budget, complexity, etc.
                "dependencies": [],
                "priority": "high",
                "acceptance_criteria": ["test passes"],
                "outputs": ["test"],
            }]
        }
        result = check_schema_compliance(pkg)
        assert result["field_completeness"] < 1.0
        assert result["field_completeness"] > 0.0

# ===========================================================================
# 2. AC Verifiability Tests
# ===========================================================================

class TestACVerifiability:
    # --- Level 4: Executable signals ---
    def test_level4_npm_run(self):
        result = score_ac_verifiability("npm run build completes successfully")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_pytest(self):
        result = score_ac_verifiability("pytest tests/test_auth.py passes")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_curl(self):
        result = score_ac_verifiability("curl http://localhost:3000/api/health returns 200")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_assert(self):
        result = score_ac_verifiability("assert response.status == 200")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_numeric_comparison(self):
        result = score_ac_verifiability("Response time < 200ms for all endpoints")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_url(self):
        result = score_ac_verifiability("Deploy to https://app.example.com and verify health check")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_http_method(self):
        result = score_ac_verifiability("POST /api/login returns 200 status with JWT token")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_get_method(self):
        result = score_ac_verifiability("GET /api/users returns list of all active users")
        assert result["level"] == 4
        assert result["score"] == 100

    def test_level4_status_code(self):
        result = score_ac_verifiability("Invalid input returns 400 status code with error details")
        assert result["level"] == 4
        assert result["score"] == 100

    # --- Level 3: Condition signals ---
    def test_level3_milliseconds(self):
        result = score_ac_verifiability("API response time under 150ms for all endpoints")
        assert result["level"] == 3
        assert result["score"] == 60

    def test_level3_percentage(self):
        result = score_ac_verifiability("Test coverage above 80% required")
        assert result["level"] == 3
        assert result["score"] == 60

    def test_level3_qps(self):
        result = score_ac_verifiability("System handles 500 QPS sustained load")
        assert result["level"] == 3
        assert result["score"] == 60

    def test_level3_mb(self):
        result = score_ac_verifiability("Memory usage stays below 512MB under load")
        assert result["level"] == 3
        assert result["score"] == 60

    def test_level3_seconds_chinese(self):
        result = score_ac_verifiability("页面加载时间在3秒以内")
        assert result["level"] == 3
        assert result["score"] == 60

    # --- Level 2: Technical but unquantified ---
    def test_level2_camelcase(self):
        result = score_ac_verifiability("AuthService handles token refresh correctly")
        assert result["level"] == 2
        assert result["score"] == 30

    def test_level2_tech_acronym(self):
        result = score_ac_verifiability("REST API endpoints follow OpenAPI specification")
        assert result["level"] == 2
        assert result["score"] == 30

    def test_level2_chinese_tech(self):
        result = score_ac_verifiability("数据库连接池配置正确，缓存模块正常工作")
        assert result["level"] == 2
        assert result["score"] == 30

    def test_level2_config_name(self):
        result = score_ac_verifiability("package.json contains all required dependencies")
        assert result["level"] == 2
        assert result["score"] == 30

    # --- Level 1: Vague ---
    def test_level1_vague_chinese(self):
        result = score_ac_verifiability("功能实现完成")
        assert result["level"] == 1
        assert result["score"] == 0

    def test_level1_vague_english(self):
        result = score_ac_verifiability("works as expected")
        assert result["level"] == 1
        assert result["score"] == 0

    def test_level1_empty(self):
        result = score_ac_verifiability("")
        assert result["level"] == 1
        assert result["score"] == 0

    def test_level1_none(self):
        result = score_ac_verifiability(None)
        assert result["level"] == 1
        assert result["score"] == 0

    def test_level1_generic_text(self):
        result = score_ac_verifiability("All features should be implemented and working")
        assert result["level"] == 1
        assert result["score"] == 0

    # --- Batch scoring ---
    def test_score_all_acs_good(self, good_ship_package):
        result = score_all_acs(good_ship_package["work_packages"])
        assert result["mean_score"] >= 80, \
            f"Expected mean >= 80, got {result['mean_score']}. Distribution: {result['distribution']}"
        assert result["passed"] is True
        assert result["distribution"]["L4"] > 0

    def test_score_all_acs_bad(self, bad_ship_package):
        result = score_all_acs(bad_ship_package["work_packages"])
        assert result["mean_score"] < 80
        assert result["passed"] is False
        assert result["distribution"]["L1"] > 0

    def test_weakest_acs_tracked(self, bad_ship_package):
        result = score_all_acs(bad_ship_package["work_packages"])
        assert len(result["weakest_acs"]) > 0
        for weak in result["weakest_acs"]:
            assert weak["score"] < 60
            assert "wp_id" in weak
            assert "ac_idx" in weak

# ===========================================================================
# 3. Dependency Graph Tests
# ===========================================================================

class TestDependencyGraph:
    def test_linear_chain(self, good_ship_package):
        result = check_dependency_graph(good_ship_package["work_packages"])
        assert result["passed"] is True
        assert result["has_cycles"] is False
        assert result["orphans"] == []
        assert result["invalid_refs"] == []
        assert result["topological_order"] == ["WP-001", "WP-002", "WP-003"]

    def test_cycle_detection(self, bad_ship_package):
        result = check_dependency_graph(bad_ship_package["work_packages"])
        assert result["has_cycles"] is True
        assert len(result["cycles"]) > 0

    def test_invalid_reference(self, bad_ship_package):
        result = check_dependency_graph(bad_ship_package["work_packages"])
        assert len(result["invalid_refs"]) > 0
        assert any(ref["invalid_dep"] == "WP-999" for ref in result["invalid_refs"])

    def test_orphan_detection(self, orphan_wp_package):
        result = check_dependency_graph(orphan_wp_package["work_packages"])
        assert len(result["orphans"]) > 0
        assert "WP-003" in result["orphans"]
        assert "WP-004" in result["orphans"]

    def test_single_wp_no_orphan(self, single_wp_package):
        """Single WP should NOT be flagged as orphan (module count <= 1)."""
        result = check_dependency_graph(single_wp_package["work_packages"])
        assert result["orphans"] == []
        assert result["passed"] is True

    def test_topological_order_chain(self, large_wp_package):
        result = check_dependency_graph(large_wp_package["work_packages"])
        order = result["topological_order"]
        assert len(order) == 12
        # Verify ordering: each WP comes after its dependency
        positions = {wp_id: i for i, wp_id in enumerate(order)}
        for i in range(2, 13):
            wp_id = f"WP-{i:03d}"
            dep_id = f"WP-{i-1:03d}"
            assert positions[dep_id] < positions[wp_id], \
                f"{dep_id} should come before {wp_id}"

    def test_no_deps_all_orphans(self):
        """Multiple WPs with no dependencies at all = all orphans."""
        pkg = {
            "work_packages": [
                {"id": "WP-001", "dependencies": []},
                {"id": "WP-002", "dependencies": []},
                {"id": "WP-003", "dependencies": []},
            ]
        }
        result = check_dependency_graph(pkg["work_packages"])
        assert len(result["orphans"]) == 3

    def test_diamond_dependency(self):
        """Diamond: A -> B, A -> C, B -> D, C -> D."""
        pkg = {
            "work_packages": [
                {"id": "WP-001", "dependencies": []},          # A (root)
                {"id": "WP-002", "dependencies": ["WP-001"]},  # B -> A
                {"id": "WP-003", "dependencies": ["WP-001"]},  # C -> A
                {"id": "WP-004", "dependencies": ["WP-002", "WP-003"]},  # D -> B, C
            ]
        }
        result = check_dependency_graph(pkg["work_packages"])
        assert result["has_cycles"] is False
        assert result["passed"] is True
        assert result["topological_order"][0] == "WP-001"
        assert result["topological_order"][-1] == "WP-004"

# ===========================================================================
# 4. AC Deduplication Tests
# ===========================================================================

class TestACDedup:
    def test_no_duplicates_good(self, good_ship_package):
        result = check_ac_dedup(good_ship_package["work_packages"])
        assert result["passed"] is True
        assert len(result["duplicate_pairs"]) == 0

    def test_duplicate_detection(self, duplicate_ac_package):
        result = check_ac_dedup(duplicate_ac_package["work_packages"])
        assert result["passed"] is False
        assert len(result["duplicate_pairs"]) > 0
        # Should detect the exact duplicate
        found_exact = False
        for pair in result["duplicate_pairs"]:
            if pair["similarity"] > 0.9:
                found_exact = True
        assert found_exact, "Should detect near-exact duplicate"

    def test_similar_but_not_duplicate(self):
        """ACs that share topic but differ significantly should not be flagged."""
        pkg = {
            "work_packages": [
                {
                    "id": "WP-001",
                    "dependencies": [],
                    "acceptance_criteria": [
                        "POST /api/login returns JWT token with 200 status",
                        "DELETE /api/users/:id returns 204 and removes user from database"
                    ]
                }
            ]
        }
        result = check_ac_dedup(pkg["work_packages"])
        assert result["passed"] is True

    def test_empty_acs(self):
        pkg = {"work_packages": [{"id": "WP-001", "dependencies": [], "acceptance_criteria": []}]}
        result = check_ac_dedup(pkg["work_packages"])
        assert result["passed"] is True
        assert result["duplicate_rate"] == 0.0

    def test_custom_threshold(self, duplicate_ac_package):
        """With a very high threshold, fewer duplicates should be detected."""
        result = check_ac_dedup(duplicate_ac_package["work_packages"], threshold=0.95)
        # Only exact or near-exact matches should pass this threshold
        for pair in result["duplicate_pairs"]:
            assert pair["similarity"] > 0.95

# ===========================================================================
# 5. Field Completeness Tests
# ===========================================================================

class TestFieldCompleteness:
    def test_all_complete(self, good_ship_package):
        result = check_field_completeness(good_ship_package["work_packages"])
        assert result["passed"] is True
        assert result["completeness_rate"] == 1.0

    def test_missing_required_fields(self, bad_ship_package):
        result = check_field_completeness(bad_ship_package["work_packages"])
        assert result["passed"] is False
        assert "WP-004" in result["missing_fields"]
        missing = result["missing_fields"]["WP-004"]
        assert "title" in missing
        assert "objective" in missing

    def test_empty_string_fields(self):
        """Empty strings for required fields should count as missing."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "",
                "objective": "  ",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "acceptance_criteria": ["test passes"],
                "outputs": ["test"],
            }]
        }
        result = check_field_completeness(pkg["work_packages"])
        assert result["passed"] is False
        assert "WP-001" in result["missing_fields"]

    def test_empty_acceptance_criteria(self):
        """Empty acceptance_criteria list should be flagged."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                "objective": "Test objective",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "acceptance_criteria": [],
                "outputs": ["test"],
            }]
        }
        result = check_field_completeness(pkg["work_packages"])
        assert result["passed"] is False

    def test_optional_fields_not_required(self):
        """Missing optional fields should NOT cause failure."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Test",
                "objective": "Test objective",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "acceptance_criteria": ["pytest test.py passes"],
                "outputs": ["test"],
                # No optional fields like model_tier, context_files, etc.
            }]
        }
        result = check_field_completeness(pkg["work_packages"])
        assert result["passed"] is True

    def test_dependencies_can_be_empty(self):
        """Empty dependencies list is valid (root node)."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Root task",
                "objective": "Do something",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": [],
                "priority": "high",
                "acceptance_criteria": ["pytest test.py passes"],
                "outputs": ["result"],
            }]
        }
        result = check_field_completeness(pkg["work_packages"])
        assert result["passed"] is True

# ===========================================================================
# 6. Comprehensive Check (run_all_checks) Tests
# ===========================================================================

class TestRunAllChecks:
    def test_good_package_all_pass(self, good_ship_package):
        result = run_all_checks(good_ship_package)
        assert result["verdict"] == "pass", \
            f"Expected pass, got {result['verdict']}. Summary: {result['summary']}"
        for check_name, check_result in result["checks"].items():
            assert check_result["passed"] is True, \
                f"{check_name} should pass for good package"

    def test_bad_package_has_failures(self, bad_ship_package):
        result = run_all_checks(bad_ship_package)
        assert result["verdict"] == "fail"
        # Multiple checks should fail
        failed = [name for name, check in result["checks"].items() if not check.get("passed")]
        assert len(failed) >= 2, f"Expected multiple failures, got: {failed}"

    def test_summary_format(self, good_ship_package):
        result = run_all_checks(good_ship_package)
        assert "passed" in result["summary"]
        assert "/" in result["summary"]

    def test_summary_includes_issues(self, bad_ship_package):
        result = run_all_checks(bad_ship_package)
        assert "issue" in result["summary"].lower()

    def test_single_wp_passes(self, single_wp_package):
        result = run_all_checks(single_wp_package)
        assert result["verdict"] == "pass", \
            f"Single WP should pass. Summary: {result['summary']}"

    def test_large_package_passes(self, large_wp_package):
        result = run_all_checks(large_wp_package)
        assert result["verdict"] == "pass", \
            f"Large well-formed package should pass. Summary: {result['summary']}"

    def test_orphan_package_fails(self, orphan_wp_package):
        result = run_all_checks(orphan_wp_package)
        assert result["checks"]["dependency_graph"]["passed"] is False

    def test_duplicate_ac_fails(self, duplicate_ac_package):
        result = run_all_checks(duplicate_ac_package)
        assert result["checks"]["ac_dedup"]["passed"] is False

# ===========================================================================
# 7. Format Report Tests
# ===========================================================================

class TestFormatReport:
    def test_report_contains_verdict(self, good_ship_package):
        result = run_all_checks(good_ship_package)
        report = format_report(result)
        assert "PASS" in report
        assert "L2 Code-Based Eval Report" in report

    def test_report_contains_all_sections(self, good_ship_package):
        result = run_all_checks(good_ship_package)
        report = format_report(result)
        assert "Schema Compliance" in report
        assert "AC Verifiability" in report
        assert "Dependency Graph" in report
        assert "AC Deduplication" in report
        assert "Field Completeness" in report

    def test_report_shows_issues(self, bad_ship_package):
        result = run_all_checks(bad_ship_package)
        report = format_report(result)
        assert "FAIL" in report

# ===========================================================================
# 8. Edge Cases & Boundary Tests
# ===========================================================================

class TestEdgeCases:
    def test_ac_with_mixed_signals(self):
        """AC with both executable and condition signals should be Level 4."""
        result = score_ac_verifiability(
            "pytest tests/test_api.py passes with response time < 200ms"
        )
        assert result["level"] == 4

    def test_self_dependency(self):
        """WP depending on itself should be detected as a cycle."""
        pkg = {
            "work_packages": [{
                "id": "WP-001",
                "title": "Self-referencing",
                "objective": "Test",
                "budget": _make_budget(2000),
                "complexity": "simple",
                "dependencies": ["WP-001"],
                "priority": "high",
                "outputs": ["test"],
                "acceptance_criteria": ["pytest test.py passes"]
            }]
        }
        result = check_dependency_graph(pkg["work_packages"])
        assert result["has_cycles"] is True

    def test_unicode_ac_text(self):
        """AC with mixed Chinese/English should be handled correctly."""
        result = score_ac_verifiability("API 响应时间 < 500ms 且返回 200 状态码")
        # Has < 500 which matches executable signal
        assert result["level"] == 4

    def test_very_long_ac_text(self):
        """Very long AC text should not crash."""
        long_text = "Test that the system " + "works correctly " * 1000
        result = score_ac_verifiability(long_text)
        assert result["level"] in [1, 2]  # Should not crash

    def test_special_characters_in_ac(self):
        """AC with special characters should be handled."""
        result = score_ac_verifiability("Response == {\"status\": 200, \"data\": []}")
        assert result["level"] == 4  # Has == signal

    def test_multiple_cycles(self):
        """Graph with multiple independent cycles."""
        pkg = {
            "work_packages": [
                {"id": "WP-001", "dependencies": ["WP-002"]},
                {"id": "WP-002", "dependencies": ["WP-001"]},  # Cycle 1
                {"id": "WP-003", "dependencies": ["WP-004"]},
                {"id": "WP-004", "dependencies": ["WP-003"]},  # Cycle 2
            ]
        }
        result = check_dependency_graph(pkg["work_packages"])
        assert result["has_cycles"] is True
        assert len(result["cycles"]) >= 2

    def test_ngrams_edge_case_short_text(self):
        """Very short text should still produce n-grams."""
        from eval_code_checks import _char_ngrams
        ngrams = _char_ngrams("ab")
        assert len(ngrams) >= 1

    def test_jaccard_identical_sets(self):
        from eval_code_checks import _jaccard_similarity
        assert _jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_jaccard_disjoint_sets(self):
        from eval_code_checks import _jaccard_similarity
        assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_jaccard_empty_sets(self):
        from eval_code_checks import _jaccard_similarity
        assert _jaccard_similarity(set(), set()) == 1.0

# ===========================================================================
# 9. Integration / CLI Tests
# ===========================================================================

class TestCLI:
    def test_cli_with_good_file(self, good_ship_package, tmp_path):
        """CLI should exit 0 for a good package."""
        import subprocess
        pkg_file = tmp_path / "good_package.json"
        pkg_file.write_text(json.dumps(good_ship_package, ensure_ascii=False))

        script_path = os.path.join(os.path.dirname(__file__), "eval_code_checks.py")
        result = subprocess.run(
            [sys.executable, script_path, str(pkg_file), "--json"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["verdict"] == "pass"

    def test_cli_with_bad_file(self, bad_ship_package, tmp_path):
        """CLI should exit 1 for a bad package."""
        import subprocess
        pkg_file = tmp_path / "bad_package.json"
        pkg_file.write_text(json.dumps(bad_ship_package, ensure_ascii=False))

        script_path = os.path.join(os.path.dirname(__file__), "eval_code_checks.py")
        result = subprocess.run(
            [sys.executable, script_path, str(pkg_file), "--json"],
            capture_output=True, text=True
        )
        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output["verdict"] == "fail"

    def test_cli_missing_file(self):
        """CLI should handle missing file gracefully."""
        import subprocess
        script_path = os.path.join(os.path.dirname(__file__), "eval_code_checks.py")
        result = subprocess.run(
            [sys.executable, script_path, "/nonexistent/path.json"],
            capture_output=True, text=True
        )
        assert result.returncode != 0

    def test_cli_invalid_json(self, tmp_path):
        """CLI should handle invalid JSON gracefully."""
        import subprocess
import core.bootstrap
        pkg_file = tmp_path / "invalid.json"
        pkg_file.write_text("{invalid json content")

        script_path = os.path.join(os.path.dirname(__file__), "eval_code_checks.py")
        result = subprocess.run(
            [sys.executable, script_path, str(pkg_file)],
            capture_output=True, text=True
        )
        assert result.returncode != 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
