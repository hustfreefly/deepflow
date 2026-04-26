#!/usr/bin/env python3
"""简化测试：只测试初始化"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

print("[Test] 开始导入...")
from domains.solution import SolutionOrchestrator
print("[Test] 导入成功")

context = {
    "topic": "设计一个支持百万日订单的电商订单系统",
    "type": "architecture",
    "mode": "standard",
    "constraints": ["日均百万订单", "99.99%可用性", "<200ms响应时间"],
    "stakeholders": ["技术团队", "产品团队", "运维团队"]
}

print("[Test] 创建 Orchestrator...")
orch = SolutionOrchestrator(context)
print(f"[Test] Session ID: {orch.session_id}")
print(f"[Test] Pipeline: {[s.name for s in orch.domain_config.pipeline]}")
print("[Test] 初始化成功！")
