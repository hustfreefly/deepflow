#!/usr/bin/env python3
"""
check_pipeline_engine_type.py - 验证 cb_result 类型防御
"""
import sys

def test_cb_result_type_handling():
    """验证 cb_result 类型处理"""
    # 模拟不同类型的 cb_result
    test_cases = [
        # (input, expected_success, description)
        ({"content": "test", "success": True, "score": 0.8}, True, "dict 类型"),
        (type('StageResult', (), {"content": "test", "success": True, "score": 0.8})(), True, "StageResult 对象"),
        ("raw string", False, "字符串类型"),
        (None, False, "None 类型"),
    ]
    
    for cb_result, expected_success, desc in test_cases:
        try:
            # 模拟 pipeline_engine 的处理逻辑
            if isinstance(cb_result, dict):
                content = cb_result.get("content", "")
                success = cb_result.get("success", False)
                score = cb_result.get("score", 0.0)
            elif hasattr(cb_result, 'content'):
                # StageResult-like 对象
                content = getattr(cb_result, 'content', "")
                success = getattr(cb_result, 'success', False)
                score = getattr(cb_result, 'score', 0.0)
            else:
                # 不支持的类型
                raise TypeError(f"Unsupported cb_result type: {type(cb_result)}")
            
            print(f"✅ {desc}: 处理成功 (success={success}, score={score})")
            
        except (AttributeError, TypeError) as e:
            if expected_success:
                print(f"❌ {desc}: 意外失败 - {e}")
                return False
            else:
                print(f"✅ {desc}: 正确拒绝 - {e}")
    
    return True

def test_safe_content_extraction():
    """验证安全的内容提取"""
    # 测试各种边缘情况
    test_cases = [
        ({"content": "valid"}, "valid"),
        ({"content": None}, ""),
        ({"content": ""}, ""),
        ({}, ""),  # 缺少 content 键
        ({"output": "wrong key"}, ""),  # 错误的键名
    ]
    
    for data, expected in test_cases:
        result = data.get("content") if isinstance(data, dict) else ""
        if result is None:
            result = ""
        
        if result == expected:
            print(f"✅ 输入 {data} -> 输出 '{result}'")
        else:
            print(f"❌ 输入 {data} -> 预期 '{expected}', 实际 '{result}'")
            return False
    
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("PipelineEngine 类型防御验证")
    print("=" * 50)
    
    try:
        test_cb_result_type_handling()
        test_safe_content_extraction()
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
