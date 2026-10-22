"""Contract tests for network isolation (P0-2)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_network_marker_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(str(m).startswith("network") for m in markers), markers


def test_default_addopts_excludes_network():
    text = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "not network" in text


def test_citation_verifier_marked_network():
    path = ROOT / "domains" / "research_pro" / "tests" / "test_citation_verifier.py"
    text = path.read_text(encoding="utf-8")
    assert "pytest.mark.network" in text