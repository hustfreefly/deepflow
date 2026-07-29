"""防呆回归测试：确保 V2 LLM Orchestrator 残留物不会回归。

背景（2026-07-28 事故）：
- LLM Orchestrator（drive_all）模式导致 17 并发失控 + 已完成 worker 重复 spawn
- 根因：已验证的 Pulse 路径未成为唯一入口，废弃 prompt 物理存在被误用
- 修复：5 层防呆（入口契约 / 方法 fence / 文件移除 / CI 检查 / cron 自动注册）

本测试是第 4 层：CI 自动验证文档/代码一致性，防止未来回归。
"""
import os
import pytest
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DELIVER_PRO_DIR = DEEPFLOW_ROOT / "domains" / "deliver_pro"
PROMPTS_DIR = DELIVER_PRO_DIR / "prompts"


def test_orchestrator_prompt_removed_from_active():
    """废弃的 deliver_orchestrator.md 不得存在于 prompts/ 活跃目录。"""
    assert not (PROMPTS_DIR / "deliver_orchestrator.md").exists(), (
        "deliver_orchestrator.md 不应存在于 prompts/ 活跃目录"
        "（已废弃，应移至 _archive/）。存在 = LLM 调度模式可被误用"
    )


def test_orchestrator_prompt_archived():
    """废弃 prompt 应在 _archive/ 中保留审计痕迹（.deprecated 后缀）。"""
    archived = PROMPTS_DIR / "_archive" / "deliver_orchestrator.md.deprecated"
    assert archived.exists(), (
        "deliver_orchestrator.md.deprecated 应在 _archive/ 中保留审计痕迹"
    )


def test_init_docstring_mentions_pulse_not_llm_orchestrator():
    """__init__.py 文档必须指向 Pulse，不得描述 LLM Orchestrator 为默认架构。"""
    src = (DELIVER_PRO_DIR / "__init__.py").read_text(encoding="utf-8")
    assert "pulse" in src.lower(), "__init__.py 必须提到 Pulse 模式"
    # V2 旧架构描述不得作为现行文档存在（历史注释中提及可接受，但 docstring 不行）
    docstring = src.split('"""')[1] if '"""' in src else ""
    assert "Orchestrator Agent, LLM" not in docstring, (
        "__init__.py docstring 不得再描述 V2 LLM Orchestrator 为现行架构"
    )


def test_run_deliver_pro_rejects_non_pulse_mode():
    """契约笼子：run_deliver_pro(mode!=pulse) 必须 raise ValueError。"""
    from unittest.mock import patch
    with patch("domains.deliver_pro.Path.exists", return_value=True):
        from domains.deliver_pro import run_deliver_pro
        with pytest.raises(ValueError, match="已禁用"):
            run_deliver_pro("test_project", mode="drive_all")
        with pytest.raises(ValueError, match="已禁用"):
            run_deliver_pro("test_project", mode="llm_orchestrator")


def test_drive_all_fence_blocks_without_env_var():
    """契约笼子：drive_all 无 DEEPFLOW_ALLOW_DRIVE_ALL=1 时必须 raise RuntimeError。"""
    from unittest.mock import patch, MagicMock
    # 确保环境变量未设置
    env = os.environ.copy()
    env.pop("DEEPFLOW_ALLOW_DRIVE_ALL", None)
    with patch.dict(os.environ, env, clear=True):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        # F1 fix (W3): _find_ship_package 缺失 → raise，所以测试 fence 需要 mock 一个有效 package
        mock_path = MagicMock()
        mock_path.read_text.return_value = '{"work_packages": [], "dependency_graph": {}}'
        with patch.object(
            DeliverOrchestrator, "_find_ship_package",
            return_value=mock_path
        ):
            orch = DeliverOrchestrator("test_project")
            with pytest.raises(RuntimeError, match="已禁用"):
                orch.drive_all()


def test_drive_once_fence_blocks_without_env_var():
    """契约笼子：drive_once 无 DEEPFLOW_ALLOW_DRIVE_ALL=1 时必须 raise RuntimeError。"""
    from unittest.mock import patch, MagicMock
    env = os.environ.copy()
    env.pop("DEEPFLOW_ALLOW_DRIVE_ALL", None)
    with patch.dict(os.environ, env, clear=True):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        # F1 fix (W3): _find_ship_package 缺失 → raise，所以测试 fence 需要 mock 一个有效 package
        mock_path = MagicMock()
        mock_path.read_text.return_value = '{"work_packages": [], "dependency_graph": {}}'
        with patch.object(
            DeliverOrchestrator, "_find_ship_package",
            return_value=mock_path
        ):
            orch = DeliverOrchestrator("test_project")
            with pytest.raises(RuntimeError, match="已禁用"):
                orch.drive_once()


def test_drive_all_fence_allows_with_env_var():
    """紧急回退口：DEEPFLOW_ALLOW_DRIVE_ALL=1 时 fence 不阻止（会走到后续逻辑）。

    注意：只验证 fence 本身不 raise RuntimeError("已禁用")，
    后续逻辑因 mock 环境可能抛其他异常（属正常）。
    """
    from unittest.mock import patch, MagicMock
    with patch.dict(os.environ, {"DEEPFLOW_ALLOW_DRIVE_ALL": "1"}):
        from domains.deliver_pro.orchestrator import DeliverOrchestrator
        # F1 fix (W3): _find_ship_package 缺失 → raise，所以测试 fence 需要 mock 一个有效 package
        mock_path = MagicMock()
        mock_path.read_text.return_value = '{"work_packages": [], "dependency_graph": {}}'
        with patch.object(
            DeliverOrchestrator, "_find_ship_package",
            return_value=mock_path
        ):
            orch = DeliverOrchestrator("test_project")
            # fence 不应抛 "已禁用" RuntimeError；后续 get_status 可能因缺文件抛其他错
            try:
                orch.drive_all()
            except RuntimeError as e:
                assert "已禁用" not in str(e), (
                    f"DEEPFLOW_ALLOW_DRIVE_ALL=1 时 fence 不应阻止，但报错: {e}"
                )
            except Exception:
                pass  # 后续逻辑异常属正常（mock 环境缺文件）


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
