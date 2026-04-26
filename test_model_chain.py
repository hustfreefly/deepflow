#!/usr/bin/env python3
"""测试 ModelChain 是否正常工作"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

print("[Test] 导入模块...")
from core.orchestrator_base import ModelChain, ModelChainConfig

config = ModelChainConfig(
    primary="bailian/qwen3.6-plus",
    fallback="bailian/qwen3-coder-plus",
    emergency="bailian/qwen-turbo"
)

chain = ModelChain(config)
print(f"[Test] ModelChain 创建成功")
print(f"[Test] Fallback chain: {chain.fallback_chain}")

# 测试简单调用
import asyncio

async def test_call():
    print("\n[Test] 测试模型调用...")
    try:
        result = await chain.call("请回复：OK", timeout=30)
        print(f"[Test] ✓ 调用成功")
        print(f"[Test] 结果: {result['result'][:100]}...")
        return True
    except Exception as e:
        print(f"[Test] ✗ 调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_call())
    print(f"\n[Test] {'通过' if success else '失败'}")
