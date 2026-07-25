"""Verify Ship Pro Orchestrator prompt contains no sessions_yield references.

V8_DECISIONS.md (line 172) declares: 禁止 sessions_yield（用 cron wake 替代）
This test ensures the Orchestrator prompt in __init__.py complies with that decision.
"""
import re
from pathlib import Path


def _orchestrator_prompt() -> str:
    """Extract the Orchestrator prompt string from __init__.py."""
    init_path = Path(__file__).resolve().parent.parent / "__init__.py"
    return init_path.read_text()


def test_no_sessions_yield_in_orchestrator_prompt():
    """Orchestrator prompt must not contain 'sessions_yield' anywhere."""
    prompt = _orchestrator_prompt()
    matches = list(re.finditer(r"sessions_yield", prompt))
    assert len(matches) == 0, (
        f"Found {len(matches)} 'sessions_yield' references in Orchestrator prompt. "
        f"V8_DECISIONS.md mandates cron wake instead. "
        f"Lines: {[prompt[:m.start()].count(chr(10)) + 1 for m in matches]}"
    )


def test_no_yield_instruction_in_orchestrator_prompt():
    """Orchestrator prompt must not instruct to yield (yield = dead risk)."""
    prompt = _orchestrator_prompt()
    # Check for yield-related instruction patterns
    patterns = [
        r"调用\s*sessions_yield",
        r"必须.*yield",
        r"立即.*yield",
        r"yield.*等待",
    ]
    violations = []
    for pat in patterns:
        for m in re.finditer(pat, prompt):
            line_no = prompt[:m.start()].count("\n") + 1
            violations.append(f"  line {line_no}: pattern '{pat}' matched '{m.group()}'")

    assert not violations, (
        f"Found {len(violations)} yield instruction(s) in Orchestrator prompt:\n"
        + "\n".join(violations)
        + "\nV8_DECISIONS.md mandates cron wake instead."
    )


def test_cron_wake_mentioned():
    """Orchestrator prompt should mention cron wake as the waiting mechanism."""
    prompt = _orchestrator_prompt()
    assert "cron" in prompt.lower(), (
        "Orchestrator prompt does not mention 'cron' — "
        "expected cron wake to be documented as the waiting mechanism."
    )
