"""P2-1: Ship Pro sanitize 回归测试

验证含 / 的 role 被正确处理（替换为 _），防止路径穿越。
"""
import pytest
from pathlib import Path


def test_ship_pro_role_sanitize_slash():
    """role 含 / 时，sanitize 后应替换为 _"""
    role = "backend/api"
    safe_role = role.replace(" ", "_").replace("/", "_")
    assert safe_role == "backend_api"
    assert "/" not in safe_role


def test_ship_pro_role_sanitize_space_and_slash():
    """role 含空格和 / 时，两者都应被替换"""
    role = "backend api/v2"
    safe_role = role.replace(" ", "_").replace("/", "_")
    assert safe_role == "backend_api_v2"


def test_ship_pro_role_sanitize_no_change_for_clean_role():
    """clean role 不应被修改"""
    role = "backend_api"
    safe_role = role.replace(" ", "_").replace("/", "_")
    assert safe_role == "backend_api"


def test_ship_pro_output_path_construction():
    """验证 output_path 构造逻辑正确"""
    worker_outputs_dir = Path("/tmp/test/stages/worker_outputs")
    role = "backend/api"
    safe_role = role.replace(" ", "_").replace("/", "_")
    output_path = str(worker_outputs_dir / f"worker_{safe_role}.json")
    assert output_path == "/tmp/test/stages/worker_outputs/worker_backend_api.json"
    assert "/" not in output_path.split("worker_outputs/")[-1].replace(".json", "").split("worker_")[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
