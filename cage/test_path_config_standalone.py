#!/usr/bin/env python3
"""
PathConfig 独立测试脚本（不依赖 pytest）
绕过项目 __init__.py 导入问题
"""

import sys
import os
import tempfile
from pathlib import Path

# 直接添加 core 目录到路径，避免导入项目根 __init__.py
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/core/config')
from path_config import PathConfig, validate_path_safety, _is_relative_to

passed = 0
failed = 0

def test(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} - {detail}")

print("\n" + "="*70)
print("PathConfig 独立测试")
print("="*70)

# Test 1: 基本实例化
print("\n[Test 1] 基本实例化")
try:
    config = PathConfig('/tmp/test_path_config')
    test("实例化", True)
except Exception as e:
    test("实例化", False, str(e))

# Test 2: MAX_SESSION_ID_LENGTH
print("\n[Test 2] session_id 长度限制")
try:
    config = PathConfig('/tmp/test')
    config.get_blackboard_path("a" * 300)
    test("长度限制", False, "应抛出异常")
except ValueError:
    test("长度限制", True)
except Exception as e:
    test("长度限制", False, str(e))

# Test 3: session_id 清理
print("\n[Test 3] session_id 清理")
try:
    config = PathConfig('/tmp/test')
    path = config.get_blackboard_path("test_123")
    test("正常字符", "test_123" in str(path))
    
    path2 = config.get_blackboard_path("test@file")
    test("非法字符替换", "test_file" in str(path2))
except Exception as e:
    test("session_id清理", False, str(e))

# Test 4: 空 session_id
print("\n[Test 4] 空 session_id")
try:
    config = PathConfig('/tmp/test')
    config.get_blackboard_path("")
    test("空session_id", False, "应抛出异常")
except ValueError:
    test("空session_id", True)

# Test 5: 目录创建
print("\n[Test 5] 目录创建")
try:
    with tempfile.TemporaryDirectory() as tmpdir:
        config = PathConfig(tmpdir)
        config.ensure_directories()
        test("blackboard目录", config.blackboard_dir.exists())
        test("config目录", config.config_dir.exists())
        test("logs目录", config.logs_dir.exists())
        test("cache目录", config.cache_dir.exists())
except Exception as e:
    test("目录创建", False, str(e))

# Test 6: 权限隔离（Unix only）
print("\n[Test 6] 权限隔离")
if os.name != 'nt':
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PathConfig(tmpdir)
            config.ensure_directories()
            mode = (Path(tmpdir) / 'blackboard').stat().st_mode & 0o777
            test("权限700", mode == 0o700, f"实际: {oct(mode)}")
    except Exception as e:
        test("权限隔离", False, str(e))
else:
    test("权限隔离", True, "Windows跳过")

# Test 7: _is_relative_to 兼容性
print("\n[Test 7] _is_relative_to 兼容性")
from pathlib import Path
test("子路径", _is_relative_to(Path('/tmp/base/child'), Path('/tmp/base')))
test("外部路径", not _is_relative_to(Path('/tmp/outside'), Path('/tmp/base')))

# Test 8: validate_path_safety
print("\n[Test 8] validate_path_safety")
try:
    with tempfile.TemporaryDirectory() as tmpdir:
        allowed = Path(tmpdir) / 'allowed'
        allowed.mkdir()
        # 创建测试文件
        safe_file = allowed / 'safe.txt'
        safe_file.write_text('test')
        validate_path_safety(safe_file, allowed)
        test("安全路径", True)
except Exception as e:
    test("安全路径", False, str(e))

try:
    with tempfile.TemporaryDirectory() as tmpdir:
        allowed = Path(tmpdir) / 'allowed'
        allowed.mkdir()
        validate_path_safety(allowed / '..' / 'etc' / 'passwd', allowed)
        test("路径遍历防护", False, "应抛出异常")
except ValueError:
    test("路径遍历防护", True)

# Test 9: _validate_env_path
print("\n[Test 9] _validate_env_path")
try:
    PathConfig._validate_env_path('/tmp/test')
    test("有效路径", True)
except Exception as e:
    test("有效路径", False, str(e))

try:
    PathConfig._validate_env_path('relative/path')
    test("相对路径拒绝", False, "应抛出异常")
except ValueError:
    test("相对路径拒绝", True)

# Test 10: __repr__
print("\n[Test 10] __repr__")
try:
    config = PathConfig('/tmp/test')
    repr_str = repr(config)
    test("__repr__包含PathConfig", 'PathConfig' in repr_str)
    test("__repr__包含路径", '/tmp/test' in repr_str)
except Exception as e:
    test("__repr__", False, str(e))

# 汇总
print("\n" + "="*70)
print(f"测试结果: {passed}/{passed+failed} 通过")
print("="*70)

if failed > 0:
    print(f"\n❌ {failed} 个测试失败")
    sys.exit(1)
else:
    print("\n✅ 所有测试通过")
    sys.exit(0)
