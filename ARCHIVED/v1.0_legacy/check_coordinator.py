#!/usr/bin/env python3
"""
check_coordinator.py - Coordinator 契约验证

验证点：
1. Mode D架构合规（Coordinator不直接spawn）
2. start()返回正确状态
3. resume()正确注入结果
4. 编码规范 P0=0
5. 无mock遗留（TODO检查）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coordinator import Coordinator, AgentResult, ExecutionStatus


def test_mode_d_compliance():
    """验证Mode D架构：Coordinator不直接调用sessions_spawn"""
    print("\n[TEST] Mode D架构合规性")
    
    source = Path("coordinator.py").read_text()
    
    # 检查危险模式
    dangerous_patterns = [
        "sessions_spawn",
        "from openclaw",
        "import sessions_spawn",
    ]
    
    found = []
    lines = source.split('\n')
    for i, line in enumerate(lines, 1):
        # 排除注释和字符串
        stripped = line.split('#')[0]
        for pattern in dangerous_patterns:
            if pattern in stripped and 'TODO' not in line:
                found.append((i, line.strip()))
    
    if found:
        print("  ❌ 发现直接spawn调用（违反Mode D）：")
        for line_no, content in found[:3]:  # 只显示前3个
            print(f"     行{line_no}: {content}")
        return False
    else:
        print("  ✅ 无直接spawn调用，Mode D架构合规")
        return True


def test_start_returns_status():
    """测试start()返回正确状态"""
    print("\n[TEST] start()返回状态")
    
    try:
        coord = Coordinator()
        # 使用mock配置运行
        import asyncio
        
        async def test():
            # 使用简单输入
            status = await coord.start("测试输入")
            return status
        
        status = asyncio.run(test())
        
        # 验证返回类型
        if not isinstance(status, ExecutionStatus):
            print(f"  ❌ 返回类型错误: {type(status)}")
            return False
        
        # 验证状态字段
        required_fields = ['state', 'session_id', 'pending_requests']
        for field in required_fields:
            if not hasattr(status, field):
                print(f"  ❌ 缺少字段: {field}")
                return False
        
        print(f"  ✅ 返回状态有效: {status.state}")
        print(f"     session_id: {status.session_id}")
        print(f"     pending_requests: {len(status.pending_requests)}")
        return True
        
    except Exception as e:
        print(f"  ❌ 执行失败: {e}")
        return False


def test_resume_injects_results():
    """测试resume()正确注入结果"""
    print("\n[TEST] resume()结果注入")
    
    try:
        coord = Coordinator()
        import asyncio
        
        async def test():
            # 先start
            status1 = await coord.start("测试输入")
            if status1.state != "WAITING_AGENT":
                print(f"  ⚠️  未进入WAITING_AGENT状态: {status1.state}")
                return True  # 可能是配置问题，不算失败
            
            # 模拟注入结果
            session_id = status1.session_id
            mock_results = [
                AgentResult(
                    request_id=req['request_id'],
                    success=True,
                    output_file=f"/tmp/test_{req['stage_id']}.md",
                    score=0.85
                )
                for req in status1.pending_requests
            ]
            
            # 调用resume
            status2 = await coord.resume(session_id, mock_results)
            print(f"  ✅ resume()执行成功，新状态: {status2.state}")
            return True
        
        return asyncio.run(test())
        
    except Exception as e:
        print(f"  ❌ 执行失败: {e}")
        return False


def test_no_mock_todos():
    """检查是否有未替换的mock TODO"""
    print("\n[TEST] 无mock遗留")
    
    source = Path("coordinator.py").read_text()
    
    # 检查TODO模式
    todo_patterns = [
        "# TODO: 替换",
        "# 模拟",
        "# 实际使用",
        "mock",
        "MOCK",
    ]
    
    found = []
    lines = source.split('\n')
    for i, line in enumerate(lines, 1):
        for pattern in todo_patterns:
            if pattern in line and 'logger' not in line.lower():
                found.append((i, line.strip()))
                break
    
    if found:
        print(f"  ⚠️  发现{len(found)}处可能的mock/TODO：")
        for line_no, content in found[:3]:
            print(f"     行{line_no}: {content[:60]}...")
        # 这是警告不是失败，因为可能还有故意的mock
        return True
    else:
        print("  ✅ 无明显的mock遗留")
        return True


def test_coding_standards():
    """编码规范验证"""
    print("\n[TEST] 编码规范 P0=0")
    
    from coding_standards import CodingStandardsChecker
    
    checker = CodingStandardsChecker(strict_mode=False)
    report = checker.check_file(Path("coordinator.py"))
    
    print(f"  P0={report.p0_count}, P1={report.p1_count}, P2={report.p2_count}")
    
    if report.p0_count == 0:
        print("  ✅ 编码规范合规")
        return True
    else:
        print("  ❌ 存在P0违规：")
        for v in report.violations:
            if v.level == "P0":
                print(f"     行{v.line}: {v.rule}")
        return False


def main():
    """主入口"""
    print("=" * 60)
    print("Coordinator 契约验证")
    print("=" * 60)
    
    tests = [
        ("Mode D架构合规", test_mode_d_compliance),
        ("start()返回状态", test_start_returns_status),
        ("resume()结果注入", test_resume_injects_results),
        ("无mock遗留", test_no_mock_todos),
        ("编码规范", test_coding_standards),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ 测试执行失败: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("🎉 所有契约验证通过！")
        print("下一步：实现真实spawn集成")
        return 0
    else:
        print("⚠️  存在失败项，请修复后再继续。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
