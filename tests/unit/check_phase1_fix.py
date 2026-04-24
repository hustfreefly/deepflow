#!/usr/bin/env python3
"""Phase 1 修复验证脚本：Blackboard 强制接入验证"""

import os
import sys
import json
from pathlib import Path

# 测试配置
BLACKBOARD_PATH = Path.home() / ".openclaw/workspace/.v3/blackboard"
CONTRACTS_PATH = Path.home() / ".openclaw/workspace/.deepflow/contracts"

def check_coordinator_entry():
    """验证 Coordinator 强制入口"""
    print("=" * 50)
    print("【验证 1.1】Coordinator 强制入口")
    print("=" * 50)
    
    # 检查 SYSTEM_PROMPT.md 是否包含强制入口要求
    system_prompt_path = Path.home() / ".openclaw/workspace/.deepflow/SYSTEM_PROMPT.md"
    
    if not system_prompt_path.exists():
        print("❌ SYSTEM_PROMPT.md 不存在")
        return False
    
    content = system_prompt_path.read_text()
    
    checks = [
        "coordinator.start()" in content or "`Coordinator.start()`" in content,
        "禁止主Agent直接" in content or "禁止直接" in content,
        "WAITING_AGENT" in content,
    ]
    
    if all(checks):
        print("✅ SYSTEM_PROMPT.md 已强制 Coordinator 入口")
        return True
    else:
        print(f"❌ SYSTEM_PROMPT.md 缺少强制入口要求")
        print(f"   - coordinator.start(): {'✅' if checks[0] else '❌'}")
        print(f"   - 禁止直接执行: {'✅' if checks[1] else '❌'}")
        print(f"   - WAITING_AGENT: {'✅' if checks[2] else '❌'}")
        return False

def check_blackboard_structure():
    """验证 Blackboard 目录结构"""
    print("\n" + "=" * 50)
    print("【验证 1.2】Blackboard 目录结构")
    print("=" * 50)
    
    if not BLACKBOARD_PATH.exists():
        print(f"❌ Blackboard 根目录不存在: {BLACKBOARD_PATH}")
        return False
    
    print(f"✅ Blackboard 根目录存在: {BLACKBOARD_PATH}")
    
    # 检查最近是否有 session 目录创建
    sessions = [d for d in BLACKBOARD_PATH.iterdir() if d.is_dir()]
    
    if not sessions:
        print("⚠️  暂无 session 子目录（等待任务创建）")
        return None  # 中性状态
    
    print(f"✅ 发现 {len(sessions)} 个 session 目录")
    
    # 检查 session 内容
    for session in sessions[:3]:  # 最多检查3个
        outputs = list(session.glob("*_output.md"))
        print(f"   - {session.name}: {len(outputs)} 个输出文件")
    
    return True

def check_agent_prompts():
    """验证 Agent Prompt 是否包含 Blackboard 指令"""
    print("\n" + "=" * 50)
    print("【验证 1.3】Agent Prompt Blackboard 指令")
    print("=" * 50)
    
    prompts_path = Path.home() / ".openclaw/workspace/.deepflow/prompts"
    
    if not prompts_path.exists():
        print("⚠️  prompts 目录不存在，使用内联 prompt")
        return None
    
    required_keywords = [
        "blackboard",
        "_output.md",
        "写入",
        "读取",
    ]
    
    prompt_files = list(prompts_path.glob("*.md"))
    
    if not prompt_files:
        print("⚠️  暂无 prompt 文件")
        return None
    
    all_good = True
    for prompt_file in prompt_files:
        content = prompt_file.read_text()
        has_keywords = any(kw in content for kw in required_keywords)
        
        if has_keywords:
            print(f"✅ {prompt_file.name}: 包含 Blackboard 指令")
        else:
            print(f"❌ {prompt_file.name}: 缺少 Blackboard 指令")
            all_good = False
    
    return all_good

def main():
    print("\n" + "=" * 60)
    print("Phase 1 修复验证: Blackboard 强制接入")
    print("=" * 60)
    
    results = {
        "coordinator_entry": check_coordinator_entry(),
        "blackboard_structure": check_blackboard_structure(),
        "agent_prompts": check_agent_prompts(),
    }
    
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for check, result in results.items():
        status = "✅ 通过" if result else ("⚠️  未验证" if result is None else "❌ 失败")
        print(f"{check}: {status}")
    
    # 判断是否全部通过
    passed = all(r is True for r in results.values())
    
    if passed:
        print("\n🎉 Phase 1 修复验证全部通过！")
        return 0
    else:
        print("\n⚠️  部分验证未通过，需要继续修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())
