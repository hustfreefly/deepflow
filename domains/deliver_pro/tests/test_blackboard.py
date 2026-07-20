"""Tests for DeliverProBlackboard."""

import json
import threading

import pytest

from domains.deliver_pro.blackboard import DeliverProBlackboard


class TestDirectoryInitialization:
    def test_creates_directory_structure(self, tmp_path):
        bb = DeliverProBlackboard("test_project", base_dir=tmp_path)
        assert bb.root.exists()
        assert (bb.root / "data").is_dir()
        assert (bb.root / "stages").is_dir()
        assert (bb.root / "stages" / "worker_outputs").is_dir()
        assert (bb.root / "stages" / "integrated_draft").is_dir()
        assert (bb.root / "stages" / "final_deliverable").is_dir()

    def test_root_path_construction(self, tmp_path):
        bb = DeliverProBlackboard("my_project", base_dir=tmp_path)
        assert bb.root == tmp_path / "blackboard" / "my_project" / "deliver_pro"

    def test_default_base_dir(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bb = DeliverProBlackboard("proj")
        assert bb.root == tmp_path / "blackboard" / "proj" / "deliver_pro"

    def test_idempotent_init(self, tmp_path):
        """Creating blackboard twice should not raise."""
        bb1 = DeliverProBlackboard("proj", base_dir=tmp_path)
        bb2 = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb1.root == bb2.root


class TestSaveLoadJson:
    def test_save_and_load_json(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        data = {"key": "value", "nested": {"a": 1}}
        bb.save_json("analyze", data, "plan.json")

        loaded = bb.load_json("analyze", "plan.json")
        assert loaded == data

    def test_load_json_nonexistent(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        result = bb.load_json("analyze", "nonexistent.json")
        assert result is None

    def test_save_json_creates_stage_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        bb.save_json("custom_stage", {"x": 1}, "data.json")
        assert (bb.root / "stages" / "custom_stage").is_dir()

    def test_save_json_unicode(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        data = {"name": "测试项目", "emoji": "🚀"}
        bb.save_json("test", data, "unicode.json")
        loaded = bb.load_json("test", "unicode.json")
        assert loaded["name"] == "测试项目"

    def test_save_json_atomic_no_leftover_tmp(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        bb.save_json("test", {"a": 1}, "file.json")
        stage_dir = bb.root / "stages" / "test"
        tmp_files = list(stage_dir.glob(".*tmp"))
        assert len(tmp_files) == 0


class TestSaveLoadFile:
    def test_save_and_load_file(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        content = "Hello, World!\nLine 2"
        bb.save_file("generate", content, "output.md")

        loaded = bb.load_file("generate", "output.md")
        assert loaded == content

    def test_load_file_nonexistent(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        result = bb.load_file("generate", "nonexistent.md")
        assert result is None

    def test_save_file_unicode(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        content = "中文内容\n测试"
        bb.save_file("test", content, "cn.txt")
        loaded = bb.load_file("test", "cn.txt")
        assert loaded == content


class TestExists:
    def test_exists_true(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        bb.save_json("test", {"a": 1}, "file.json")
        assert bb.exists("test", "file.json") is True

    def test_exists_false(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.exists("test", "nope.json") is False


class TestGetWorkerOutputDir:
    def test_creates_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        worker_dir = bb.get_worker_output_dir("T-001")
        assert worker_dir.is_dir()
        assert worker_dir == bb.root / "stages" / "worker_outputs" / "T-001"

    def test_different_tasks_different_dirs(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        d1 = bb.get_worker_output_dir("T-001")
        d2 = bb.get_worker_output_dir("T-002")
        assert d1 != d2


class TestGetStagePath:
    def test_creates_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        path = bb.get_stage_path("analyze")
        assert path.is_dir()
        assert path == bb.root / "stages" / "analyze"

    def test_idempotent(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        p1 = bb.get_stage_path("analyze")
        p2 = bb.get_stage_path("analyze")
        assert p1 == p2


class TestProperties:
    def test_data_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.data_dir == bb.root / "data"

    def test_stages_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.stages_dir == bb.root / "stages"

    def test_worker_outputs_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.worker_outputs_dir == bb.root / "stages" / "worker_outputs"

    def test_integrated_draft_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.integrated_draft_dir == bb.root / "stages" / "integrated_draft"

    def test_final_deliverable_dir(self, tmp_path):
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        assert bb.final_deliverable_dir == bb.root / "stages" / "final_deliverable"


class TestConcurrentWrites:
    def test_concurrent_json_writes(self, tmp_path):
        """Multiple threads writing different files should not corrupt data."""
        bb = DeliverProBlackboard("proj", base_dir=tmp_path)
        errors = []

        def writer(i):
            try:
                bb.save_json("concurrent", {"thread": i}, f"file_{i}.json")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Verify all files are readable
        for i in range(10):
            data = bb.load_json("concurrent", f"file_{i}.json")
            assert data is not None
            assert data["thread"] == i
