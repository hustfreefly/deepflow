"""Verify Deliver Pro code does not contain 'sessions_yield' references.

AgentDryRun V3.7 (2026-07-30) 发现：
- orchestrator.py docstring 中有 sessions_yield() 示例代码
- driver.py docstring 中有 "sessions_spawn + yield" 注释
- 但 deliver_pulse.md 明确禁止 sessions_yield

契约笼子修复：物理移除过时注释 + CI 防回归测试。
"""
import re
from pathlib import Path


def _get_deliver_pro_files() -> list[Path]:
    """Get all Python files in deliver_pro directory (excluding tests)."""
    deliver_pro_dir = Path(__file__).resolve().parent.parent
    return [
        f for f in deliver_pro_dir.glob("*.py")
        if f.name != "__init__.py" and "test" not in f.name
    ]


def _is_prohibition_line(line: str) -> bool:
    """Check if a line is a prohibition instruction (e.g., '绝不 sessions_yield')."""
    return bool(re.search(
        r"绝不.*sessions_yield|禁止.*sessions_yield|不要.*sessions_yield|NOT.*sessions_yield",
        line
    ))


def test_no_sessions_yield_in_deliver_pro_code():
    """Deliver Pro code must not contain 'sessions_yield' anywhere (except prohibition lines).

    deliver_pulse.md mandates: "绝不 sessions_yield。绝不等待 worker 完成。"
    """
    violations = []
    for filepath in _get_deliver_pro_files():
        content = filepath.read_text()
        matches = list(re.finditer(r"sessions_yield", content))
        for m in matches:
            line_no = content[:m.start()].count("\n") + 1
            line_text = content.split("\n")[line_no - 1]
            # Exclude prohibition instructions ("绝不 sessions_yield" is a valid prohibition)
            if _is_prohibition_line(line_text):
                continue
            violations.append(f"  {filepath.name}:{line_no}: {line_text.strip()[:80]}")

    assert not violations, (
        f"Found {len(violations)} 'sessions_yield' reference(s) in Deliver Pro code.\n"
        + "\n".join(violations)
        + "\ndeliver_pulse.md mandates: 绝不 sessions_yield。"
        + "\nFixFlow 2026-07-30: Pulse 模式 spawn 后立即结束，不等待。"
    )


def test_no_yield_instruction_in_deliver_pro_docstrings():
    """Deliver Pro docstrings must not instruct to yield."""
    patterns = [
        r"sessions_spawn.*\+\s*yield",
        r"→.*yield",
    ]
    violations = []
    for filepath in _get_deliver_pro_files():
        content = filepath.read_text()
        for pat in patterns:
            for m in re.finditer(pat, content):
                line_no = content[:m.start()].count("\n") + 1
                line_text = content.split("\n")[line_no - 1].strip()
                # Exclude prohibition instructions
                if _is_prohibition_line(line_text):
                    continue
                violations.append(f"  {filepath.name}:{line_no}: {line_text[:60]}")

    assert not violations, (
        f"Found {len(violations)} yield instruction(s) in Deliver Pro docstrings:\n"
        + "\n".join(violations)
        + "\nFixFlow 2026-07-30: Pulse 模式 spawn 后立即结束，不等待。"
    )


def test_deprecated_state_manager_raises():
    """DeliverProStateManager must raise ValueError on instantiation (contract cage)."""
    from domains.deliver_pro.state_manager import DeliverProStateManager

    try:
        DeliverProStateManager(None)
        assert False, "DeliverProStateManager should raise ValueError"
    except ValueError as e:
        assert "DEPRECATED" in str(e)
        assert "contract cage" in str(e).lower()
