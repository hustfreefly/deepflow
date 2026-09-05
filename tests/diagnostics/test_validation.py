"""
Test suite for Diagnostics Validation.

This module contains pytest tests for the 7-item validation checklist
implemented in deepflow.diagnostics.validation.

Run tests with:
    pytest tests/diagnostics/test_validation.py -v
    pytest tests/diagnostics/test_validation.py::test_api_availability -v
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Add src to path for imports
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAG_PKG = REPO_ROOT / "src" / "deepflow" / "diagnostics"
if not DIAG_PKG.exists():
    pytest.skip(
        "src/deepflow/diagnostics 不在当前 checkout（历史 cleanup 已移除），diagnostics 测试停用",
        allow_module_level=True,
    )

class MockDiagnosticsData:
    """Helper to create mock diagnostics data for testing."""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.sessions_dir = temp_dir / "blackboard"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        name: str,
        diagnostics_data: Optional[Dict] = None,
        stage_files: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Create a mock session directory with diagnostics data."""
        session_dir = self.sessions_dir / name
        session_dir.mkdir(exist_ok=True)

        stages_dir = session_dir / "stages"
        stages_dir.mkdir(exist_ok=True)

        # Create diagnostics file
        if diagnostics_data is not None:
            diag_file = session_dir / "diagnostics.json"
            with open(diag_file, "w", encoding="utf-8") as f:
                json.dump(diagnostics_data, f, indent=2)

        # Create stage files
        if stage_files is not None:
            for filename, content in stage_files.items():
                stage_file = stages_dir / filename
                if isinstance(content, dict):
                    with open(stage_file, "w", encoding="utf-8") as f:
                        json.dump(content, f, indent=2)
                else:
                    stage_file.write_text(content)

        return session_dir

# ============================================================================
# Validation Tests
# ============================================================================

class TestDiagnosticsValidation:
    """Test diagnostics validation module."""

    @pytest.fixture
    def mock_data(self, tmp_path: Path) -> MockDiagnosticsData:
        """Create mock diagnostics data for tests."""
        return MockDiagnosticsData(tmp_path)

    def test_api_availability_pass(self, mock_data: MockDiagnosticsData):
        """V-001: API availability - pass case."""
        # Create session with valid JSON containing diagnostics-related keywords
        session_dir = mock_data.create_session(
            "test_session_001",
            diagnostics_data={"tokens": {"input_tokens": 100, "output_tokens": 50}},
            stage_files={
                "planning.json": {
                    "tokens": {"input_tokens": 100, "output_tokens": 50},
                    "cost": 0.01,
                }
            },
        )

        # Patch diagnostics path - directly point to stages directory
        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_api_availability()
            assert result.status == "pass"
            assert result.field_name == "diagnostics JSON"
            assert result.fallback_available is True
        finally:
            validation.find_diagnostics_data = original_path

    def test_api_availability_fail_no_data(self, mock_data: MockDiagnosticsData):
        """V-001: API availability - fail case (no data)."""
        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return None

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_api_availability()
            assert result.status == "fail"
            assert "No diagnostics data" in result.details
        finally:
            validation.find_diagnostics_data = original_path

    def test_cost_field_inferred(self, mock_data: MockDiagnosticsData):
        """V-003: Cost field - inferred when not available."""
        session_dir = mock_data.create_session(
            "test_session_003",
            stage_files={"planning.json": {"tokens": {"input_tokens": 100}}},
        )

        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_cost_field()
            assert result.status == "pass"
            assert "inferred from tokens" in result.field_name
            assert result.fallback_available is True
        finally:
            validation.find_diagnostics_data = original_path

    def test_tokens_field_pass(self, mock_data: MockDiagnosticsData):
        """V-002: Tokens field - pass case."""
        session_dir = mock_data.create_session(
            "test_session_002",
            stage_files={
                "planning.json": {
                    "tokens": {"input_tokens": 100, "output_tokens": 50}
                }
            },
        )

        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_tokens_field()
            assert result.status == "pass"
            assert result.field_name is not None
            assert result.fallback_available is True
        finally:
            validation.find_diagnostics_data = original_path

    def test_worker_phase_association_inferred(self, mock_data: MockDiagnosticsData):
        """V-005: Worker/Phase association - inferred from stage files."""
        session_dir = mock_data.create_session(
            "test_session_005",
            stage_files={
                "planning.json": {"content": "test", "tokens": {"input_tokens": 100}},
                "review_technical.json": {"content": "test", "tokens": {"input_tokens": 100}},
            },
        )

        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_worker_phase_association()
            assert result.status == "pass"
            assert "inferred from stage files" in result.field_name
            assert result.fallback_available is True
        finally:
            validation.find_diagnostics_data = original_path

    def test_run_id_inferred(self, mock_data: MockDiagnosticsData):
        """V-006: Run ID association - inferred from session directory."""
        session_dir = mock_data.create_session(
            "test_session_006",
            stage_files={"planning.json": {"content": "test"}},
        )

        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            result = validation.validate_run_id_association()
            assert result.status == "pass"
            assert "inferred from session directory" in result.field_name
            assert result.fallback_available is True
        finally:
            validation.find_diagnostics_data = original_path

class TestFallbackExtractor:
    """Test fallback duration extractor."""

    @pytest.fixture
    def mock_data(self, tmp_path: Path) -> MockDiagnosticsData:
        """Create mock diagnostics data for tests."""
        return MockDiagnosticsData(tmp_path)

    def test_extract_duration_from_stages(self, mock_data: MockDiagnosticsData):
        """Test duration extraction from stage files."""
        import time

        session_dir = mock_data.create_session(
            "test_duration_session",
            stage_files={
                "planning.json": {"content": "planning"},
                "review_technical.json": {"content": "review"},
                "consolidator.json": {"content": "consolidation"},
            },
        )

        from deepflow.diagnostics.fallback_extractor import (
            extract_duration_from_stages,
        )

        records = extract_duration_from_stages(session_dir)

        assert len(records) == 3
        assert records[0]["stage_file"] == "planning.json"
        #_worker name check is based on STAGE_FILE_MAPPINGS in fallback_extractor
        #For planning.json → inferred_worker="planner" (STAGE_FILE_MAPPINGS value)
        assert records[0]["inferred_worker"] in ["planner", "unknown_worker"]
        assert records[0]["inferred_phase"] in ["planning", "planning"]

        # First record should have no duration (no previous file)
        assert records[0]["duration_seconds"] is None

        # Subsequent records should have duration
        assert records[1]["duration_seconds"] is not None
        assert records[1]["duration_seconds"] >= 0

    def test_infer_stage_name(self, mock_data: MockDiagnosticsData):
        """Test stage name inference."""
        from deepflow.diagnostics.fallback_extractor import infer_stage_name

        # infer_stage_name returns file_path.stem when not in STAGE_FILE_MAPPINGS
        assert infer_stage_name(mock_data.temp_dir / "stages" / "planning.json") == "planning"
        assert infer_stage_name(mock_data.temp_dir / "stages" / "review_technical.json") == "review_technical"
        assert infer_stage_name(mock_data.temp_dir / "stages" / "unknown_file.json") == "unknown_file"

class TestValidationIntegration:
    """Integration tests for full validation workflow."""

    @pytest.fixture
    def mock_data(self, tmp_path: Path) -> MockDiagnosticsData:
        """Create mock diagnostics data for tests."""
        return MockDiagnosticsData(tmp_path)

    def test_full_validation_workflow(self, mock_data: MockDiagnosticsData):
        """Test complete validation workflow with mock data."""
        session_dir = mock_data.create_session(
            "integration_test_session",
            stage_files={
                "planning.json": {
                    "tokens": {"input_tokens": 100, "output_tokens": 50},
                    "cost": 0.01,
                    "duration": 10.5,
                    "worker_id": "agent_planner",
                    "phase_id": "stage_planning",
                    "run_id": "run_integration_001",
                    "model": "gpt-4o",
                    "timestamp": "2026-06-22T10:00:00Z",
                },
                "review_technical.json": {
                    "tokens": {"input_tokens": 150, "output_tokens": 75},
                    "cost": 0.02,
                    "duration": 15.3,
                    "worker_id": "agent_reviewer",
                    "phase_id": "stage_review",
                    "run_id": "run_integration_001",
                    "model": "gpt-4o",
                    "timestamp": "2026-06-22T10:00:30Z",
                },
            },
        )

        from deepflow.diagnostics import validation

        original_path = validation.find_diagnostics_data

        def mock_find():
            return session_dir / "stages"

        validation.find_diagnostics_data = mock_find

        try:
            results = validation.validate_diagnostics()

            # Should have 7 validation results
            assert len(results) == 7

            # Check V-001: API availability
            v001 = next(r for r in results if r["id"] == "V-001")
            assert v001["status"] == "pass"

            # Check V-002: Tokens field
            v002 = next(r for r in results if r["id"] == "V-002")
            assert v002["status"] == "pass"
            assert "tokens" in v002["field_name"].lower()

            # Check V-003: Cost field
            v003 = next(r for r in results if r["id"] == "V-003")
            assert v003["status"] == "pass"
            assert "cost" in v003["field_name"].lower()

        finally:
            validation.find_diagnostics_data = original_path

class TestFieldMapping:
    """Test field mapping functionality."""

    def test_diagnostics_mapping_exists(self):
        """Test that diagnostics mapping file exists and is valid."""
        from pathlib import Path

        # Path relative to workspace root
        mapping_path = Path(__file__).parent.parent.parent / "src" / "deepflow" / "diagnostics" / "diagnostics_mapping.json"

        assert mapping_path.exists(), "diagnostics_mapping.json should exist"

        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        assert "mappings" in mapping
        assert len(mapping["mappings"]) >= 5, "Should have at least 5 field mappings"

        # Check required fields in mapping
        tokens_mapping = next(m for m in mapping["mappings"] if m["field_name"] == "tokens")
        assert tokens_mapping["required"] is True
        assert len(tokens_mapping["source_paths"]) >= 1

    def test_fallback_strategies(self):
        """Test that fallback strategies are defined."""
        from pathlib import Path

        mapping_path = Path(__file__).parent.parent.parent / "src" / "deepflow" / "diagnostics" / "diagnostics_mapping.json"

        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        assert "fallback_strategies" in mapping
        assert len(mapping["fallback_strategies"]) >= 2

        # Check each strategy has required fields
        for strategy in mapping["fallback_strategies"]:
            assert "strategy_id" in strategy
            assert "name" in strategy
            assert "description" in strategy

# ============================================================================
# Test Utilities
# ============================================================================

def find_deepflow_workspace() -> Path:
    """Find DeepFlow workspace directory for integration tests."""
    home = Path.home()
    workspace_paths = [
        home / ".openclaw" / "workspace" / ".deepflow",
        Path.cwd() / ".deepflow",
    ]
    for path in workspace_paths:
        if path.exists():
            return path
    raise FileNotFoundError("DeepFlow workspace not found")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
