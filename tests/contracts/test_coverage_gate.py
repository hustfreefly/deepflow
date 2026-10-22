"""Contract tests for the coverage gate (P0-3)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_supports_coverage_mode():
    text = (ROOT / "scripts" / "ci" / "ci.sh").read_text(encoding="utf-8")
    assert "--coverage" in text
    assert "--cov" in text


def test_pytest_cov_available():
    import pytest_cov  # noqa: F401