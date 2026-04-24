#!/usr/bin/env python3
"""
investment_summarizer prompt 契约验证脚本

验证清单：
1. 分析框架 v2.0 是否已嵌入
2. 核心投资逻辑段落是否存在
3. 文件优先级分层是否正确
4. 矛盾处理规则是否定义
5. 输出结构是否符合要求
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROMPT_PATH = ROOT / "prompts" / "investment_summarizer.md"


def check_summarizer_prompt():
    """验证 investment_summarizer.md"""
    violations = []
    
    if not PROMPT_PATH.exists():
        print(f"❌ {PROMPT_PATH.name} 不存在")
        return 1
    
    with open(PROMPT_PATH) as f:
        content = f.read()
    
    # 1. 检查核心投资逻辑段落
    if "核心投资逻辑" not in content:
        violations.append(("P0", "缺少核心投资逻辑段落"))
    else:
        print("✅ 包含核心投资逻辑段落")
    
    # 2. 检查分析框架标记
    if "分析框架" not in content and "Step 1:" not in content:
        violations.append(("P0", "缺少分析框架（四步法）"))
    else:
        print("✅ 包含分析框架")
    
    # 3. 检查文件优先级分层
    has_layer1 = "第一层" in content or "layer1" in content.lower()
    has_layer2 = "第二层" in content or "layer2" in content.lower()
    has_layer3 = "第三层" in content or "layer3" in content.lower()
    
    if not all([has_layer1, has_layer2, has_layer3]):
        violations.append(("P0", "缺少文件优先级分层（三层都必须有）"))
    else:
        print("✅ 包含文件优先级分层")
    
    # 4. 检查矛盾处理规则
    if "矛盾" not in content:
        violations.append(("P0", "缺少矛盾处理规则"))
    else:
        print("✅ 包含矛盾处理规则")
    
    # 5. 检查情景分析要求
    if "乐观" not in content or "中性" not in content or "悲观" not in content:
        violations.append(("P0", "缺少情景分析（乐观/中性/悲观）"))
    else:
        print("✅ 包含情景分析要求")
    
    # 6. 检查禁止行为
    if "禁止" not in content:
        violations.append(("P1", "缺少禁止行为列表"))
    else:
        print("✅ 包含禁止行为")
    
    # 7. 检查质量标准
    if "质量标准" not in content and "检查清单" not in content:
        violations.append(("P1", "缺少质量标准或检查清单"))
    else:
        print("✅ 包含质量标准")
    
    # 8. 检查是否去重（没有重复JSON结构）
    json_blocks = content.split("```json")
    if len(json_blocks) > 3:  # 允许示例 + 输出模板
        # 检查是否有重复的结构
        scenario_count = content.count("scenario_analysis")
        if scenario_count > 2:
            violations.append(("P1", f"可能有重复的JSON结构（scenario_analysis出现{scenario_count}次）"))
        else:
            print("✅ JSON结构无重复")
    else:
        print("✅ JSON结构数量合理")
    
    # 输出结果
    print(f"\n{'='*60}")
    print(f"验证结果: {PROMPT_PATH.name}")
    print(f"{'='*60}")
    
    if not violations:
        print("✅ 全部通过！无违规")
        return 0
    
    p0_count = sum(1 for v in violations if v[0] == "P0")
    p1_count = sum(1 for v in violations if v[0] == "P1")
    
    print(f"\n违规统计: P0={p0_count}, P1={p1_count}")
    print()
    
    for level, msg in violations:
        print(f"{level}: {msg}")
    
    if p0_count > 0:
        print(f"\n❌ 存在 P0 违规，必须修复")
        return 1
    else:
        print(f"\n⚠️ 存在 P1 违规，建议修复")
        return 0


if __name__ == "__main__":
    sys.exit(check_summarizer_prompt())
