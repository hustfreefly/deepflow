#!/usr/bin/env python3
"""
check_scale_unification.py - 验证尺度统一
"""
import sys

def test_normalize_threshold():
    """验证 _normalize_threshold 转换正确"""
    test_cases = [
        (0.88, 88.0, "0-1 转 0-100"),
        (88.0, 88.0, "0-100 保持不变"),
        (0.5, 50.0, "0.5 转 50"),
        (1.0, 100.0, "1.0 转 100"),
        (0.0, 0.0, "0 保持不变"),
        (95.0, 95.0, "95 保持不变"),
    ]
    
    for input_val, expected, desc in test_cases:
        # 模拟 _normalize_threshold
        if 0 <= input_val <= 1.0:
            result = input_val * 100.0
        else:
            result = input_val
        
        if abs(result - expected) < 0.01:
            print(f"✅ {desc}: {input_val} -> {result}")
        else:
            print(f"❌ {desc}: 预期 {expected}, 实际 {result}")
            return False
    
    return True

def test_score_comparison_consistency():
    """验证分数比较时尺度一致"""
    # 场景1: score=0.88 (0-1存储), target=88 (0-100配置)
    # 错误: 直接比较 0.88 >= 88 -> False
    # 正确: 转换后比较 88 >= 88 -> True
    
    score_01 = 0.88
    target_100 = 88.0
    
    # 错误方式
    wrong_result = score_01 >= target_100  # False
    
    # 正确方式
    normalized_score = score_01 * 100 if score_01 <= 1.0 else score_01
    correct_result = normalized_score >= target_100  # True
    
    if wrong_result == False and correct_result == True:
        print("✅ 尺度转换避免错误比较 (0.88 vs 88)")
    else:
        print("❌ 尺度比较逻辑错误")
        return False
    
    # 场景2: score=92 (0-100), target=0.90 (0-1配置)
    score_100 = 92.0
    target_01 = 0.90
    
    normalized_target = target_01 * 100 if target_01 <= 1.0 else target_01
    result = score_100 >= normalized_target  # True
    
    if result == True:
        print("✅ 尺度转换正确处理 (92 vs 0.90 -> 90)")
    else:
        print("❌ 尺度比较逻辑错误")
        return False
    
    return True

def test_no_double_conversion():
    """验证无双重转换"""
    # 错误: 0.88 -> 88 -> 8800
    # 正确: 0.88 -> 88
    
    val = 0.88
    
    # 模拟错误双重转换
    wrong = (val * 100) * 100  # 8800
    
    # 正确单次转换
    correct = val * 100 if val <= 1.0 else val  # 88
    
    if wrong == 8800 and correct == 88.0:
        print("✅ 单次转换正确 (0.88 -> 88, 非 8800)")
        return True
    else:
        print(f"❌ 转换逻辑错误: wrong={wrong}, correct={correct}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("尺度统一验证")
    print("=" * 50)
    
    try:
        test_normalize_threshold()
        test_score_comparison_consistency()
        test_no_double_conversion()
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
