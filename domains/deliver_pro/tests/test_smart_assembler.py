"""Tests for SmartAssembler — Code-First Assembly."""

import json
import pytest
from pathlib import Path

from domains.deliver_pro.smart_assembler import SmartAssembler, assemble


@pytest.fixture
def mock_worker_outputs(tmp_path):
    """Create mock worker output directories."""
    worker_dir = tmp_path / "worker_outputs"

    for i, (task_id, title) in enumerate([
        ("T-001", "数据采集"),
        ("T-002", "技术路线"),
        ("T-003", "竞争格局"),
    ], 1):
        task_dir = worker_dir / task_id
        task_dir.mkdir(parents=True)

        content = f"# {title}\n\n这是第{i}个章节的内容。\n\n## 详细分析\n\n详细数据...\n"
        (task_dir / "DELIVERABLE.md").write_text(content, encoding="utf-8")
        (task_dir / "EVIDENCE.md").write_text(
            f"# {title} 证据\n\n- 来源1: URL\n- 来源2: URL\n",
            encoding="utf-8",
        )
        (task_dir / "ISSUES.md").write_text(
            f"# {title} 问题\n\n无阻塞问题。\n",
            encoding="utf-8",
        )
        (task_dir / "MANIFEST.json").write_text(json.dumps({
            "task_id": task_id,
            "status": "COMPLETE",
            "quality_self_check": {"acceptance_criteria_met": True},
        }), encoding="utf-8")

    return worker_dir


@pytest.fixture
def mock_plan():
    """Create a mock execution plan."""
    return {
        "wp_id": "WP-TEST",
        "task_graph": [
            {"task_id": "T-001", "title": "数据采集", "depends_on": []},
            {"task_id": "T-002", "title": "技术路线", "depends_on": []},
            {"task_id": "T-003", "title": "竞争格局", "depends_on": ["T-001"]},
        ],
    }


class TestSmartAssembler:

    def test_basic_assembly(self, mock_worker_outputs, mock_plan, tmp_path):
        """基本组装：3 个 Worker → 拼接后保留率 ≥95%。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        assert result.status == "READY_FOR_VALIDATE"
        assert result.workers_integrated == 3
        assert result.workers_failed == 0
        assert result.retention_ratio >= 0.95  # 保留率 ≥95%
        assert result.deliverable_path.exists()

    def test_content_preservation(self, mock_worker_outputs, mock_plan, tmp_path):
        """内容守恒：每个 Worker 的核心内容在最终文件中存在。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        final_text = result.deliverable_path.read_text(encoding="utf-8")

        # Each chapter title should be present
        assert "数据采集" in final_text
        assert "技术路线" in final_text
        assert "竞争格局" in final_text

        # Each chapter content should be preserved
        assert "这是第1个章节的内容" in final_text
        assert "这是第2个章节的内容" in final_text
        assert "这是第3个章节的内容" in final_text

    def test_toc_generation(self, mock_worker_outputs, mock_plan, tmp_path):
        """TOC 生成：目录包含所有章节标题。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        final_text = result.deliverable_path.read_text(encoding="utf-8")
        assert "## 目录" in final_text
        assert "数据采集" in final_text
        assert "技术路线" in final_text

    def test_evidence_appendix(self, mock_worker_outputs, mock_plan, tmp_path):
        """证据索引附录：所有 EVIDENCE.md 内容被合并。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        final_text = result.deliverable_path.read_text(encoding="utf-8")
        assert "附录：证据索引" in final_text
        assert "来源1: URL" in final_text

    def test_report_generation(self, mock_worker_outputs, mock_plan, tmp_path):
        """integration_report.json 正确生成。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        assert result.report_path.exists()
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        assert report["workers_integrated"] == 3
        assert report["status"] == "READY_FOR_VALIDATE"
        assert report["assembly_stats"]["method"] == "code-first-deterministic"
        assert report["assembly_stats"]["llm_calls"] == 0

    def test_missing_worker_graceful(self, mock_worker_outputs, mock_plan, tmp_path):
        """缺失 Worker 不崩溃，跳过并继续，但状态反映缺失。"""
        # Remove T-002
        import shutil
        shutil.rmtree(mock_worker_outputs / "T-002")

        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        # Should still assemble T-001 and T-003
        assert result.workers_integrated == 2
        assert result.workers_failed == 1
        # Missing worker → PARTIAL, not READY_FOR_VALIDATE
        assert result.status == "PARTIAL"
        # coverage_gaps should list the missing task
        assert "T-002" in result.coverage_gaps
        # Report should also reflect the failure
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        assert report["workers_failed"] == 1
        assert report["status"] == "PARTIAL"
        assert "T-002" in report["coverage"]["gaps"]

    def test_convenience_function(self, mock_worker_outputs, mock_plan, tmp_path):
        """assemble() 便捷函数可用。"""
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps(mock_plan), encoding="utf-8")
        output_dir = tmp_path / "output"

        result = assemble(mock_worker_outputs, plan_path, output_dir)
        assert result.status == "READY_FOR_VALIDATE"
        assert result.retention_ratio >= 0.95

    def test_heading_normalization(self, mock_worker_outputs, mock_plan, tmp_path):
        """标题层级归一化：Worker 内部 # → ##。"""
        output_dir = tmp_path / "integrated_draft"
        assembler = SmartAssembler(mock_worker_outputs, mock_plan, output_dir)
        result = assembler.run()

        final_text = result.deliverable_path.read_text(encoding="utf-8")
        # Chapter headers should be # level
        assert "# 第1章 数据采集" in final_text
        # Original ## should become ###
        assert "### 详细分析" in final_text
