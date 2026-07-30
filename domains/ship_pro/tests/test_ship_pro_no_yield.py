"""Verify Ship Pro Orchestrator prompt uses blocking wait, not yield/cron-wake.

V8_DECISIONS.md (line 172) originally declared: 禁止 sessions_yield（用 cron wake 替代）
FixFlow 2026-07-30: 进一步改为 wait_for_module() 阻塞等待（不再依赖 cron wake）。
This test ensures the Orchestrator prompt complies with the new architecture.
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
    """Orchestrator prompt must not instruct to yield (yield = dead risk).

    FixFlow 2026-07-30: 排除否定模式（"不要 yield"、"禁止 yield" 是合法的禁止指令）。
    """
    prompt = _orchestrator_prompt()
    # Check for yield-related instruction patterns (positive instructions only)
    patterns = [
        r"调用\s*sessions_yield",
        r"必须.*yield",
    ]
    violations = []
    for pat in patterns:
        for m in re.finditer(pat, prompt):
            line_no = prompt[:m.start()].count("\n") + 1
            line_text = prompt.split("\n")[line_no - 1]
            # Exclude negative instructions ("不要 yield", "禁止 yield", "不要yield")
            if re.search(r"不要\s*yield|禁止\s*yield|不要yield", line_text):
                continue
            violations.append(f"  line {line_no}: pattern '{pat}' matched '{m.group()}'")

    assert not violations, (
        f"Found {len(violations)} yield instruction(s) in Orchestrator prompt:\n"
        + "\n".join(violations)
        + "\nFixFlow 2026-07-30: 必须用 wait_for_module() 阻塞等待，不要 yield。"
    )


def test_wait_for_module_mentioned():
    """Orchestrator prompt should mention wait_for_module as the waiting mechanism.

    FixFlow 2026-07-30: 架构从 cron wake 改为 wait_for_module() 阻塞等待。
    """
    prompt = _orchestrator_prompt()
    assert "wait_for_module" in prompt, (
        "Orchestrator prompt does not mention 'wait_for_module' — "
        "expected wait_for_module() to be documented as the waiting mechanism."
    )
