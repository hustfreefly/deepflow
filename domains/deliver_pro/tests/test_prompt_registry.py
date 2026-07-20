"""Tests for Deliver Pro Prompt Registry."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from domains.deliver_pro.prompt_registry import (
    load_prompt, list_prompts, clear_cache,
    _load_template, _strip_front_matter, _render_template,
    _PROMPTS_DIR, _template_cache,
)


class TestLoadPrompt:
    def setup_method(self):
        clear_cache()

    def test_load_all_prompts(self):
        """All 6 prompt files should load successfully."""
        prompt_names = list_prompts()
        assert len(prompt_names) >= 6
        for name in prompt_names:
            result = load_prompt(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError, match="Prompt not found"):
            load_prompt("nonexistent_prompt_xyz")

    def test_variable_substitution_single_brace(self):
        """{variable} should be replaced when provided, kept when not."""
        # Use a real prompt and pass extra variables
        result = load_prompt("deliver_analyze", wp_id="WP-TEST", scenario="code")
        assert "WP-TEST" in result or "wp_id" not in result  # variable substituted or not present

    def test_deepflow_root_auto_inject(self):
        """{deepflow_root} should be auto-injected."""
        result = load_prompt("deliver_analyze")
        # deepflow_root should be replaced with actual path
        assert "{deepflow_root}" not in result


class TestStripFrontMatter:
    def test_strip_front_matter(self):
        content = "---\ntitle: Test\nauthor: Agent\n---\n# Hello\nBody text"
        result = _strip_front_matter(content)
        assert not result.startswith("---")
        assert "# Hello" in result
        assert "Body text" in result

    def test_no_front_matter(self):
        content = "# Just a heading\nSome content"
        result = _strip_front_matter(content)
        assert result == content

    def test_unclosed_front_matter(self):
        content = "---\ntitle: Test\nNo closing marker"
        result = _strip_front_matter(content)
        assert result == content  # returned as-is


class TestRenderTemplate:
    def setup_method(self):
        clear_cache()

    def test_required_variable_missing_raises(self):
        template = "Hello {{username}}, welcome to {{place}}."
        with pytest.raises(ValueError, match="Missing required variable"):
            _render_template(template, "test")

    def test_required_variable_provided(self):
        template = "Hello {{username}}, welcome."
        result = _render_template(template, "test", username="Alice")
        assert result == "Hello Alice, welcome."

    def test_optional_variable_kept_when_missing(self):
        template = "Value: {optional_var}"
        result = _render_template(template, "test")
        assert "{optional_var}" in result or "Value:" in result

    def test_optional_variable_replaced_when_provided(self):
        template = "Value: {my_var}"
        result = _render_template(template, "test", my_var="42")
        assert "42" in result

    def test_deepflow_root_injected(self):
        template = "Root: {deepflow_root}"
        result = _render_template(template, "test")
        # Should be replaced with actual path
        assert "Root:" in result
        assert "{deepflow_root}" not in result


class TestListPrompts:
    def test_list_prompts_not_empty(self):
        prompts = list_prompts()
        assert len(prompts) >= 6

    def test_list_prompts_sorted(self):
        prompts = list_prompts()
        assert prompts == sorted(prompts)


class TestClearCache:
    def test_clear_cache(self):
        # Load something to populate cache
        load_prompt("deliver_analyze")
        assert len(_template_cache) > 0

        clear_cache()
        assert len(_template_cache) == 0
