import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from domains.spec_pro.merge_spec import merge_spec


ROOT = Path(__file__).resolve().parents[2]


def test_merge_user_directives_from_parsed_updates_into_confirmed(tmp_path):
    response_path = tmp_path / "response.json"
    living_spec_path = tmp_path / "living_spec.json"
    response_path.write_text(
        json.dumps(
            {
                "parsed_updates": {
                    "user_directives": [
                        {
                            "dimension": "users",
                            "directive": "deliberately_omitted",
                            "reason": "用户明确不想继续讨论用户角色",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    living_spec_path.write_text(
        json.dumps(
            {
                "meta": {},
                "confirmed": {},
                "inferred": [],
                "guardrails": {"always_do": [], "ask_first": [], "never_do": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = merge_spec(str(response_path), str(living_spec_path))

    assert result["status"] == "merged"
    living_spec = json.loads(living_spec_path.read_text(encoding="utf-8"))
    assert living_spec["confirmed"]["user_directives"] == [
        {
            "dimension": "users",
            "directive": "deliberately_omitted",
            "reason": "用户明确不想继续讨论用户角色",
        }
    ]
    assert "user_directives" not in living_spec


def test_merge_spec_cli_exits_nonzero_on_error(tmp_path):
    living_spec_path = tmp_path / "living_spec.json"
    living_spec_path.write_text(
        json.dumps({"meta": {}, "confirmed": {}, "inferred": [], "guardrails": {}}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "domains/spec_pro/merge_spec.py"),
            str(tmp_path / "missing_response.json"),
            str(living_spec_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    assert '"status": "error"' in proc.stdout


def test_spec_pro_entrypoints_bootstrap_project_path(tmp_path):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for script in [
        ROOT / "domains/spec_pro/spec_pro_api.py",
        ROOT / "scripts/runners/run_spec_pro.py",
    ]:
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr


def test_read_output_persists_reconstructed_state(tmp_path, monkeypatch):
    from domains.spec_pro import spec_pro_api

    session_id = "spec_test_state"
    session_path = tmp_path / "blackboard" / session_id
    spec_path = session_path / "spec"
    spec_path.mkdir(parents=True)
    (spec_path / "round_result.json").write_text(
        json.dumps({"action": "summary"}), encoding="utf-8"
    )
    (session_path / "coord_state.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "base_path": str(session_path),
                "scenario": "genesis",
                "mode": "standard",
                "current_round": 2,
                "state": "asking",
            }
        ),
        encoding="utf-8",
    )
    # Patch BlackboardManager to use tmp_path/blackboard as base_dir
    from domains.spec_pro.blackboard import BlackboardManager as _BM
    _orig_init = _BM.__init__
    def _patched_init(self, sid, base_dir=None, **kw):
        _orig_init(self, sid, base_dir=str(tmp_path / "blackboard"), **kw)
    monkeypatch.setattr(_BM, "__init__", _patched_init)

    result = spec_pro_api.cmd_read_output(SimpleNamespace(session_id=session_id))

    assert result["success"] is True
    persisted = json.loads((session_path / "coord_state.json").read_text(encoding="utf-8"))
    assert persisted["state"] == "confirming"
