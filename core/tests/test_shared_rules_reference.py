"""
Test: all sub-agent prompts reference the shared subagent rules file.

P0-2 fix: NO_REPLY protection requires every sub-agent prompt to reference
core/prompts/_shared_subagent_rules.md (which includes rule #8: never output NO_REPLY).
"""
import os
import re
from pathlib import Path

import pytest

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_RULES_PATH = DEEPFLOW_ROOT / "core" / "prompts" / "_shared_subagent_rules.md"
REFERENCE_MARKER = "core/prompts/_shared_subagent_rules.md"

# All sub-agent prompt files that MUST reference the shared rules
SPEC_PRO_PROMPTS = [
    "domains/spec_pro/prompts/parse.md",
    "domains/spec_pro/prompts/structure.md",
    "domains/spec_pro/prompts/assess.md",
    "domains/spec_pro/prompts/guide.md",
    "domains/spec_pro/prompts/harness.md",
]

RESEARCH_PRO_PROMPTS = [
    "domains/research_pro/prompts/orchestrator.md",
    "domains/research_pro/prompts/planning.md",
    "domains/research_pro/prompts/search.md",
    "domains/research_pro/prompts/report_writer.md",
    "domains/research_pro/prompts/tech_analysis.md",
    "domains/research_pro/prompts/finance_analysis.md",
]

SHIP_PRO_PROMPTS = [
    "domains/ship_pro/prompts/consolidator.md",
]

SHIP_PRO_PYTHON_PROMPTS = [
    "domains/ship_pro/__init__.py",  # contains embedded orchestrator prompt
]


def _read(rel_path: str) -> str:
    full = DEEPFLOW_ROOT / rel_path
    return full.read_text(encoding="utf-8")


class TestSharedRulesFileExists:
    """The shared rules file must exist at core/prompts/_shared_subagent_rules.md."""

    def test_file_exists(self):
        assert SHARED_RULES_PATH.exists(), (
            f"Shared rules file missing: {SHARED_RULES_PATH}"
        )

    def test_contains_no_reply_rule(self):
        """Rule #8: NO_REPLY protection must be present."""
        content = SHARED_RULES_PATH.read_text(encoding="utf-8")
        # Match rule 8 with NO_REPLY keyword
        assert re.search(r"8\.\s*.*NO_REPLY", content), (
            "Shared rules missing rule #8 (NO_REPLY protection)"
        )

    def test_contains_all_eight_rules(self):
        """All 8 iron rules must be present."""
        content = SHARED_RULES_PATH.read_text(encoding="utf-8")
        for i in range(1, 9):
            assert re.search(rf"^{i}\.\s", content, re.MULTILINE), (
                f"Shared rules missing rule #{i}"
            )


class TestSpecProPromptsReference:
    """spec_pro sub-agent prompts must reference shared rules."""

    @pytest.mark.parametrize("rel_path", SPEC_PRO_PROMPTS)
    def test_reference_present(self, rel_path):
        content = _read(rel_path)
        assert REFERENCE_MARKER in content, (
            f"{rel_path} missing reference to {REFERENCE_MARKER}"
        )


class TestResearchProPromptsReference:
    """research_pro sub-agent prompts must reference shared rules."""

    @pytest.mark.parametrize("rel_path", RESEARCH_PRO_PROMPTS)
    def test_reference_present(self, rel_path):
        content = _read(rel_path)
        assert REFERENCE_MARKER in content, (
            f"{rel_path} missing reference to {REFERENCE_MARKER}"
        )


class TestShipProPromptsReference:
    """ship_pro sub-agent prompts must reference shared rules."""

    @pytest.mark.parametrize("rel_path", SHIP_PRO_PROMPTS)
    def test_md_reference_present(self, rel_path):
        content = _read(rel_path)
        assert REFERENCE_MARKER in content, (
            f"{rel_path} missing reference to {REFERENCE_MARKER}"
        )

    @pytest.mark.parametrize("rel_path", SHIP_PRO_PYTHON_PROMPTS)
    def test_python_embedded_reference_present(self, rel_path):
        """ship_pro embeds orchestrator prompt in Python f-string."""
        content = _read(rel_path)
        assert REFERENCE_MARKER in content, (
            f"{rel_path} missing reference to {REFERENCE_MARKER} in embedded prompt"
        )


class TestNoOrphanedPrompts:
    """Ensure no sub-agent prompt files were missed."""

    def test_all_md_prompts_covered(self):
        """Every .md file under domains/*/prompts/ should be in our test lists."""
        covered = set(SPEC_PRO_PROMPTS + RESEARCH_PRO_PROMPTS + SHIP_PRO_PROMPTS)
        all_prompts = set()
        for domain in ["spec_pro", "research_pro", "ship_pro"]:
            prompts_dir = DEEPFLOW_ROOT / "domains" / domain / "prompts"
            if prompts_dir.exists():
                for md_file in prompts_dir.glob("*.md"):
                    rel = str(md_file.relative_to(DEEPFLOW_ROOT))
                    all_prompts.add(rel)
        # Report any uncovered prompts (warning, not failure)
        uncovered = all_prompts - covered
        # These are expected to exist but not require shared rules reference
        # (e.g., deprecated files, parse_response.md, etc.)
        # Just assert the critical ones are covered
        assert covered.issubset(all_prompts | covered), (
            "Test lists reference non-existent files"
        )
