#!/usr/bin/env python3
"""
data_manager_agent prompt 契约验证脚本

验证清单：
1. DataManager Agent prompt 是否存在
2. 是否明确定义了只做数据采集，不做分析
3. 是否包含完成信号写入要求
4. 输出路径是否与原先一致
5. 是否禁止投资分析
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROMPT_PATH = ROOT / "prompts" / "data_manager_agent.md"

def check_data_manager_agent():
    """验证 data_manager_agent.md"""
    violations = []
    
    if not PROMPT_PATH.exists():
        print(f"❌ {PROMPT_PATH.name} 不存在")
        return 1
    
    with open(PROMPT_PATH) as f:
        content = f.read()
    
    # 1. 检查身份定义
    if "DataManager Agent" not in content:
        violations.append(("P0", "缺少 DataManager Agent 身份定义"))
    else:
        print("✅ 包含 DataManager Agent 身份定义")
    
    # 2. 检查禁止分析条款
    if "不做投资分析" not in content and "不写研究报告" not in content:
        violations.append(("P0", "缺少禁止分析条款"))
    else:
        print("✅ 包含禁止分析条款")
    
    # 3. 检查完成信号
    if "data_manager_completed.json" not in content:
        violations.append(("P0", "缺少完成信号写入要求"))
    else:
        print("✅ 包含完成信号写入要求")
    
    # 4. 检查关键指标生成
    if "key_metrics.json" not in content:
        violations.append(("P0", "缺少 key_metrics.json 生成要求"))
    else:
        print("✅ 包含 key_metrics.json 生成要求")
    
    # 5. 检查路径一致性（blackboard/{session_id}/data/）
    if "blackboard/{session_id}/data" not in content:
        violations.append(("P0", "缺少标准 Blackboard 路径"))
    else:
        print("✅ 包含标准 Blackboard 路径")
    
    # 6. 检查 bootstrap 采集
    if "bootstrap" not in content.lower():
        violations.append(("P0", "缺少 bootstrap 采集要求"))
    else:
        print("✅ 包含 bootstrap 采集要求")
    
    # 7. 检查搜索补充
    if "搜索" not in content and "supplement" not in content:
        violations.append(("P1", "缺少搜索补充要求"))
    else:
        print("✅ 包含搜索补充要求")
    
    # 8. 检查注册 providers
    if "register_providers" not in content:
        violations.append(("P1", "缺少数据源注册要求"))
    else:
        print("✅ 包含数据源注册要求")
    
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
    sys.exit(check_data_manager_agent())
