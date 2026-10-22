"""G3 gate tests: the active contract cage must fail loudly, never silently pass."""

from pathlib import Path

import pytest

from core.cage.active_contracts import (
    DEFAULT_CAGE_DIR,
    MIN_CONTRACTS,
    main,
    validate_all,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_active_contracts_exist():
    files = sorted(DEFAULT_CAGE_DIR.glob("*.yaml"))
    assert len(files) >= MIN_CONTRACTS, (
        f"expected >= {MIN_CONTRACTS} contracts in {DEFAULT_CAGE_DIR}, got {len(files)}"
    )


def test_every_active_contract_valid():
    results, global_errors = validate_all()
    assert not global_errors, global_errors
    failures = {
        r.path.name: r.errors for r in results if not r.valid
    }
    assert not failures, failures


def test_identities_unique():
    results, _ = validate_all(min_contracts=0)
    identities = [r.identity for r in results if r.identity]
    duplicates = {i for i in identities if identities.count(i) > 1}
    assert not duplicates, f"duplicate identities: {duplicates}"


def test_empty_directory_fails(tmp_path):
    results, global_errors = validate_all(tmp_path, min_contracts=MIN_CONTRACTS)
    assert results == []
    assert global_errors, "empty contract set must produce a global error"


def test_hybrid_frontmatter_contract_parses():
    path = DEFAULT_CAGE_DIR / "deepflow_cleanup_v1.0.yaml"
    assert path.exists()
    results, global_errors = validate_all(min_contracts=1)
    result = next(r for r in results if r.path == path)
    assert result.valid, result.errors
    assert result.meta is not None
    assert result.meta.get("module") == "deepflow_root"


def test_cli_passes_on_real_cage(capsys):
    code = main(["--all"])
    captured = capsys.readouterr().out
    assert code == 0, captured
    assert "RESULT: PASS" in captured


def test_no_temp_scripts_at_repo_root():
    offenders = sorted(p.name for p in REPO_ROOT.glob("_tmp_*.py"))
    assert not offenders, f"temporary scripts must not live in repo root: {offenders}"
