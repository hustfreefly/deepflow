"""e2e_monitor.py 单元测试"""
import json
import tempfile
from pathlib import Path

# 添加脚本目录到 path

from e2e_monitor import (
    _file_info,
    _check_stage,
    _detect_domain,
    _format_duration,
    scan_session,
    detect_changes,
)

def test_file_info_valid_json():
    """测试：有效的 JSON 文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"status": "completed", "stage": "planning"}, f)
        f.flush()
        path = Path(f.name)
    
    info = _file_info(path)
    
    assert info['valid_json'] is True
    assert 'json_error' not in info
    assert info['size'] > 0
    assert 'mtime' in info
    
    path.unlink()

def test_file_info_invalid_json():
    """测试：无效的 JSON 文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json }")
        f.flush()
        path = Path(f.name)
    
    info = _file_info(path)
    
    assert info['valid_json'] is False
    assert 'json_error' in info
    
    path.unlink()

def test_file_info_missing():
    """测试：不存在的文件"""
    path = Path("/tmp/nonexistent_file_12345.json")
    info = _file_info(path)
    
    assert info['valid_json'] is False
    assert 'json_error' in info

def test_check_stage_completed():
    """测试：已完成的阶段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stages_dir = Path(tmpdir) / "stages"
        stages_dir.mkdir()
        
        stage_file = stages_dir / "planning.json"
        stage_file.write_text(json.dumps({
            "status": "completed",
            "stage": "planning",
            "output": "plan.md"
        }))
        
        info = _check_stage(stages_dir, "planning")
        
        assert info is not None
        assert info['valid_json'] is True
        assert info['has_status'] is True
        assert info['has_stage'] is True

def test_check_stage_missing():
    """测试：缺失的阶段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stages_dir = Path(tmpdir) / "stages"
        stages_dir.mkdir()
        
        info = _check_stage(stages_dir, "planning")
        assert info is None

def test_detect_domain_solution_pro():
    """测试：识别 Solution Pro 会话"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "solution_test"
        session_dir.mkdir()
        (session_dir / "stages").mkdir()
        
        domain = _detect_domain(session_dir)
        assert domain == "solution_pro"

def test_detect_domain_spec_pro():
    """测试：识别 Spec Pro 会话"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "spec_test"
        session_dir.mkdir()
        (session_dir / "spec").mkdir()
        
        domain = _detect_domain(session_dir)
        assert domain == "spec_pro"

def test_detect_domain_ship_pro():
    """测试：识别 Ship Pro 会话"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "ship_test"
        session_dir.mkdir()
        (session_dir / "ship").mkdir()
        
        domain = _detect_domain(session_dir)
        assert domain == "ship_pro"

def test_format_duration():
    """测试：时间格式化"""
    assert _format_duration(30) == "30s"
    assert _format_duration(90) == "1m30s"
    assert _format_duration(3661) == "1h1m"  # 忽略秒数
    assert _format_duration(7200) == "2h0m"

def test_scan_session():
    """测试：完整会话扫描"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建模拟会话目录
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        
        # 创建几个阶段文件（使用实际存在的 stage 名称）
        (stages_dir / "planning.json").write_text(
            json.dumps({"status": "completed"})
        )
        (stages_dir / "reviewer_technical.json").write_text(
            json.dumps({"status": "completed"})
        )
        
        # 创建终态文件
        (session_dir / "final_solution.md").write_text("# Solution")
        
        result = scan_session(session_dir)
        
        assert result['session'] == "test_session"
        assert result['summary']['completed_stages'] == 2
        assert result['summary']['total_stages'] == 2
        assert result['summary']['is_finished'] is True
        assert result['summary']['domain'] == "solution_pro"

def test_detect_changes_first_run():
    """测试：首次运行（无历史数据）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        (session_dir / "stages").mkdir()
        
        current = scan_session(session_dir)
        changes = detect_changes(current)
        
        # 首次运行应该报告所有阶段为新增
        assert isinstance(changes, list)

def test_detect_changes_with_history():
    """测试：有历史数据时检测变更"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        
        # 创建初始阶段
        (stages_dir / "planning.json").write_text(
            json.dumps({"status": "completed"})
        )
        
        # 首次扫描并写入 .progress.json
        current1 = scan_session(session_dir)
        from e2e_monitor import write_progress
        write_progress(current1)
        
        # 添加新阶段（使用实际存在的 stage 名称）
        (stages_dir / "reviewer_technical.json").write_text(
            json.dumps({"status": "completed"})
        )
        
        # 第二次扫描
        current2 = scan_session(session_dir)
        changes = detect_changes(current2)
        
        # changes 返回的是格式化字符串，检查是否包含 stage 名称
        assert any("reviewer_technical" in change for change in changes)

def test_scan_session_with_invalid_json():
    """测试：包含无效 JSON 的会话"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        
        # 有效 JSON（使用实际存在的 stage 名称）
        (stages_dir / "planning.json").write_text(
            json.dumps({"status": "completed"})
        )
        
        # 无效 JSON（使用实际存在的 stage 名称）
        (stages_dir / "reviewer_technical.json").write_text("{ invalid }")
        
        result = scan_session(session_dir)
        
        assert result['summary']['completed_stages'] == 1
        assert result['summary']['failed_stages'] == 1

def test_check_stage_size_warnings():
    """测试：阶段文件大小警告"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stages_dir = Path(tmpdir) / "stages"
        stages_dir.mkdir()
        
        # 太小的文件
        (stages_dir / "planning.json").write_text('{"s":1}')
        
        # 太大的文件（模拟）
        large_content = '{"data":"' + 'x' * 600000 + '"}'
        (stages_dir / "reviewer_technical.json").write_text(large_content)
        
        from e2e_monitor import _check_stage
        
        info_small = _check_stage(stages_dir, "planning")
        assert info_small is not None
        assert "warning" in info_small
        assert "too_small" in info_small["warning"]
        
        info_large = _check_stage(stages_dir, "reviewer_technical")
        assert info_large is not None
        assert "warning" in info_large
        assert "too_large" in info_large["warning"]

def test_check_stage_error_detection():
    """测试：阶段文件错误检测"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stages_dir = Path(tmpdir) / "stages"
        stages_dir.mkdir()
        
        # status=error
        (stages_dir / "planning.json").write_text(
            json.dumps({"status": "error", "message": "timeout"})
        )
        
        # 包含 error 字段
        (stages_dir / "reviewer_technical.json").write_text(
            json.dumps({"status": "completed", "error": "spawn failed"})
        )
        
        from e2e_monitor import _check_stage
        
        info1 = _check_stage(stages_dir, "planning")
        assert info1 is not None
        assert "error" in info1
        assert "error" in info1["error"]
        
        info2 = _check_stage(stages_dir, "reviewer_technical")
        assert info2 is not None
        assert "error" in info2
        assert "spawn failed" in info2["error"]

def test_compute_summary_stuck_detection():
    """测试：卡住检测（长时间无新阶段）"""
    import time
    
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        
        # 创建一个很旧的阶段文件（模拟卡住）
        old_file = stages_dir / "planning.json"
        old_file.write_text(json.dumps({"status": "completed"}))
        
        # 修改 mtime 为 1 小时前
        old_time = time.time() - 3600
        old_file.touch()
        import os
        os.utime(old_file, (old_time, old_time))
        
        from e2e_monitor import _scan_stage_files, _scan_terminal_files, _compute_summary
        
        stages = _scan_stage_files(session_dir)
        terminal = _scan_terminal_files(session_dir)
        summary = _compute_summary(stages, terminal, session_dir)
        
        # 应该检测到卡住警告
        assert "warnings" in summary
        assert any("可能卡住" in w for w in summary["warnings"])

def test_check_subagent_health():
    """测试：子Agent健康检查"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        
        from e2e_monitor import _check_subagent_health
import core.bootstrap
        
        # 测试1：空 .completed 文件
        (session_dir / ".completed").write_text("")
        issues = _check_subagent_health(session_dir)
        assert any(".completed 文件内容为空或过短" in i for i in issues)
        
        # 测试2：正常的 .completed 文件
        (session_dir / ".completed").write_text("2026-06-22T13:00:00Z")
        issues = _check_subagent_health(session_dir)
        assert not any(".completed 文件内容为空或过短" in i for i in issues)
        
        # 测试3：.stage_progress.json 显示错误
        (session_dir / ".stage_progress.json").write_text(
            json.dumps({"current_stage": "planning", "status": "error"})
        )
        issues = _check_subagent_health(session_dir)
        assert any("error" in i.lower() for i in issues)
        
        # 测试4：日志文件包含错误
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        (stages_dir / "planning.log").write_text("ERROR: timeout occurred")
        issues = _check_subagent_health(session_dir)
        assert any("planning.log" in i for i in issues)

def test_scan_session_with_errors_and_warnings():
    """测试：完整会话扫描包含错误和警告"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / "test_session"
        session_dir.mkdir()
        
        stages_dir = session_dir / "stages"
        stages_dir.mkdir()
        
        # 正常阶段
        (stages_dir / "planning.json").write_text(
            json.dumps({"status": "completed"})
        )
        
        # 错误阶段
        (stages_dir / "reviewer_technical.json").write_text(
            json.dumps({"status": "error", "message": "timeout"})
        )
        
        # 太小的阶段
        (stages_dir / "reviewer_business.json").write_text('{"s":1}')
        
        result = scan_session(session_dir)
        
        # 应该收集错误和警告
        assert "errors" in result["summary"]
        assert len(result["summary"]["errors"]) > 0
        assert "warnings" in result["summary"]
        assert len(result["summary"]["warnings"]) > 0

if __name__ == "__main__":
    # 运行所有测试
    test_functions = [
        test_file_info_valid_json,
        test_file_info_invalid_json,
        test_file_info_missing,
        test_check_stage_completed,
        test_check_stage_missing,
        test_detect_domain_solution_pro,
        test_detect_domain_spec_pro,
        test_detect_domain_ship_pro,
        test_format_duration,
        test_scan_session,
        test_detect_changes_first_run,
        test_detect_changes_with_history,
        test_scan_session_with_invalid_json,
        test_check_stage_size_warnings,
        test_check_stage_error_detection,
        test_compute_summary_stuck_detection,
        test_check_subagent_health,
        test_scan_session_with_errors_and_warnings,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n总计: {passed + failed} 个测试, {passed} 通过, {failed} 失败")
    sys.exit(0 if failed == 0 else 1)
