#!/usr/bin/env python3
"""
Tests for Ship Pro V3.1 Harness Gate Functions.

Run with:
    pytest test_gates.py -v
    pytest test_gates.py -v -k "test_real_pipeline"
"""

import json
import os
import sys
import pytest

import core.bootstrap
from domains.ship_pro.eval.gates import (
    gate_architect,
    gate_decomposer,
    gate_specifier,
    gate_packager,
    _check_acyclic_from_adj,
    _normalize_deps_to_adj,
)


# ===========================================================================
# Test Data Directory
# ===========================================================================

TEST_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test_output", "real_case_crossborder", "blackboard"
)

# Import STAGE_PATH_REGISTRY for path resolution
import core.bootstrap
from domains.ship_pro.blackboard import STAGE_PATH_REGISTRY


def _load_json(stage_name: str) -> dict:
    """Load a JSON file from the test data directory using STAGE_PATH_REGISTRY."""
    filename = STAGE_PATH_REGISTRY.get(stage_name, stage_name)
    path = os.path.join(TEST_DATA_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(f"Test data not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# Fixtures — Good / Bad / Edge Case Data
# ===========================================================================

@pytest.fixture
def good_blueprint():
    """A well-formed architect blueprint that should PASS the gate."""
    return {
        "project_type": "greenfield",
        "modules": [
            {
                "id": "COMP-001",
                "name": "API Gateway",
                "summary": "Core gateway with routing",
                "responsibilities": ["routing", "auth"],
                "technology_stack": ["Go", "Docker"],
            },
            {
                "id": "COMP-002",
                "name": "Frontend",
                "summary": "User interface",
                "responsibilities": ["dashboard", "landing"],
                "technology_stack": ["Next.js", "React"],
            },
        ],
        "dependencies": [
            {"from": "COMP-002", "to": "COMP-001", "reason": "Frontend calls API"},
        ],
        "requirements": [
            {"req_id": "REQ-001", "description": "API routing", "mapped_components": ["COMP-001"]},
            {"req_id": "REQ-002", "description": "User dashboard", "mapped_components": ["COMP-002"]},
        ],
        "wp_file_mapping": {
            "COMP-001": {"expected_outputs": ["src/gateway/"]},
            "COMP-002": {"expected_outputs": ["src/frontend/"]},
        },
        "domain_details": {
            "pricing_model": {"tiers": ["free", "pro"]},
        },
    }


@pytest.fixture
def good_wp_structure():
    """A well-formed decomposer output."""
    return {
        "work_packages": [
            {
                "id": "WP-001",
                "title": "API Gateway Setup",
                "source_modules": ["COMP-001"],
                "dependencies": [],
                "priority": "high",
                "rationale": "Gateway is the core component",
            },
            {
                "id": "WP-002",
                "title": "Frontend Development",
                "source_modules": ["COMP-002"],
                "dependencies": [{"from": "WP-001", "to": "WP-002", "reason": "Needs API"}],
                "priority": "medium",
                "rationale": "UI depends on API being ready",
            },
        ],
    }


@pytest.fixture
def good_specs():
    """A well-formed specifier output that should PASS."""
    return {
        "work_package_specs": [
            {
                "id": "WP-001",
                "title": "API Gateway Setup",
                "budget": {"tokens": 50000, "time_minutes": 120, "max_retries": 3},
                "complexity": "medium",
                "outputs": ["src/gateway/main.go", "src/gateway/router.go"],
                "acceptance_criteria": [
                    "POST /v1/chat/completions returns 200 status code with valid JSON response",
                    "curl http://localhost:8080/health returns 200 with exit code 0",
                    "pytest tests/test_gateway.py passes with coverage > 80%",
                ],
                "requirements": ["REQ-001"],
                "context_files": ["docs/api-spec.md"],
                "acceptance_tests": ["pytest tests/test_gateway.py"],
                "model_tier": "claude-sonnet",
                "dependencies": [],
                "priority": "high",
            },
            {
                "id": "WP-002",
                "title": "Frontend Development",
                "budget": {"tokens": 80000, "time_minutes": 240, "max_retries": 3},
                "complexity": "complex",
                "outputs": ["src/frontend/pages/index.tsx", "src/frontend/components/Dashboard.tsx"],
                "acceptance_criteria": [
                    "npm run build completes with exit code 0",
                    "Lighthouse performance score >= 80 on landing page",
                    "curl http://localhost:3000 returns 200 status code",
                ],
                "requirements": ["REQ-002"],
                "context_files": ["src/gateway/api-spec.json"],
                "acceptance_tests": ["npm run test"],
                "model_tier": "claude-sonnet",
                "dependencies": ["WP-001"],
                "priority": "medium",
            },
        ],
    }


@pytest.fixture
def good_package():
    """A well-formed packager output (ship_package)."""
    return {
        "schema_version": "3.0.0",
        "meta": {
            "package_id": "SP-001",
            "generated_at": "2026-06-19T01:00:00+08:00",
            "generator": {"agent": "ship-pro", "model": "test", "version": "3.0.0"},
            "source_session_id": "test-session",
        },
        "project_context": {
            "problem_statement": "Test problem",
            "solution_overview": "Test solution",
        },
        "work_packages": [
            {
                "id": "WP-001",
                "title": "API Gateway",
                "objective": "Build the API gateway",
                "budget": {"tokens": 50000, "time_minutes": 120, "max_retries": 3},
                "complexity": "medium",
                "dependencies": [],
                "priority": "high",
                "outputs": [{"type": "file", "path": "src/gateway/main.go", "description": "API gateway entry"}],
                "acceptance_criteria": [
                    "POST /v1/chat/completions returns 200 status code",
                    "curl http://localhost:8080/health returns 200 with exit code 0",
                ],
            },
            {
                "id": "WP-002",
                "title": "Frontend",
                "objective": "Build the frontend UI",
                "budget": {"tokens": 80000, "time_minutes": 240, "max_retries": 3},
                "complexity": "high",
                "dependencies": ["WP-001"],
                "priority": "medium",
                "outputs": [{"type": "file", "path": "src/frontend/pages/index.tsx", "description": "Frontend UI"}],
                "acceptance_criteria": [
                    "npm run build completes with exit code 0",
                    "Lighthouse performance score >= 80",
                ],
            },
        ],
        "dependency_graph": {
            "execution_order": ["WP-001", "WP-002"],
            "parallel_groups": [["WP-001"], ["WP-002"]],
            "edges": [{"from": "WP-002", "to": "WP-001"}],
        },
        "summary": {
            "total_wps": 2,
            "estimated_effort": "2 days",
        },
    }


@pytest.fixture
def bad_specs_all_empty():
    """Specifier output with all critical fields empty — should FAIL."""
    return {
        "work_package_specs": [
            {
                "wp_id": "WP-001",  # Wrong field name
                "title": "Task 1",
                "budget": None,
                "complexity": None,
                "outputs": [],
                "acceptance_criteria": [],
                "dependencies": [],
            },
            {
                "wp_id": "WP-002",
                "title": "Task 2",
                "budget": None,
                "complexity": None,
                "outputs": [],
                "acceptance_criteria": [],
                "dependencies": [],
            },
        ],
    }


# ===========================================================================
# 1. Gate Architect Tests
# ===========================================================================

class TestGateArchitect:
    def test_good_blueprint_passes(self, good_blueprint):
        result = gate_architect(good_blueprint)
        assert result["decision"] == "PASS", f"Expected PASS, got {result['decision']}: {result['feedback']}"
        assert result["passed"] is True
        assert all(result["critical_results"].values())

    def test_empty_modules_fails(self, good_blueprint):
        good_blueprint["modules"] = []
        result = gate_architect(good_blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["modules_non_empty"] is False

    def test_cyclic_dependencies_fails(self, good_blueprint):
        # Add a cycle: COMP-001 → COMP-002 → COMP-001
        good_blueprint["dependencies"] = [
            {"from": "COMP-001", "to": "COMP-002"},
            {"from": "COMP-002", "to": "COMP-001"},
        ]
        result = gate_architect(good_blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["dependencies_acyclic"] is False

    def test_empty_requirements_fails(self, good_blueprint):
        good_blueprint["requirements"] = []
        result = gate_architect(good_blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["requirements_non_empty"] is False

    def test_missing_project_type_conditional(self, good_blueprint):
        del good_blueprint["project_type"]
        result = gate_architect(good_blueprint)
        # Only 1 major failure out of 2 = 50% > 50% threshold? No, 50% is not > 50%
        # So it should be PASS with minor notes about major failures
        # Actually: len(major_failures)=1, len(major)=2, 1 > 2*0.5=1.0? No, 1 is not > 1.0
        assert result["decision"] == "PASS"
        assert result["major_results"]["project_type_exists"] is False

    def test_missing_all_major_fields_conditional(self, good_blueprint):
        """Both major fields missing → >50% major failures → CONDITIONAL."""
        del good_blueprint["project_type"]
        for req in good_blueprint["requirements"]:
            del req["mapped_components"]
        # Add a consistency issue to push failures over threshold
        # (4 major checks now: requirements_mapped, project_type_exists, internal_consistency, implementation_phase_consistency)
        good_blueprint["architecture_principles"] = [
            {"id": "P1", "anti_patterns": ["自建测试模块"]}
        ]
        good_blueprint["modules"][0]["responsibilities"] = ["测试模块"]
        result = gate_architect(good_blueprint)
        # 3 failures out of 4 (75%) → >50% → CONDITIONAL
        assert result["decision"] == "CONDITIONAL"

    def test_missing_minor_fields_still_passes(self, good_blueprint):
        del good_blueprint["wp_file_mapping"]
        good_blueprint["domain_details"] = {}
        result = gate_architect(good_blueprint)
        assert result["decision"] == "PASS"
        assert result["minor_results"]["wp_file_mapping_exists"] is False
        assert result["minor_results"]["domain_details_non_empty"] is False

    def test_real_pipeline_data(self):
        """Test against real architect output."""
        data = _load_json("architect")
        result = gate_architect(data)
        # Real data has modules, deps, requirements but no project_type/wp_file_mapping
        assert result["critical_results"]["modules_non_empty"] is True
        assert result["critical_results"]["dependencies_acyclic"] is True
        assert result["critical_results"]["requirements_non_empty"] is True
        # Should PASS or CONDITIONAL (missing project_type + mapped_components)
        assert result["decision"] in ("PASS", "CONDITIONAL"), \
            f"Expected PASS/CONDITIONAL, got {result['decision']}: {result['feedback']}"


# ===========================================================================
# 2. Gate Decomposer Tests
# ===========================================================================

class TestGateDecomposer:
    def test_good_structure_passes(self, good_wp_structure, good_blueprint):
        result = gate_decomposer(good_wp_structure, good_blueprint)
        assert result["decision"] == "PASS", f"Expected PASS: {result['feedback']}"
        assert result["passed"] is True

    def test_empty_wps_fails(self, good_blueprint):
        result = gate_decomposer({"work_packages": []}, good_blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["wps_non_empty"] is False

    def test_incomplete_module_coverage_fails(self, good_blueprint):
        """WP only covers COMP-001 but not COMP-002."""
        wp_struct = {
            "work_packages": [
                {
                    "id": "WP-001",
                    "title": "Gateway only",
                    "source_modules": ["COMP-001"],
                    "dependencies": [],
                    "rationale": "Only gateway",
                },
            ],
        }
        result = gate_decomposer(wp_struct, good_blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["module_coverage_100"] is False

    def test_cyclic_wp_dependencies_fails(self):
        wp_struct = {
            "work_packages": [
                {"id": "WP-001", "source_modules": ["COMP-001"], "dependencies": ["WP-002"], "rationale": "test"},
                {"id": "WP-002", "source_modules": ["COMP-002"], "dependencies": ["WP-001"], "rationale": "test"},
            ],
        }
        blueprint = {"modules": [{"id": "COMP-001"}, {"id": "COMP-002"}]}
        result = gate_decomposer(wp_struct, blueprint)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["dependencies_acyclic"] is False

    def test_missing_source_modules_conditional(self, good_blueprint):
        wp_struct = {
            "work_packages": [
                {"id": "WP-001", "source_modules": [], "dependencies": [], "rationale": "test"},
                {"id": "WP-002", "source_modules": ["COMP-002"], "dependencies": ["WP-001"], "rationale": "test"},
            ],
        }
        result = gate_decomposer(wp_struct, good_blueprint)
        # module_coverage: COMP-001 not covered → FAIL
        # Actually this will FAIL on module_coverage first
        assert result["critical_results"]["module_coverage_100"] is False

    def test_missing_rationale_major(self, good_blueprint):
        wp_struct = {
            "work_packages": [
                {"id": "WP-001", "source_modules": ["COMP-001"], "dependencies": [], "rationale": ""},
                {"id": "WP-002", "source_modules": ["COMP-002"], "dependencies": ["WP-001"], "rationale": ""},
            ],
        }
        result = gate_decomposer(wp_struct, good_blueprint)
        # Both WPs missing rationale → 100% major failure → CONDITIONAL
        assert result["major_results"]["all_wps_have_rationale"] is False
        assert result["decision"] in ("CONDITIONAL", "FAIL")

    def test_real_pipeline_data(self):
        """Test against real decomposer + architect output."""
        decomp = _load_json("decomposer")
        arch = _load_json("architect")
        result = gate_decomposer(decomp, arch)
        assert result["decision"] == "PASS", \
            f"Expected PASS for real decomposer, got {result['decision']}: {result['feedback']}"


# ===========================================================================
# 3. Gate Specifier Tests (★ most critical)
# ===========================================================================

class TestGateSpecifier:
    def test_good_specs_passes(self, good_specs):
        result = gate_specifier(good_specs)
        assert result["decision"] == "PASS", f"Expected PASS: {result['feedback']}"
        assert result["passed"] is True
        assert all(result["critical_results"].values())

    def test_all_empty_fails(self, bad_specs_all_empty):
        """All critical fields empty → FAIL."""
        result = gate_specifier(bad_specs_all_empty)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["budget_filled"] is False
        assert result["critical_results"]["complexity_filled"] is False
        assert result["critical_results"]["outputs_non_empty"] is False
        assert result["critical_results"]["ac_non_empty"] is False
        assert result["critical_results"]["schema_field_names"] is False  # uses wp_id

    def test_wp_id_field_name_fails(self):
        """Using wp_id instead of id should fail schema_field_names."""
        specs = {
            "work_package_specs": [
                {
                    "wp_id": "WP-001",
                    "budget": {"tokens": 5000},
                    "complexity": "simple",
                    "outputs": ["file.go"],
                    "acceptance_criteria": [
                        "pytest tests pass with exit code 0",
                        "curl http://localhost:8080 returns 200 status code",
                    ],
                },
            ],
        }
        result = gate_specifier(specs)
        assert result["critical_results"]["schema_field_names"] is False

    def test_null_budget_fails(self, good_specs):
        for wp in good_specs["work_package_specs"]:
            wp["budget"] = None
        result = gate_specifier(good_specs)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["budget_filled"] is False

    def test_null_complexity_fails(self, good_specs):
        for wp in good_specs["work_package_specs"]:
            wp["complexity"] = None
        result = gate_specifier(good_specs)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["complexity_filled"] is False

    def test_empty_outputs_fails(self, good_specs):
        for wp in good_specs["work_package_specs"]:
            wp["outputs"] = []
        result = gate_specifier(good_specs)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["outputs_non_empty"] is False

    def test_single_ac_fails(self, good_specs):
        """Each WP needs ≥2 ACs."""
        for wp in good_specs["work_package_specs"]:
            wp["acceptance_criteria"] = ["only one AC here"]
        result = gate_specifier(good_specs)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["ac_non_empty"] is False

    def test_missing_requirements_major(self, good_specs):
        for wp in good_specs["work_package_specs"]:
            wp["requirements"] = []
        result = gate_specifier(good_specs)
        assert result["major_results"]["requirements_non_empty"] is False

    def test_minor_fields_missing_still_passes(self, good_specs):
        """Missing minor fields should not cause failure."""
        for wp in good_specs["work_package_specs"]:
            wp["context_files"] = []
            wp["acceptance_tests"] = []
            wp["model_tier"] = None
        result = gate_specifier(good_specs)
        assert result["decision"] == "PASS"
        assert result["minor_results"]["context_files_filled"] is False
        assert result["minor_results"]["acceptance_tests_filled"] is False
        assert result["minor_results"]["model_tier_filled"] is False

    def test_empty_specs_fails(self):
        result = gate_specifier({"work_package_specs": []})
        assert result["decision"] == "FAIL"

    def test_real_pipeline_data_should_fail(self):
        """★ Real specifier output has budget/complexity/outputs all null → MUST FAIL."""
        data = _load_json("specifier")
        result = gate_specifier(data)
        assert result["decision"] == "FAIL", \
            f"Real specifier output should FAIL but got {result['decision']}: {result['feedback']}"
        # Verify specific critical failures
        assert result["critical_results"]["budget_filled"] is False
        assert result["critical_results"]["complexity_filled"] is False
        assert result["critical_results"]["outputs_non_empty"] is False
        assert result["critical_results"]["schema_field_names"] is False  # uses wp_id

    def test_ac_objects_accepted_for_scoring(self):
        """AC as objects (with description/verification) should be scored correctly."""
        specs = {
            "work_package_specs": [
                {
                    "id": "WP-001",
                    "budget": {"tokens": 5000},
                    "complexity": "simple",
                    "outputs": ["file.go"],
                    "acceptance_criteria": [
                        {
                            "description": "API endpoint returns 200",
                            "verification": "curl http://localhost:8080/health returns 200 status code",
                        },
                        {
                            "description": "Database connection works",
                            "verification": "pytest tests/test_db.py passes with exit code 0",
                        },
                    ],
                    "requirements": ["REQ-001"],
                },
            ],
        }
        result = gate_specifier(specs)
        assert result["critical_results"]["ac_non_empty"] is True
        assert result["decision"] == "PASS"

    def test_single_wp_passes(self):
        """Edge case: single WP."""
        specs = {
            "work_package_specs": [
                {
                    "id": "WP-001",
                    "budget": {"tokens": 5000},
                    "complexity": "simple",
                    "outputs": ["file.go"],
                    "acceptance_criteria": [
                        "pytest tests pass with exit code 0",
                        "curl http://localhost:8080 returns 200 status code",
                    ],
                    "requirements": ["REQ-001"],
                    "context_files": ["README.md"],
                    "acceptance_tests": ["pytest"],
                    "model_tier": "fast",
                },
            ],
        }
        result = gate_specifier(specs)
        assert result["decision"] == "PASS"

    def test_many_wps_passes(self):
        """Edge case: 10+ WPs all properly filled."""
        wps = []
        for i in range(1, 13):
            wps.append({
                "id": f"WP-{i:03d}",
                "budget": {"tokens": 5000 * i},
                "complexity": "simple" if i <= 4 else "medium",
                "outputs": [f"output_{i}.go"],
                "acceptance_criteria": [
                    f"pytest tests/test_{i}.py passes with exit code 0",
                    f"curl http://localhost:{8080+i}/health returns 200 status code",
                ],
                "requirements": [f"REQ-{i:03d}"],
                "context_files": [f"docs/{i}.md"],
                "acceptance_tests": [f"pytest tests/test_{i}.py"],
                "model_tier": "fast",
                "dependencies": [f"WP-{i-1:03d}"] if i > 1 else [],
            })
        specs = {"work_package_specs": wps}
        result = gate_specifier(specs)
        assert result["decision"] == "PASS"


# ===========================================================================
# 4. Gate Packager Tests
# ===========================================================================

class TestGatePackager:
    def test_good_package_passes(self, good_package):
        result = gate_packager(good_package)
        assert result["decision"] == "PASS", f"Expected PASS: {result['feedback']}"
        assert result["passed"] is True

    def test_schema_violation_fails(self, good_package):
        # Remove required field
        del good_package["work_packages"][0]["budget"]
        result = gate_packager(good_package)
        assert result["decision"] == "FAIL"
        assert result["critical_results"]["schema_compliant"] is False

    def test_ac_as_objects_fails(self, good_package):
        """AC as objects instead of strings should fail ac_text_not_count."""
        for wp in good_package["work_packages"]:
            wp["acceptance_criteria"] = [
                {"description": "test", "verification": "curl returns 200"}
            ]
        result = gate_packager(good_package)
        assert result["critical_results"]["ac_text_not_count"] is False

    def test_cyclic_dependency_graph_fails(self, good_package):
        good_package["dependency_graph"]["edges"] = [
            {"from": "WP-001", "to": "WP-002"},
            {"from": "WP-002", "to": "WP-001"},
        ]
        result = gate_packager(good_package)
        assert result["critical_results"]["dependency_graph_acyclic"] is False

    def test_missing_summary_conditional(self, good_package):
        good_package["summary"] = {}
        result = gate_packager(good_package)
        # Empty summary → summary_exists=False (1 major failure out of 2 = 50%)
        # 1 > 2*0.5=1.0? No → PASS
        assert result["major_results"]["summary_exists"] is False

    def test_wp_mismatch_major(self, good_package):
        """Execution order references WPs that don't exist."""
        good_package["dependency_graph"]["execution_order"] = ["WP-001", "WP-002", "WP-999"]
        result = gate_packager(good_package)
        assert result["major_results"]["all_wps_present"] is False

    def test_real_pipeline_data(self):
        """Test against real packager output."""
        data = _load_json("packager")
        result = gate_packager(data)
        # Real data has budget=null, complexity=null, AC as objects → should FAIL
        assert result["decision"] == "FAIL", \
            f"Real packager output should FAIL but got {result['decision']}: {result['feedback']}"


# ===========================================================================
# 5. Helper Function Tests
# ===========================================================================

class TestHelpers:
    def test_acyclic_linear(self):
        adj = {"A": [], "B": ["A"], "C": ["B"]}
        assert _check_acyclic_from_adj(adj) is True

    def test_acyclic_cycle(self):
        adj = {"A": ["B"], "B": ["A"]}
        assert _check_acyclic_from_adj(adj) is False

    def test_acyclic_self_loop(self):
        adj = {"A": ["A"]}
        assert _check_acyclic_from_adj(adj) is False

    def test_acyclic_empty(self):
        assert _check_acyclic_from_adj({}) is True

    def test_acyclic_diamond(self):
        adj = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]}
        assert _check_acyclic_from_adj(adj) is True

    def test_normalize_deps_strings(self):
        wps = [
            {"id": "WP-001", "dependencies": []},
            {"id": "WP-002", "dependencies": ["WP-001"]},
        ]
        adj = _normalize_deps_to_adj(wps)
        assert adj == {"WP-001": [], "WP-002": ["WP-001"]}

    def test_normalize_deps_objects(self):
        wps = [
            {"id": "WP-001", "dependencies": []},
            {"id": "WP-002", "dependencies": [{"from": "WP-001", "to": "WP-002"}]},
        ]
        adj = _normalize_deps_to_adj(wps)
        assert adj["WP-002"] == ["WP-001"]


# ===========================================================================
# 6. Tiered Decision Logic Tests
# ===========================================================================

class TestTieredDecision:
    """Verify that Critical→FAIL, Major→CONDITIONAL, Minor→PASS."""

    def test_critical_failure_always_fails(self):
        """Even one Critical failure → FAIL regardless of other tiers."""
        blueprint = {
            "modules": [],  # Critical fail
            "dependencies": [],
            "requirements": [{"req_id": "R1", "mapped_components": ["C1"]}],
            "project_type": "greenfield",
            "wp_file_mapping": {"C1": {}},
            "domain_details": {"key": "val"},
        }
        result = gate_architect(blueprint)
        assert result["decision"] == "FAIL"

    def test_major_failure_can_be_conditional(self):
        """Major failures > threshold → CONDITIONAL (not FAIL)."""
        blueprint = {
            "modules": [{"id": "C1", "responsibilities": ["自建限流器"]}],
            "dependencies": [],
            "requirements": [{"req_id": "R1"}],  # No mapped_components
            # No project_type
            "architecture_principles": [
                {"id": "P1", "anti_patterns": ["自建限流器"]}
            ],
            "implementation_hints": [
                {"phase": "Phase 1"},
                {"phase": "Phase 2"}
            ]
        }
        result = gate_architect(blueprint)
        # 4 major failures out of 4 (100%) → >50% → CONDITIONAL
        # (requirements_mapped, project_type_exists, internal_consistency, implementation_phase_consistency)
        assert result["decision"] == "CONDITIONAL"
        assert result["passed"] is True  # CONDITIONAL still passes

    def test_minor_failure_still_passes(self):
        """Minor failures → PASS (just recorded)."""
        blueprint = {
            "modules": [{"id": "C1"}],
            "dependencies": [],
            "requirements": [{"req_id": "R1", "mapped_components": ["C1"]}],
            "project_type": "greenfield",
            # No wp_file_mapping (minor)
            # No domain_details (minor)
        }
        result = gate_architect(blueprint)
        assert result["decision"] == "PASS"
        assert result["passed"] is True
        assert result["minor_results"]["wp_file_mapping_exists"] is False


# ===========================================================================
# 7. Integration: Full Pipeline Gate Sequence
# ===========================================================================

class TestFullPipeline:
    """Run all 4 gates in sequence against real data."""

    def test_full_pipeline_real_data(self):
        """
        Expected results for real crossborder pipeline:
        - Architect: PASS or CONDITIONAL (good structure, missing project_type)
        - Decomposer: PASS (good coverage and structure)
        - Specifier: FAIL (budget/complexity/outputs all null)
        - Packager: FAIL (schema violations from null fields)
        """
        arch = _load_json("architect")
        decomp = _load_json("decomposer")
        spec = _load_json("specifier")
        pack = _load_json("packager")

        r1 = gate_architect(arch)
        r2 = gate_decomposer(decomp, arch)
        r3 = gate_specifier(spec)
        r4 = gate_packager(pack)

        # Architect should be reasonable
        assert r1["decision"] in ("PASS", "CONDITIONAL"), \
            f"Architect: {r1['decision']} — {r1['feedback']}"

        # Decomposer should pass
        assert r2["decision"] == "PASS", \
            f"Decomposer: {r2['decision']} — {r2['feedback']}"

        # ★ Specifier MUST fail (this is the key test case)
        assert r3["decision"] == "FAIL", \
            f"Specifier: {r3['decision']} — {r3['feedback']}"

        # Packager should fail due to propagated issues
        assert r4["decision"] == "FAIL", \
            f"Packager: {r4['decision']} — {r4['feedback']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
