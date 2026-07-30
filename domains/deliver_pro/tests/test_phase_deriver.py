"""B1 fix: 畸形 delivery_manifest.json 不应被推导为 DONE

验证 phase_deriver.derive_phase() 在 delivery_manifest.json 损坏时
返回 PACKAGING 而非 DONE，让 package agent 重试。
"""
import pytest
import tempfile
from pathlib import Path


def test_corrupted_manifest_returns_packaging_not_done():
    """损坏的 delivery_manifest.json + 非空 final_deliverable/ 应返回 PACKAGING"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wp_dir = Path(tmpdir) / "wp_test"
        stages_dir = wp_dir / "stages"
        stages_dir.mkdir(parents=True)

        # 创建损坏的 delivery_manifest.json（无效 JSON）
        manifest_file = stages_dir / "delivery_manifest.json"
        manifest_file.write_text("{ invalid json content", encoding="utf-8")

        # 创建非空 final_deliverable/（含 ≥50B 文件）
        final_dir = stages_dir / "final_deliverable"
        final_dir.mkdir()
        deliverable = final_dir / "DELIVERABLE.md"
        deliverable.write_text("x" * 100, encoding="utf-8")  # 100 bytes

        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_PACKAGING

        phase = derive_phase(wp_dir)

        # 关键断言：不应返回 DONE
        assert phase != "DONE", f"Expected non-DONE phase, got {phase}"
        assert phase == PHASE_PACKAGING, f"Expected PACKAGING, got {phase}"


def test_valid_manifest_with_deliverable_returns_done():
    """有效的 delivery_manifest.json + 非空 final_deliverable/ 应返回 DONE"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wp_dir = Path(tmpdir) / "wp_test"
        stages_dir = wp_dir / "stages"
        stages_dir.mkdir(parents=True)

        # 创建有效的 delivery_manifest.json（符合 DeliveryManifest schema）
        manifest_file = stages_dir / "delivery_manifest.json"
        valid_manifest = {
            "wp_id": "wp_test",
            "delivery_status": "COMPLETE",
            "components": [
                {
                    "task_id": "T-001",
                    "title": "Test Task",
                    "status": "PASS",
                    "artifacts": ["DELIVERABLE.md"],
                }
            ],
            "validation_summary": {
                "rounds_run": 1,
                "final_score": 85.0,
                "verdict": "PASS",
            },
            "semantic_anchors": [],
            "requirement_traceability": {
                "covered_req_ids": [],
                "total_req_ids": [],
                "coverage_ratio": 0.0,
            },
        }
        manifest_file.write_text(
            __import__("json").dumps(valid_manifest),
            encoding="utf-8",
        )

        # 创建非空 final_deliverable/
        final_dir = stages_dir / "final_deliverable"
        final_dir.mkdir()
        deliverable = final_dir / "DELIVERABLE.md"
        deliverable.write_text("x" * 100, encoding="utf-8")

        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_DONE

        phase = derive_phase(wp_dir)

        assert phase == PHASE_DONE, f"Expected DONE, got {phase}"


def test_schema_invalid_manifest_returns_packaging():
    """JSON 有效但不符合 DeliveryManifest schema 应返回 PACKAGING"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wp_dir = Path(tmpdir) / "wp_test"
        stages_dir = wp_dir / "stages"
        stages_dir.mkdir(parents=True)

        # 创建 JSON 有效但 schema 无效的 manifest（缺少必需字段 wp_id）
        manifest_file = stages_dir / "delivery_manifest.json"
        invalid_schema_manifest = {
            "delivery_status": "COMPLETE",
            "components": [],
            # 缺少 wp_id（必需字段）
        }
        manifest_file.write_text(
            __import__("json").dumps(invalid_schema_manifest),
            encoding="utf-8",
        )

        # 创建非空 final_deliverable/
        final_dir = stages_dir / "final_deliverable"
        final_dir.mkdir()
        deliverable = final_dir / "DELIVERABLE.md"
        deliverable.write_text("x" * 100, encoding="utf-8")

        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_PACKAGING

        phase = derive_phase(wp_dir)

        assert phase != "DONE", f"Expected non-DONE phase, got {phase}"
        assert phase == PHASE_PACKAGING, f"Expected PACKAGING, got {phase}"


def test_legacy_path_corrupted_manifest_returns_packaging():
    """Legacy 路径下损坏的 manifest 也应返回 PACKAGING"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wp_dir = Path(tmpdir) / "wp_test"
        stages_dir = wp_dir / "stages"
        stages_dir.mkdir(parents=True)

        # 创建损坏的 delivery_manifest.json
        manifest_file = stages_dir / "delivery_manifest.json"
        manifest_file.write_text("not valid json at all", encoding="utf-8")

        # Legacy 路径：final_deliverable 在 WP 根目录
        legacy_final_dir = wp_dir / "final_deliverable"
        legacy_final_dir.mkdir()
        deliverable = legacy_final_dir / "DELIVERABLE.md"
        deliverable.write_text("x" * 100, encoding="utf-8")

        from domains.deliver_pro.phase_deriver import derive_phase, PHASE_PACKAGING

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 忽略 DeprecationWarning
            phase = derive_phase(wp_dir)

        assert phase != "DONE", f"Expected non-DONE phase, got {phase}"
        assert phase == PHASE_PACKAGING, f"Expected PACKAGING, got {phase}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
