"""E402 白名单守卫：只允许带真实 sys.path bootstrap 的存量文件。"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAX_ALLOWED = 30
REAL_BOOTSTRAP = re.compile(r"^\s*_?sys\.path\.insert", re.M)


def _allowlist() -> list[str]:
    text = PYPROJECT.read_text(encoding="utf-8")
    marker = "[tool.ruff.lint.per-file-ignores]"
    assert marker in text, "missing ruff per-file-ignores section"
    section = text.split(marker, 1)[1].split("\n[", 1)[0]
    return re.findall(r'"([^"]+)"\s*=\s*\["E402"\]', section)


def test_allowlist_is_bounded():
    files = _allowlist()
    assert files, "E402 allowlist must not be empty"
    assert len(files) <= MAX_ALLOWED, (
        f"E402 allowlist grew to {len(files)} (> {MAX_ALLOWED})"
    )


def test_every_allowed_file_has_real_bootstrap():
    for rel in _allowlist():
        path = REPO_ROOT / rel
        assert path.is_file(), f"allowlisted file missing: {rel}"
        assert REAL_BOOTSTRAP.search(path.read_text(encoding="utf-8")), (
            f"{rel} is allowlisted for E402 but has no real sys.path.insert"
        )
