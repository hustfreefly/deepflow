"""P2-2: Deliver Pro legacy .parent 修复回归测试

验证 slash 路径下 legacy 迁移正确（使用显式 blackboard_root 而非 .parent）。
"""
import pytest
import tempfile
import shutil
from pathlib import Path


def test_migrate_legacy_with_explicit_blackboard_root():
    """显式 blackboard_root 应正确计算 legacy2 路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        bb_root = Path(tmpdir)
        # 模拟项目结构
        project = "test_project"
        wp_subdir = "wp_001"
        wp_dir = bb_root / project / "deliver_pro" / wp_subdir
        correct_dir = wp_dir / "stages" / "worker_outputs"
        correct_dir.mkdir(parents=True)

        # 创建 legacy2 目录（在 blackboard_root/stages/worker_outputs/）
        legacy2_dir = bb_root / "stages" / "worker_outputs"
        legacy2_dir.mkdir(parents=True)
        task_dir = legacy2_dir / "T-001"
        task_dir.mkdir()
        (task_dir / "MANIFEST.json").write_text('{"status": "completed"}')

        from domains.deliver_pro.phase_deriver import migrate_legacy_worker_outputs

        migrated = migrate_legacy_worker_outputs(wp_dir, blackboard_root=bb_root)

        assert "T-001" in migrated
        assert (correct_dir / "T-001" / "MANIFEST.json").exists()


def test_migrate_legacy_without_blackboard_root_fallback():
    """无 blackboard_root 时回退到 .parent 行为"""
    with tempfile.TemporaryDirectory() as tmpdir:
        bb_root = Path(tmpdir)
        project = "test_project"
        wp_subdir = "wp_001"
        wp_dir = bb_root / project / "deliver_pro" / wp_subdir
        correct_dir = wp_dir / "stages" / "worker_outputs"
        correct_dir.mkdir(parents=True)

        # 创建 legacy1 目录
        legacy1_dir = wp_dir / "worker_outputs"
        legacy1_dir.mkdir(parents=True)
        task_dir = legacy1_dir / "T-002"
        task_dir.mkdir()
        (task_dir / "MANIFEST.json").write_text('{"status": "completed"}')

        from domains.deliver_pro.phase_deriver import migrate_legacy_worker_outputs

        migrated = migrate_legacy_worker_outputs(wp_dir)

        assert "T-002" in migrated
        assert (correct_dir / "T-002" / "MANIFEST.json").exists()


def test_migrate_legacy_slash_path_no_cross_contamination():
    """slash 路径下 legacy2 不应指向错误位置"""
    with tempfile.TemporaryDirectory() as tmpdir:
        bb_root = Path(tmpdir)
        # 模拟含 slash 的 project_name（已被 sanitize 为 _）
        project = "foo_bar"  # sanitize 后
        wp_subdir = "wp_001"
        wp_dir = bb_root / project / "deliver_pro" / wp_subdir
        correct_dir = wp_dir / "stages" / "worker_outputs"
        correct_dir.mkdir(parents=True)

        # 用显式 blackboard_root 时，legacy2 应指向 bb_root/stages/worker_outputs
        legacy2_dir = bb_root / "stages" / "worker_outputs"
        legacy2_dir.mkdir(parents=True)
        task_dir = legacy2_dir / "T-003"
        task_dir.mkdir()
        (task_dir / "MANIFEST.json").write_text('{"status": "completed"}')

        from domains.deliver_pro.phase_deriver import migrate_legacy_worker_outputs

        migrated = migrate_legacy_worker_outputs(wp_dir, blackboard_root=bb_root)

        assert "T-003" in migrated
        # 验证文件确实被迁移到正确位置
        assert (correct_dir / "T-003" / "MANIFEST.json").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
