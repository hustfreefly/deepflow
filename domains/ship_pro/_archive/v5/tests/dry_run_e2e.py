#!/usr/bin/env python3
"""
Phase 1 端到端 Dry Run
用 mock 数据跑一遍完整流程，验证 LLM 执行是否有基础问题
"""

import json
import sys
from pathlib import Path

# 模拟 LLM 执行每个 prompt 的输出（基于 prompt 中的 schema）

def simulate_parser_output():
    """模拟 P1-1 Parser 的输出"""
    return {
        "format": "A",
        "quality_score": 0.85,
        "modules": [
            {
                "id": "COMP-001",
                "name": "用户认证服务",
                "description": "处理用户注册、登录、Token 管理",
                "capabilities": ["用户注册", "登录验证", "Token 管理"],
                "source_section": "Section 2.1"
            },
            {
                "id": "COMP-002",
                "name": "订单处理服务",
                "description": "处理订单创建、支付集成、状态管理",
                "capabilities": ["创建订单", "支付集成", "订单状态管理"],
                "source_section": "Section 2.2"
            },
            {
                "id": "COMP-003",
                "name": "商品目录服务",
                "description": "处理商品查询、库存管理、价格计算",
                "capabilities": ["商品查询", "库存管理", "价格计算"],
                "source_section": "Section 2.3"
            }
        ],
        "requirements": [
            {
                "id": "REQ-001",
                "text": "系统必须支持每秒 1000 次并发登录",
                "priority": "high",
                "source_section": "Section 3.1"
            },
            {
                "id": "REQ-002",
                "text": "订单创建响应时间 < 500ms",
                "priority": "high",
                "source_section": "Section 3.2"
            }
        ],
        "principles": [
            {
                "id": "PRINCIPLE-001",
                "text": "微服务架构，每个服务独立部署",
                "source_section": "Section 1.1"
            },
            {
                "id": "PRINCIPLE-002",
                "text": "事件驱动通信优先",
                "source_section": "Section 1.2"
            }
        ],
        "sla_constraints": [
            {
                "id": "SLA-001",
                "metric": "latency",
                "target": "500ms",
                "source_section": "Section 4.1"
            },
            {
                "id": "SLA-002",
                "metric": "availability",
                "target": "99.9%",
                "source_section": "Section 4.2"
            }
        ],
        "platform_capabilities": [
            {
                "id": "CAP-001",
                "name": "Kafka",
                "description": "用于异步事件通知",
                "source_section": "Section 5.1"
            },
            {
                "id": "CAP-002",
                "name": "Redis",
                "description": "用于缓存和会话存储",
                "source_section": "Section 5.2"
            }
        ],
        "data_flows": [
            {
                "id": "FLOW-001",
                "from": "COMP-001",
                "to": "COMP-002",
                "data_type": "用户Token验证",
                "source_section": "Section 6.1"
            },
            {
                "id": "FLOW-002",
                "from": "COMP-002",
                "to": "COMP-003",
                "data_type": "库存查询",
                "source_section": "Section 6.2"
            }
        ]
    }

def simulate_explorer_output():
    """模拟 P1-2 Explorer 的输出"""
    return {
        "findings": [
            {
                "id": "FIND-001",
                "category": "implicit_dependency",
                "description": "订单处理服务依赖用户认证服务进行 Token 验证，但反向依赖未声明",
                "evidence": "Section 6.1: 'FLOW-001 from COMP-001 to COMP-002 数据类型: 用户Token验证'",
                "confidence": 0.9,
                "type": "inferred",
                "related_modules": ["COMP-001", "COMP-002"],
                "impact": "high"
            },
            {
                "id": "FIND-002",
                "category": "boundary_condition",
                "description": "要求 500ms 响应时间，但订单创建涉及支付集成，可能存在网络延迟",
                "evidence": "Section 3.2: '订单创建响应时间 < 500ms' + Section 2.2: '支付集成'",
                "confidence": 0.85,
                "type": "inferred",
                "related_modules": ["COMP-002"],
                "impact": "medium"
            }
        ],
        "hypotheses": [
            {
                "id": "HYP-001",
                "description": "可能需要使用 Redis 缓存用户 Token 以提高性能",
                "reason": "SLA 要求 500ms 响应，但文档未明确提及缓存策略",
                "needs_clarification": True
            }
        ],
        "coverage_summary": {
            "total_findings": 2,
            "explicit": 0,
            "inferred": 2,
            "high_confidence": 2,
            "hypotheses_rejected": 1
        }
    }

def simulate_architect_step1_output():
    """模拟 P1-3a Architect Step 1 的输出"""
    return {
        "version": "1.0",
        "step": 1,
        "work_packages": [
            {
                "id": "WP-001",
                "title": "用户认证服务包",
                "source_modules": ["COMP-001"],
                "dependencies": [],
                "priority": "high",
                "estimated_effort": "2-3d",
                "deliverable": "可独立部署的认证服务单元"
            },
            {
                "id": "WP-002",
                "title": "订单处理服务包",
                "source_modules": ["COMP-002"],
                "dependencies": ["WP-001"],
                "priority": "high",
                "estimated_effort": "3-5d",
                "deliverable": "可独立部署的订单处理单元，含支付集成"
            },
            {
                "id": "WP-003",
                "title": "商品目录服务包",
                "source_modules": ["COMP-003"],
                "dependencies": [],
                "priority": "medium",
                "estimated_effort": "2-3d",
                "deliverable": "可独立部署的商品目录服务单元"
            }
        ],
        "orphan_modules": [],
        "merge_candidates": [],
        "coverage_check": {
            "total_modules": 3,
            "covered_modules": 3,
            "uncovered_modules": [],
            "coverage_rate": 1.0
        }
    }

def simulate_critics_output():
    """模拟 3 个 Critic 的输出"""
    coverage = {
        "critic_id": "coverage",
        "verdict": "PASS",
        "issues": [
            {
                "id": "COV-001",
                "severity": "INFO",
                "category": "coverage_gap",
                "description": "SLA-001 (500ms 延迟) 未明确分配到具体 WP",
                "evidence": "blueprint 中无 WP 明确承诺满足 SLA-001",
                "affected_wps": ["WP-002"],
                "suggested_fix": "在 WP-002 的 deliverable 中明确性能要求"
            }
        ],
        "coverage_metrics": {
            "modules_covered": 3,
            "modules_total": 3,
            "requirements_covered": 2,
            "requirements_total": 2
        },
        "summary": {
            "total_issues": 1,
            "blockers": 0,
            "warnings": 0,
            "infos": 1
        }
    }
    
    granularity = {
        "critic_id": "granularity",
        "verdict": "PASS",
        "issues": [],
        "granularity_metrics": {
            "avg_wps_per_module": 1.0,
            "max_wps_per_module": 1,
            "min_wps_per_module": 1
        },
        "summary": {
            "total_issues": 0,
            "blockers": 0,
            "warnings": 0,
            "infos": 0
        }
    }
    
    feasibility = {
        "critic_id": "feasibility",
        "verdict": "CONDITIONAL_PASS",
        "issues": [
            {
                "id": "FEA-001",
                "severity": "WARNING",
                "category": "feasibility_risk",
                "description": "WP-002 涉及支付集成，3-5d 估计可能过于乐观",
                "evidence": "支付集成通常涉及第三方 API 调试和合规审查",
                "affected_wps": ["WP-002"],
                "suggested_fix": "将 WP-002 拆分为 '订单核心' 和 '支付集成' 两个子 WP"
            }
        ],
        "feasibility_metrics": {
            "high_risk_wps": 1,
            "medium_risk_wps": 0,
            "low_risk_wps": 2
        },
        "summary": {
            "total_issues": 1,
            "blockers": 0,
            "warnings": 1,
            "infos": 0
        }
    }
    
    return coverage, granularity, feasibility

def simulate_consolidator_output():
    """模拟 P1-Consolidator 的输出"""
    return {
        "status": "CONDITIONAL_APPROVED",
        "version": "1.0",
        "work_packages": ["WP-001", "WP-002", "WP-003"],
        "dependency_graph": {
            "WP-001": [],
            "WP-002": ["WP-001"],
            "WP-003": []
        },
        "approval_metadata": {
            "critic_summary": {
                "coverage": "PASS",
                "granularity": "PASS",
                "feasibility": "CONDITIONAL_PASS"
            },
            "issue_summary": {
                "blockers": 0,
                "warnings": 1,
                "infos": 1
            }
        }
    }

def validate_output(name: str, output: dict, required_fields: list[str]) -> bool:
    """验证输出是否包含必需字段"""
    missing = [f for f in required_fields if f not in output]
    if missing:
        print(f"❌ {name} 缺少字段: {missing}")
        return False
    else:
        print(f"✅ {name} 输出格式正确")
        return True

def main():
    print("="*60)
    print("Phase 1 端到端 Dry Run")
    print("="*60)
    
    all_passed = True
    
    # P1-1 Parser
    print("\n1. P1-1 Parser")
    parser_output = simulate_parser_output()
    all_passed &= validate_output(
        "Parser",
        parser_output,
        ["format", "modules", "requirements", "principles", "sla_constraints", "data_flows"]
    )
    
    # P1-2 Explorer
    print("\n2. P1-2 Explorer")
    explorer_output = simulate_explorer_output()
    all_passed &= validate_output(
        "Explorer",
        explorer_output,
        ["findings", "hypotheses", "coverage_summary"]
    )
    
    # P1-3a Architect Step 1
    print("\n3. P1-3a Architect Step 1")
    architect_step1_output = simulate_architect_step1_output()
    all_passed &= validate_output(
        "Architect Step 1",
        architect_step1_output,
        ["work_packages", "orphan_modules", "coverage_check"]
    )
    
    # P1-4a/b/c Critics
    print("\n4. P1-4a/b/c 三个 Critic")
    coverage, granularity, feasibility = simulate_critics_output()
    all_passed &= validate_output("Coverage Critic", coverage, ["critic_id", "verdict", "issues"])
    all_passed &= validate_output("Granularity Critic", granularity, ["critic_id", "verdict", "issues"])
    all_passed &= validate_output("Feasibility Critic", feasibility, ["critic_id", "verdict", "issues"])
    
    # P1-Consolidator
    print("\n5. P1-Consolidator")
    consolidator_output = simulate_consolidator_output()
    all_passed &= validate_output(
        "Consolidator",
        consolidator_output,
        ["status", "work_packages", "dependency_graph", "approval_metadata"]
    )
    
    # 验证链式兼容性
    print("\n" + "="*60)
    print("链式兼容性验证")
    print("="*60)
    
    # Parser -> Explorer
    if "modules" in parser_output and "findings" in explorer_output:
        print("✅ Parser -> Explorer 数据流正常")
    else:
        print("❌ Parser -> Explorer 数据流断裂")
        all_passed = False
    
    # Explorer -> Architect Step 1
    if explorer_output["findings"][0]["confidence"] >= 0.7:
        print("✅ Explorer 的高置信度发现可以传递给 Architect")
    else:
        print("⚠️ Explorer 无高置信度发现")
    
    # Architect -> Critics
    if architect_step1_output["coverage_check"]["coverage_rate"] == 1.0:
        print("✅ Architect 覆盖率 100%，Critic 可以审计")
    else:
        print("❌ Architect 覆盖率不足 100%")
        all_passed = False
    
    # Critics -> Consolidator
    total_blockers = (
        coverage["summary"]["blockers"] +
        granularity["summary"]["blockers"] +
        feasibility["summary"]["blockers"]
    )
    if total_blockers == 0:
        print(f"✅ 无 BLOCKER，Consolidator 可以裁决 (status: {consolidator_output['status']})")
    else:
        print(f"⚠️ 发现 {total_blockers} 个 BLOCKER")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ Dry Run 全部通过")
        print("="*60)
        return 0
    else:
        print("❌ Dry Run 发现问题")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
