"""Tests for DeliverProStateManager."""

import json

import pytest

from domains.deliver_pro.blackboard import DeliverProBlackboard
from domains.deliver_pro.contracts.pipeline_state import PipelinePhase, PipelineState
from domains.deliver_pro.state_manager import DeliverProStateManager, StateTransitionError


@pytest.fixture
def blackboard(tmp_path):
    return DeliverProBlackboard("test_project", base_dir=tmp_path)


@pytest.fixture
def state_manager(blackboard):
    return DeliverProStateManager(blackboard)


class TestLoadOrInit:
    def test_new_state_initialization(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        assert state.wp_id == "WP-001"
        assert state.phase == PipelinePhase.INIT
        assert state.completed_tasks == []
        assert state.failed_tasks == []

    def test_new_state_persisted(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        # State file should exist now
        assert state_manager.state_file.exists()

    def test_existing_state_restoration(self, state_manager):
        # Create and save a state
        state = state_manager.load_or_init("WP-001")
        state.phase = PipelinePhase.GENERATING
        state.completed_tasks = ["T-001", "T-002"]
        state_manager.save(state)

        # Load again — should restore
        restored = state_manager.load_or_init("WP-001")
        assert restored.wp_id == "WP-001"
        assert restored.phase == PipelinePhase.GENERATING
        assert restored.completed_tasks == ["T-001", "T-002"]

    def test_corrupted_state_file_reinit(self, state_manager):
        # Write garbage to state file
        state_manager.state_dir.mkdir(parents=True, exist_ok=True)
        state_manager.state_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")

        state = state_manager.load_or_init("WP-002")
        assert state.wp_id == "WP-002"
        assert state.phase == PipelinePhase.INIT


class TestSaveReload:
    def test_save_and_reload(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state.round_count = 3
        state.validation_score = 4.2
        state_manager.save(state)

        reloaded = state_manager.load_or_init("WP-001")
        assert reloaded.round_count == 3
        assert abs(reloaded.validation_score - 4.2) < 0.01

    def test_save_updates_timestamp(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        old_ts = state.updated_at
        import time
        time.sleep(0.01)
        state_manager.save(state)
        # updated_at should be refreshed (or at least not earlier)
        assert state.updated_at >= old_ts

    def test_progress_file_written(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state_manager.save(state)
        assert state_manager.progress_file.exists()

        progress = json.loads(state_manager.progress_file.read_text(encoding="utf-8"))
        assert progress["wp_id"] == "WP-001"
        assert progress["phase"] == "INIT"


class TestTransition:
    def test_valid_transition(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state_manager.transition(state, PipelinePhase.ANALYZING)
        assert state.phase == PipelinePhase.ANALYZING

        # Should be persisted
        reloaded = state_manager.load_or_init("WP-001")
        assert reloaded.phase == PipelinePhase.ANALYZING

    def test_invalid_transition_raises(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        with pytest.raises(StateTransitionError, match="Invalid transition"):
            state_manager.transition(state, PipelinePhase.GENERATING)

    def test_full_pipeline_transitions(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state_manager.transition(state, PipelinePhase.ANALYZING)
        state_manager.transition(state, PipelinePhase.GENERATING)
        state_manager.transition(state, PipelinePhase.INTEGRATING)
        state_manager.transition(state, PipelinePhase.VALIDATING)
        state_manager.transition(state, PipelinePhase.PACKAGING)
        state_manager.transition(state, PipelinePhase.COMPLETED)
        assert state.phase == PipelinePhase.COMPLETED
        assert state.completed_at is not None


class TestMarkTaskCompleted:
    def test_mark_task_completed(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state.pending_tasks = ["T-001", "T-002"]
        state.running_tasks = ["T-001"]
        state_manager.save(state)

        state_manager.mark_task_completed(state, "T-001")
        assert "T-001" in state.completed_tasks
        assert "T-001" not in state.pending_tasks
        assert "T-001" not in state.running_tasks

    def test_mark_task_completed_persisted(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state.pending_tasks = ["T-001"]
        state_manager.save(state)

        state_manager.mark_task_completed(state, "T-001")
        reloaded = state_manager.load_or_init("WP-001")
        assert "T-001" in reloaded.completed_tasks


class TestMarkTaskFailed:
    def test_mark_task_failed(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state.pending_tasks = ["T-001"]
        state_manager.save(state)

        state_manager.mark_task_failed(state, "T-001")
        assert "T-001" in state.failed_tasks
        assert "T-001" not in state.pending_tasks

    def test_mark_task_failed_persisted(self, state_manager):
        state = state_manager.load_or_init("WP-001")
        state.running_tasks = ["T-001"]
        state_manager.save(state)

        state_manager.mark_task_failed(state, "T-001")
        reloaded = state_manager.load_or_init("WP-001")
        assert "T-001" in reloaded.failed_tasks


class TestWriteProgressFile:
    def test_write_progress_from_state(self, state_manager):
        state = PipelineState(
            wp_id="WP-001",
            phase=PipelinePhase.GENERATING,
            completed_tasks=["T-001"],
            round_count=2,
        )
        state_manager.write_progress_file(state)

        progress = json.loads(state_manager.progress_file.read_text(encoding="utf-8"))
        assert progress["wp_id"] == "WP-001"
        assert progress["phase"] == "GENERATING"
        assert progress["completed_tasks"] == ["T-001"]
        assert progress["round_count"] == 2

    def test_write_progress_from_file(self, state_manager):
        """When no state passed, reads from state_file."""
        state = state_manager.load_or_init("WP-001")
        state.phase = PipelinePhase.VALIDATING
        state_manager.save(state)

        # Call without state arg
        state_manager.write_progress_file()
        progress = json.loads(state_manager.progress_file.read_text(encoding="utf-8"))
        assert progress["phase"] == "VALIDATING"

    def test_write_progress_no_state_file(self, state_manager):
        """No state file and no state arg → should return silently."""
        state_manager.write_progress_file()
        assert not state_manager.progress_file.exists()
