#!/usr/bin/env python3
"""
PathConfig 契约验证脚本
预期: 首次运行失败（PathConfig 类不存在）
实现后: 重新运行通过
"""

import sys
import subprocess

DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"
sys.path.insert(0, DEEPFLOW_BASE)

passed = 0
failed = 0

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} - {detail}")

print("\n" + "="*70)
print("PathConfig 契约验证")
print("="*70)

# 检查文件是否存在
import os
path_config_file = f"{DEEPFLOW_BASE}/core/config/path_config.py"
check(
    "文件存在",
    os.path.exists(path_config_file),
    f"文件不存在: {path_config_file}"
)

# 检查语法
if os.path.exists(path_config_file):
    result = subprocess.run(
        ["python3", "-m", "py_compile", path_config_file],
        capture_output=True
    )
    check(
        "语法正确",
        result.returncode == 0,
        result.stderr.decode()[:200] if result.returncode != 0 else ""
    )

# 检查导入
try:
    from core.config.path_config import PathConfig
    check("可导入", True)
    
    # 检查关键属性/方法
    check("MAX_SESSION_ID_LENGTH", hasattr(PathConfig, 'MAX_SESSION_ID_LENGTH'))
    check("resolve方法", hasattr(PathConfig, 'resolve'))
    
    # 测试基本功能
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PathConfig(tmpdir)
            check("实例化", True)
            
            # 测试 get_blackboard_path
            try:
                bb_path = config.get_blackboard_path("test_session")
                check("get_blackboard_path", "test_session" in str(bb_path))
            except Exception as e:
                check("get_blackboard_path", False, str(e))
            
            # 测试路径遍历防护
            try:
                config.get_blackboard_path("a" * 300)  # 超长 session_id
                check("路径遍历防护", False, "应抛出异常")
            except ValueError:
                check("路径遍历防护", True)
            except Exception as e:
                check("路径遍历防护", False, f"错误类型: {type(e).__name__}")
            
            # 测试 ensure_directories
            try:
                config.ensure_directories()
                check("ensure_directories", True)
            except Exception as e:
                check("ensure_directories", False, str(e))
                
    except Exception as e:
        check("实例化", False, str(e))
        
except ImportError as e:
    check("可导入", False, str(e))
    check("MAX_SESSION_ID_LENGTH", False, "导入失败")
    check("resolve方法", False, "导入失败")

# 汇总
print("\n" + "="*70)
print(f"验证结果: {passed}/{passed+failed} 通过")
print("="*70)

if failed > 0:
    print("\n❌ 契约验证失败，需要按契约实现代码")
    sys.exit(1)
else:
    print("\n✅ 契约验证通过")
    sys.exit(0)
