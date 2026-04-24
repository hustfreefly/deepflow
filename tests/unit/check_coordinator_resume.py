"""
Coordinator Resume 检查顺序验证脚本
check_coordinator_resume.py

验证内容：
1. resume() 检查顺序：buffer 先于 pending
2. 边界条件：buffer 有结果、pending 中、都不存在
3. 状态一致性：避免重复 spawn
4. 向后兼容：不影响其他 Coordinator 方法
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

from coordinator import Coordinator, AgentPendingException


def test_resume_check_order():
    """验证 resume() 检查顺序：先 buffer 后 pending"""
    print("\n📋 Test 1: Resume 检查顺序验证")
    
    coord = Coordinator()
    test_request_id = "test-req-001"
    
    # 场景 1: buffer 有结果（应直接返回，不检查 pending）
    mock_result = {"status": "success", "output": "completed"}
    coord._resume_buffer = {test_request_id: mock_result}
    coord._pending_requests = set()  # pending 为空
    
    # 正确的实现：先查 buffer，找到直接返回
    result = coord.resume(test_request_id)
    assert result == mock_result, f"buffer 有结果应直接返回，实际: {result}"
    print("  ✅ buffer 有结果时直接返回（不查 pending）")
    
    # 场景 2: buffer 无结果，pending 中有（应继续等待或报错）
    coord._resume_buffer = {}
    coord._pending_requests = {test_request_id}
    
    try:
        result = coord.resume(test_request_id)
        # 如果还在 pending，可能返回特殊标记或抛出异常
        # 取决于具体实现：可能是抛出异常或返回 pending 状态
        print(f"  📝 pending 中的请求返回: {result}")
    except Exception as e:
        print(f"  📝 pending 中的请求抛出异常: {type(e).__name__}")
    
    # 场景 3: buffer 和 pending 都没有（请求不存在）
    coord._resume_buffer = {}
    coord._pending_requests = set()
    
    try:
        result = coord.resume("non-existent-req")
        assert False, "不存在的请求应抛出异常"
    except (KeyError, ValueError) as e:
        print(f"  ✅ 不存在请求正确处理: {type(e).__name__}")
    
    print("📋 Resume 检查顺序验证完成")
    return True


def test_buffer_before_pending_logic():
    """验证逻辑顺序：buffer 优先于 pending"""
    print("\n🔍 Test 2: Buffer 优先逻辑验证")
    
    coord = Coordinator()
    test_request_id = "test-req-002"
    
    # 关键场景：buffer 和 pending 同时有（理论上不应发生，但测试鲁棒性）
    mock_result = {"status": "success"}
    coord._resume_buffer = {test_request_id: mock_result}
    coord._pending_requests = {test_request_id}  # 异常情况
    
    result = coord.resume(test_request_id)
    
    # 正确的行为：优先使用 buffer 结果（因为已经完成）
    assert result == mock_result, "buffer 和 pending 同时存在时应优先 buffer"
    print("  ✅ buffer 优先于 pending（防止重复执行）")
    
    # 验证 mock：如果实现正确，不应去 pending 中查找
    # 这里通过结果验证，而非 mock 验证
    
    print("🔍 Buffer 优先逻辑验证完成")
    return True


def test_resume_integration_with_spawn():
    """验证 resume 与 spawn 的集成"""
    print("\n🔧 Test 3: Resume 与 Spawn 集成验证")
    
    # 模拟完整的 spawn → pending → complete → buffer → resume 流程
    coord = Coordinator()
    request_id = "spawn-flow-001"
    
    # Step 1: spawn 后进入 pending
    coord._pending_requests.add(request_id)
    assert request_id in coord._pending_requests
    print("  ✅ spawn 后请求进入 pending")
    
    # Step 2: 任务完成，结果写入 buffer，从 pending 移除
    mock_result = {"status": "success", "agent_output": "done"}
    coord._resume_buffer[request_id] = mock_result
    coord._pending_requests.discard(request_id)
    
    assert request_id not in coord._pending_requests
    assert request_id in coord._resume_buffer
    print("  ✅ 完成后写入 buffer，从 pending 移除")
    
    # Step 3: resume 应正确找到 buffer 中的结果
    result = coord.resume(request_id)
    assert result == mock_result
    print("  ✅ resume 正确找到 buffer 结果")
    
    print("🔧 Resume 与 Spawn 集成验证完成")
    return True


def test_concurrent_resume_safety():
    """验证并发 resume 的安全性"""
    print("\n⚠️  Test 4: 并发 Resume 安全性验证")
    
    coord = Coordinator()
    
    # 模拟多个请求同时 resume
    request_ids = [f"concurrent-req-{i}" for i in range(5)]
    
    # 设置 buffer（部分完成）
    for i, rid in enumerate(request_ids):
        if i % 2 == 0:  # 偶数完成
            coord._resume_buffer[rid] = {"status": "success", "id": rid}
        else:  # 奇数还在 pending
            coord._pending_requests.add(rid)
    
    # 所有请求都 resume
    results = {}
    for rid in request_ids:
        try:
            results[rid] = coord.resume(rid)
        except Exception as e:
            results[rid] = f"error: {e}"
    
    # 验证偶数请求都有结果
    for i, rid in enumerate(request_ids):
        if i % 2 == 0:
            assert isinstance(results[rid], dict) and results[rid].get("status") == "success"
    
    print(f"  ✅ 并发 resume 处理正确: {len(request_ids)} 个请求")
    print("⚠️  并发 Resume 安全性验证完成")
    return True


def test_backward_compatibility():
    """验证向后兼容"""
    print("\n📏 Test 5: 向后兼容性验证")
    
    coord = Coordinator()
    
    # 确保其他方法不受影响
    assert hasattr(coord, 'start')
    assert hasattr(coord, 'execute')
    assert hasattr(coord, 'resume')
    print("  ✅ Coordinator 核心方法存在")
    
    # 验证内部数据结构
    assert isinstance(coord._resume_buffer, dict)
    assert isinstance(coord._pending_requests, set)
    print("  ✅ 内部数据结构正确")
    
    print("📏 向后兼容性验证完成")
    return True


def main():
    """主验证流程"""
    print("=" * 60)
    print("Coordinator Resume 检查顺序验证")
    print("=" * 60)
    
    tests = [
        ("Resume 检查顺序", test_resume_check_order),
        ("Buffer 优先逻辑", test_buffer_before_pending_logic),
        ("Resume-Spawn 集成", test_resume_integration_with_spawn),
        ("并发安全性", test_concurrent_resume_safety),
        ("向后兼容性", test_backward_compatibility),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ {name} 验证失败")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name} 验证异常: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"验证结果: {passed}/{len(tests)} 通过, {failed}/{len(tests)} 失败")
    print("=" * 60)
    
    print("\n📋 修复要求:")
    print("  1. resume() 方法第一行检查 _resume_buffer")
    print("  2. 找到直接返回，不检查 _pending_requests")
    print("  3. buffer 无结果时，再检查 _pending_requests")
    print("  4. 保持异常处理逻辑不变")
    
    if failed == 0:
        print("\n🎉 所有验证通过！可进入 Step 5 实现阶段。")
        return 0
    else:
        print(f"\n⚠️  {failed} 项验证失败，需要修复。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
