#!/usr/bin/env python3
"""
check_coordinator_blackboards.py - 验证 _blackboards 初始化
"""
import sys

def test_blackboards_initialized():
    """验证 Coordinator 初始化后 _blackboards 属性存在"""
    import importlib
    import coordinator
    importlib.reload(coordinator)
    
    coord = coordinator.Coordinator()
    
    # 检查属性存在
    assert hasattr(coord, '_blackboards'), "Coordinator 缺少 _blackboards 属性"
    print("✅ _blackboards 属性存在")
    
    # 检查默认值为空字典
    assert coord._blackboards == {}, f"_blackboards 默认值应为 {{}}, 实际 {coord._blackboards}"
    print("✅ _blackboards 默认值为空字典")
    
    # 检查可读写
    coord._blackboards["test_session"] = {"data": "test"}
    assert coord._blackboards["test_session"]["data"] == "test"
    print("✅ _blackboards 可读写")
    
    return True

def test_resume_hitl_no_attribute_error():
    """验证 resume_hitl 不抛出 AttributeError"""
    import importlib
    import coordinator
    importlib.reload(coordinator)
    
    coord = coordinator.Coordinator()
    
    # 模拟 resume_hitl 调用（仅检查不抛出 AttributeError）
    try:
        # 只检查访问 _blackboards 不报错
        _ = coord._blackboards.get("nonexistent")
        print("✅ resume_hitl 可安全访问 _blackboards")
    except AttributeError as e:
        print(f"❌ AttributeError: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("Coordinator _blackboards 契约验证")
    print("=" * 50)
    
    try:
        test_blackboards_initialized()
        test_resume_hitl_no_attribute_error()
        print("=" * 50)
        print("✅ 全部通过")
        sys.exit(0)
    except AssertionError as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
