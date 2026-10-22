"""Active contract cage validation (Cage V2).

Single source of truth for the G3 gate.

Reality this module encodes (verified 2026-10-22):
- contracts live in cage/active/, not in the cage/ root
- 6 pure YAML files and 2 "frontmatter + Markdown" hybrid files
- no single universal schema: identity may be module or component;
  version may be version or cage_version
- an empty contract set must FAIL, never silently pass
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAGE_DIR = ROOT / "cage" / "active"
MIN_CONTRACTS = 6
ALLOWED_STATUS = {"active", "draft", "deprecated"}


@dataclass
class ContractResult:
    path: Path
    meta: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def identity(self) -> str | None:
        if not isinstance(self.meta, dict):
            return None
        value = self.meta.get("module") or self.meta.get("component")
        return str(value) if value else None


def read_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str, str]:
    """Return (metadata, kind, body).

    kind is "frontmatter" when the file starts with a YAML frontmatter block,
    otherwise "yaml". The body is Markdown for hybrid contracts.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None and lines[first].strip() == "---":
        closing = next(
            (i for i in range(first + 1, len(lines)) if lines[i].strip() == "---"),
            None,
        )
        if closing is None:
            return None, "unterminated", text
        block = "\n".join(lines[first + 1 : closing])
        body = "\n".join(lines[closing + 1 :])
        try:
            return yaml.safe_load(block), "frontmatter", body
        except yaml.YAMLError as exc:
            return None, f"yaml-error: {exc}", body
    try:
        return yaml.safe_load(text), "yaml", ""
    except yaml.YAMLError as exc:
        return None, f"yaml-error: {exc}", ""


def validate_contract(path: Path) -> ContractResult:
    result = ContractResult(path=path)
    meta, kind, body = read_frontmatter(path)

    if meta is None:
        result.errors.append(f"metadata parse failed ({kind})")
        return result
    if not isinstance(meta, dict):
        result.errors.append(f"metadata must be a mapping, got {type(meta).__name__}")
        return result

    result.meta = meta

    if not result.identity:
        result.errors.append("missing identity: module or component")
    if not (meta.get("version") or meta.get("cage_version")):
        result.errors.append("missing version: version or cage_version")
    status = meta.get("status")
    if status is None:
        result.errors.append("missing status")
    elif str(status) not in ALLOWED_STATUS:
        result.errors.append(f"invalid status {status!r}, allowed {sorted(ALLOWED_STATUS)}")

    if kind == "frontmatter" and not body.strip():
        result.errors.append("frontmatter contract has empty body")

    return result


def validate_all(
    cage_dir: Path | str | None = None,
    min_contracts: int = MIN_CONTRACTS,
) -> tuple[list[ContractResult], list[str]]:
    """Validate every active contract.

    Returns (results, global_errors). global_errors covers set-level rules
    such as empty discovery and duplicate identities.
    """
    directory = Path(cage_dir) if cage_dir is not None else DEFAULT_CAGE_DIR
    files = sorted(p for p in directory.glob("*.yaml") if p.is_file())
    results = [validate_contract(p) for p in files]
    global_errors: list[str] = []

    if len(files) < min_contracts:
        global_errors.append(
            f"found {len(files)} active contract(s) in {directory}, "
            f"expected at least {min_contracts} (empty set must never pass)"
        )

    seen: dict[str, Path] = {}
    for result in results:
        identity = result.identity
        if not identity:
            continue
        if identity in seen:
            global_errors.append(
                f"duplicate contract identity {identity!r}: "
                f"{seen[identity].name} and {result.path.name}"
            )
        else:
            seen[identity] = result.path

    return results, global_errors


def format_report(results: list[ContractResult], global_errors: list[str]) -> str:
    lines = ["=" * 60, "CAGE V2 CONTRACT VALIDATION", "=" * 60]
    for result in results:
        mark = "OK " if result.valid else "FAIL"
        identity = result.identity or "?"
        lines.append(f"[{mark}] {result.path.name}  ({identity})")
        for warning in result.warnings:
            lines.append(f"       warn: {warning}")
        for error in result.errors:
            lines.append(f"       error: {error}")
    lines.append("-" * 60)
    for error in global_errors:
        lines.append(f"[FAIL] {error}")
    valid = sum(1 for result in results if result.valid)
    lines.append(f"contracts: {valid}/{len(results)} valid")
    failed = bool(global_errors) or any(not result.valid for result in results)
    lines.append("RESULT: FAIL" if failed else "RESULT: PASS")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cage_dir = DEFAULT_CAGE_DIR

    if "--list" in args or "--discover" in args:
        files = sorted(cage_dir.glob("*.yaml"))
        print(f"{len(files)} active contract(s) in {cage_dir}:")
        for path in files:
            print(f"  - {path.name}")
        return 0 if files else 1

    module = next((a for a in args if not a.startswith("-")), None)
    results, global_errors = validate_all(cage_dir, min_contracts=0 if module else MIN_CONTRACTS)

    if module:
        selected = [r for r in results if r.identity == module]
        if not selected:
            print(f"no active contract found for module {module!r}")
            return 1
        results = selected

    print(format_report(results, global_errors))
    return 0 if not global_errors and all(r.valid for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
