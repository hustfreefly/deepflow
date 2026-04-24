"""Contract tests for blackboard_manager module."""

import json
import pytest
from pathlib import Path
from blackboard_manager import BlackboardManager


@pytest.fixture
def bb(tmp_path):
    """Create a BlackboardManager with a temp base dir."""
    mgr = BlackboardManager(session_id="test_001", base_dir=tmp_path)
    mgr.init_session()
    return mgr


class TestBlackboardContract:
    """L1: Interface contract — all public methods exist."""

    def test_write_and_read(self, bb):
        bb.write("plan.md", "# Plan")
        assert bb.read("plan.md") == "# Plan"

    def test_write_dict(self, bb):
        data = {"key": "value", "num": 42}
        bb.write("data.json", data)
        assert bb.read_json("data.json") == data

    def test_read_missing_returns_default(self, bb):
        assert bb.read("nonexistent.md") is None
        assert bb.read("nonexistent.md", default="fallback") == "fallback"

    def test_read_json_invalid_returns_default(self, bb):
        bb.write("bad.json", "not-json{{{")
        result = bb.read_json("bad.json", default={"ok": True})
        assert result == {"ok": True}


class TestSharedStateContract:
    """L2: Shared state behavior."""

    def test_append_state_merges(self, bb):
        bb.append_state({"iteration": 1})
        bb.append_state({"score": 0.85})
        state = bb.get_state()
        assert state["iteration"] == 1
        assert state["score"] == 0.85

    def test_get_state_empty_is_dict(self, bb):
        # fresh session, state should at least be a dict
        assert isinstance(bb.get_state(), dict)


class TestBoundaryContract:
    """L3: Boundary conditions."""

    def test_session_id_empty_raises(self, tmp_path):
        with pytest.raises(ValueError):
            BlackboardManager(session_id="", base_dir=tmp_path)

    def test_atomic_write_creates_parents(self, bb):
        bb.write("sub/nested/file.md", "content")
        assert (Path(bb._session_dir) / "sub" / "nested" / "file.md").exists()

    def test_cleanup_removes_dir(self, tmp_path):
        bb = BlackboardManager(session_id="cleanup_001", base_dir=tmp_path)
        bb.init_session()
        assert bb._session_dir.exists()
        assert bb.cleanup() is True
        assert not bb._session_dir.exists()
