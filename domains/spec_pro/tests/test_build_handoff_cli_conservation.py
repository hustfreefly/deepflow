"""
Track B: build_handoff_cli.py 守恒 Gate fail-closed 校验测试

测试覆盖：
1. gate 文件缺失 → BLOCKED exit 1
2. verdict FAIL → BLOCKED exit 1
3. verdict PASS 但 MUST MISSING（数据不一致）→ BLOCKED exit 1
4. verdict PASS 且全 COVERED → exit 0
"""

import sys as _sys
from pathlib import Path as _Path

_p = _Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _r and str(_r) not in _sys.path:
    _sys.path.insert(0, str(_r))

import json
import subprocess
import tempfile
import pytest
from datetime import datetime

from domains.spec_pro.coordinator import SpecProCoordinator


def _create_session_dir(tmpdir: str) -> "Path":
    """创建满足 density gate 的最小 session 目录。"""
    sd = _Path(tmpdir)
    spec_dir = sd / "spec"
    spec_dir.mkdir()

    living_spec = {
        "topic": "Test Project",
        "objective": "Test objective for validation",
        "core_summary": "Test core summary that is long enough to pass validation checks",
        "narrative": "Test narrative that needs to be at least twenty characters long to pass",
        "semantic_anchors": [],
        "requirement_index": [
            {"id": "REQ-CAP-001", "element": "核心功能", "type": "capability", "verified": True}
        ],
        "meta": {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        "confirmed": {
            "topic": "Test Project",
            "objective": "Test objective",
            "success_metrics": [{"metric": "完成率", "target": "100%"}],
        },
    }
    (spec_dir / "living_spec.json").write_text(json.dumps(living_spec))
    (spec_dir / "quality_report.json").write_text(
        json.dumps({"overall_score": 80, "level": "A", "dimensions": {}})
    )
    return sd


def _run_cli(session_dir: "Path") -> subprocess.CompletedProcess:
    """运行 build_handoff_cli.py。"""
    cli_path = _Path(__file__).resolve().parent.parent / "build_handoff_cli.py"
    return subprocess.run(
        [_sys.executable, str(cli_path), str(session_dir), "--extract-anchors"],
        capture_output=True,
        text=True,
        cwd=str(_r),
    )


class TestConservationGateFailClosed:
    """build_handoff_cli.py 守恒 Gate fail-closed 校验。"""

    def test_gate_file_missing_blocked(self):
        """gate 文件缺失 → BLOCKED exit 1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sd = _create_session_dir(tmpdir)
            result = _run_cli(sd)
            assert result.returncode == 1
            assert "BLOCKED" in result.stderr
            assert "input_conservation_gate.json 不存在" in result.stderr

    def test_verdict_fail_blocked(self):
        """verdict FAIL → BLOCKED exit 1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sd = _create_session_dir(tmpdir)
            gate_data = {
                "verdict": "FAIL",
                "conservation_rate": 0.5,
                "must_missing": [{"id": "E1", "element": "关键功能"}],
                "elements": [],
            }
            (sd / "spec" / "input_conservation_gate.json").write_text(json.dumps(gate_data))
            result = _run_cli(sd)
            assert result.returncode == 1
            assert "BLOCKED" in result.stderr
            assert "verdict=FAIL" in result.stderr

    def test_verdict_pass_but_must_missing_blocked(self):
        """verdict PASS 但 MUST MISSING（数据不一致）→ BLOCKED exit 1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sd = _create_session_dir(tmpdir)
            gate_data = {
                "verdict": "PASS",
                "conservation_rate": 1.0,
                "must_missing": [],
                "elements": [
                    {"id": "E1", "element": "关键功能", "criticality": "MUST", "status": "MISSING"}
                ],
            }
            (sd / "spec" / "input_conservation_gate.json").write_text(json.dumps(gate_data))
            result = _run_cli(sd)
            assert result.returncode == 1
            assert "BLOCKED" in result.stderr
            assert "数据不一致" in result.stderr

    def test_verdict_pass_all_covered_exit_0(self):
        """verdict PASS 且全 COVERED → exit 0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sd = _create_session_dir(tmpdir)
            gate_data = {
                "verdict": "PASS",
                "conservation_rate": 1.0,
                "must_missing": [],
                "elements": [
                    {"id": "E1", "element": "关键功能", "criticality": "MUST", "status": "COVERED"}
                ],
            }
            (sd / "spec" / "input_conservation_gate.json").write_text(json.dumps(gate_data))
            result = _run_cli(sd)
            assert result.returncode == 0
            assert "CONSERVATION_GATE_PASS" in result.stdout


class TestInitSessionRawUserInput:
    """init_session 在生产路径写入 data/raw_user_input.txt。"""

    def test_init_session_writes_raw_user_input(self):
        """init_session 写入 data/raw_user_input.txt（从死代码迁移到生产路径）。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # 切换到临时目录以避免创建真实 session
            import os
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # 创建 .deepflow 结构
                deepflow_root = Path(tmpdir) / ".deepflow"
                deepflow_root.mkdir()
                (deepflow_root / "core" / "blackboard").mkdir(parents=True)
                (deepflow_root / "domains" / "spec_pro").mkdir(parents=True)

                # 初始化 coordinator
                coord = SpecProCoordinator(scenario="genesis", mode="standard")
                user_input = "测试用户输入：构建一个 Python API 服务"
                result = coord.init_session(user_input)

                # 验证 raw_user_input.txt 被写入
                session_dir = Path(result["base_path"])
                raw_input_path = session_dir / "data" / "raw_user_input.txt"
                assert raw_input_path.exists(), f"raw_user_input.txt 未被写入: {raw_input_path}"
                assert raw_input_path.read_text(encoding="utf-8") == user_input
            finally:
                os.chdir(orig_cwd)
