"""Contract tests for the P1 closure: runtime state, memory seed, spawn gate."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT_HOME = Path(
    os.environ.get(
        "DEEPFLOW_AGENT_HOME",
        "/Users/allen/.openclaw/workspace/agent-workspaces/deepflow-dev",
    )
)
AGENT_AVAILABLE = AGENT_HOME.exists()
AGENT_SKIP = pytest.mark.skipif(
    not AGENT_AVAILABLE,
    reason="requires local agent workspace (not available in CI)",
)


def test_core_blackboard_not_ignored():
    p = subprocess.run(
        ["git", "check-ignore", "-q", "core/blackboard/registry_base.py"], cwd=ROOT
    )
    assert p.returncode != 0, "core/blackboard source is still ignored"


def test_registry_base_tracked():
    p = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "core/blackboard/registry_base.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr


def test_worktree_exclude_anchored():
    text = (ROOT / "scripts" / "worktree.sh").read_text(encoding="utf-8")
    assert "--exclude '/blackboard'" in text
    assert "--exclude 'blackboard'" not in text


@AGENT_SKIP
def test_memory_seed_exists():
    path = AGENT_HOME / "MEMORY.md"
    assert path.exists(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    for term in ("DeepFlow", "契约笼子", "tests/contracts"):
        assert term in text, f"missing term: {term}"


@AGENT_SKIP
def test_spawn_gate_documented():
    text = (AGENT_HOME / "assets" / "gates.md").read_text(encoding="utf-8")
    assert "spawn_guard" in text


@AGENT_SKIP
def test_spawn_request_template_exists():
    path = AGENT_HOME / "projects" / "_template" / "spawn-request.json"
    assert path.exists(), f"missing {path}"
