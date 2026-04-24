"""Contract tests for config_loader module."""

import pytest
from pathlib import Path
import yaml
from config_loader import ConfigLoader


@pytest.fixture
def loader(tmp_path):
    """Create ConfigLoader with temp dirs."""
    domains_dir = tmp_path / "domains"
    pipelines_dir = tmp_path / "pipelines"
    domains_dir.mkdir()
    pipelines_dir.mkdir()
    return ConfigLoader(v3_dir=tmp_path), domains_dir, pipelines_dir


class TestConfigLoaderContract:
    """L1: Interface contract — all public methods exist."""

    def test_load_domain_default(self, loader):
        cl, _, _ = loader
        cfg = cl.load_domain("general")
        assert cfg.domain == "general"
        assert cfg.pipeline == "iterative"

    def test_load_domain_from_yaml(self, loader):
        cl, domains_dir, _ = loader
        yaml_data = {
            "domain": "investment",
            "pipeline": "iterative",
            "description": "Investment domain",
        }
        (domains_dir / "investment.yaml").write_text(yaml.dump(yaml_data))
        cfg = cl.load_domain("investment")
        assert cfg.domain == "investment"
        assert cfg.description == "Investment domain"

    def test_load_pipeline_builtin(self, loader):
        cl, _, _ = loader
        tpl = cl.load_pipeline("iterative")
        assert tpl.name == "iterative"
        assert len(tpl.stages) > 0

    def test_load_pipeline_unknown_raises(self, loader):
        cl, _, _ = loader
        with pytest.raises(ValueError):
            cl.load_pipeline("nonexistent_type")

    def test_list_domains(self, loader):
        cl, domains_dir, _ = loader
        (domains_dir / "custom.yaml").write_text("domain: custom\npipeline: iterative\n")
        names = cl.list_domains()
        assert "custom" in names

    def test_list_pipelines(self, loader):
        cl, _, pipelines_dir = loader
        (pipelines_dir / "custom.yaml").write_text("name: custom\nstages: []\n")
        names = cl.list_pipelines()
        assert "custom" in names

    def test_cache_hit(self, loader):
        cl, _, _ = loader
        c1 = cl.load_domain("general")
        c2 = cl.load_domain("general")
        assert c1 is c2  # same cached object

    def test_clear_cache(self, loader):
        cl, _, _ = loader
        cl.load_domain("general")
        cl.clear_cache()
        # After clear, should still work (re-generate default)
        cfg = cl.load_domain("general")
        assert cfg.domain == "general"


class TestBoundaryContract:
    """L3: Boundary conditions."""

    def test_empty_yaml_raises(self, loader):
        cl, domains_dir, _ = loader
        (domains_dir / "empty.yaml").write_text("")
        with pytest.raises(ValueError):
            cl.load_domain("empty")

    def test_invalid_yaml_raises(self, loader):
        cl, domains_dir, _ = loader
        (domains_dir / "bad.yaml").write_text(":\n  - invalid: [")
        with pytest.raises(ValueError):
            cl.load_domain("bad")

    def test_list_dirs_missing_returns_empty(self, tmp_path):
        # domains/ and pipelines/ don't exist
        cl = ConfigLoader(v3_dir=tmp_path)
        assert cl.list_domains() == []
        assert cl.list_pipelines() == []
