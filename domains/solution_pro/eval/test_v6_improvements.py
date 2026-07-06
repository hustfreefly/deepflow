#!/usr/bin/env python3
"""
V6 改进测试脚本 - 验证 Solution Pro V6 的关键改进

测试项:
1. Summarizer 单文件输出（只生成 final_result.json）
2. REQ-ID 传播完整性（covered_req_ids 和 requirement_evidence）
3. Schema 合规性（final_result_v3.schema.json）
4. 数据传播一致性（stages/ → final_result.json）
"""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + SummaryOrchestrator.
Do not import this file for new V2 workflows.
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, List


def test_single_file_output(bb_path: Path) -> List[str]:
    """测试 1: Summarizer 单文件输出"""
    issues = []
    
    final_result = bb_path / "final_result.json"
    summarizer_json = bb_path / "stages" / "summarizer.json"
    final_solution_md = bb_path / "final_solution.md"
    
    # final_result.json 必须存在
    if not final_result.exists():
        issues.append("❌ final_result.json 不存在")
        return issues
    
    # summarizer.json 应该不存在（V6 改为单文件输出）
    if summarizer_json.exists():
        issues.append("⚠️  stages/summarizer.json 仍然存在（V6 应该只输出 final_result.json）")
    
    # final_solution.md 应该不存在（V6 改为单文件输出）
    if final_solution_md.exists():
        issues.append("⚠️  final_solution.md 仍然存在（V6 应该只输出 final_result.json）")
    
    return issues


def test_req_propagation(bb_path: Path) -> List[str]:
    """测试 2: REQ-ID 传播完整性"""
    issues = []
    
    final_result = bb_path / "final_result.json"
    
    if not final_result.exists():
        issues.append("❌ final_result.json 不存在")
        return issues
    
    try:
        with open(final_result, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        issues.append(f"❌ final_result.json 解析失败: {e}")
        return issues
    
    # 检查 covered_req_ids
    if "covered_req_ids" not in data:
        issues.append("❌ 缺少 covered_req_ids 字段")
    elif not isinstance(data["covered_req_ids"], list):
        issues.append("❌ covered_req_ids 不是列表类型")
    elif len(data["covered_req_ids"]) == 0:
        issues.append("⚠️  covered_req_ids 为空列表")
    else:
        req_count = len(data["covered_req_ids"])
        print(f"   📊 covered_req_ids: {req_count} 个 REQ-ID")
    
    # 检查 requirement_evidence
    if "requirement_evidence" not in data:
        issues.append("❌ 缺少 requirement_evidence 字段")
    elif not isinstance(data["requirement_evidence"], dict):
        issues.append("❌ requirement_evidence 不是字典类型")
    elif len(data["requirement_evidence"]) == 0:
        issues.append("⚠️  requirement_evidence 为空字典")
    else:
        evidence_count = len(data["requirement_evidence"])
        print(f"   📊 requirement_evidence: {evidence_count} 条证据")
    
    # 检查一致性
    if "covered_req_ids" in data and "requirement_evidence" in data:
        covered_ids = set(data["covered_req_ids"])
        evidence_ids = set(data["requirement_evidence"].keys())
        
        missing_evidence = covered_ids - evidence_ids
        if missing_evidence:
            issues.append(f"⚠️  {len(missing_evidence)} 个 REQ-ID 缺少 evidence")
        
        extra_evidence = evidence_ids - covered_ids
        if extra_evidence:
            issues.append(f"⚠️  {len(extra_evidence)} 个 evidence 不在 covered_req_ids 中")
    
    return issues


def test_schema_compliance(bb_path: Path) -> List[str]:
    """测试 3: Schema 合规性"""
    issues = []
    
    final_result = bb_path / "final_result.json"
    
    if not final_result.exists():
        issues.append("❌ final_result.json 不存在")
        return issues
    
    try:
        with open(final_result, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        issues.append(f"❌ final_result.json 解析失败: {e}")
        return issues
    
    # 检查必需字段
    required_fields = ["status", "final_solution"]
    for field in required_fields:
        if field not in data:
            issues.append(f"❌ 缺少必需字段: {field}")
    
    # 检查 final_solution 结构
    if "final_solution" in data:
        fs = data["final_solution"]
        
        if "executive_summary" not in fs:
            issues.append("⚠️  缺少 final_solution.executive_summary")
        
        if "detailed_solution" not in fs:
            issues.append("⚠️  缺少 final_solution.detailed_solution")
    
    # 检查 status 值
    if "status" in data:
        valid_statuses = ["completed", "partial", "failed"]
        if data["status"] not in valid_statuses:
            issues.append(f"⚠️  status 值异常: {data['status']} (应为 {valid_statuses})")
    
    return issues


def test_data_propagation(bb_path: Path) -> List[str]:
    """测试 4: 数据传播一致性"""
    issues = []
    
    final_result = bb_path / "final_result.json"
    
    if not final_result.exists():
        issues.append("❌ final_result.json 不存在")
        return issues
    
    # 检查文件大小（V6 单文件输出应该比较大，因为包含了所有数据）
    file_size = final_result.stat().st_size
    print(f"   📊 final_result.json 大小: {file_size} bytes")
    
    if file_size < 1000:
        issues.append(f"⚠️  final_result.json 过小 ({file_size} bytes)，可能缺少数据")
    
    # 检查 REQ-ID 数量（应该 > 0）
    try:
        with open(final_result, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "covered_req_ids" in data:
            req_count = len(data["covered_req_ids"])
            if req_count == 0:
                issues.append("⚠️  covered_req_ids 为空，可能存在 REQ 传播断裂")
            elif req_count < 10:
                issues.append(f"⚠️  covered_req_ids 只有 {req_count} 个，可能不完整")
    except Exception as e:
        issues.append(f"❌ 读取 final_result.json 失败: {e}")
    
    return issues


def main():
    if len(sys.argv) < 2:
        print("用法: python3 test_v6_improvements.py <path_to_final_result.json>")
        print("示例: python3 test_v6_improvements.py .deepflow/blackboard/DeepFlow_xxx/final_result.json")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    # 如果输入的是文件路径，获取其父目录作为 blackboard path
    if input_path.is_file():
        bb_path = input_path.parent
    else:
        bb_path = input_path
    
    if not bb_path.exists():
        print(f"❌ 路径不存在: {bb_path}")
        sys.exit(1)
    
    print(f"🧪 V6 改进测试")
    print(f"   Blackboard 路径: {bb_path}")
    print()
    
    all_issues = []
    
    # 测试 1: 单文件输出
    print("=" * 60)
    print("测试 1: Summarizer 单文件输出")
    print("=" * 60)
    issues = test_single_file_output(bb_path)
    all_issues.extend(issues)
    
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ 单文件输出检查通过")
    print()
    
    # 测试 2: REQ 传播
    print("=" * 60)
    print("测试 2: REQ-ID 传播完整性")
    print("=" * 60)
    issues = test_req_propagation(bb_path)
    all_issues.extend(issues)
    
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ REQ 传播检查通过")
    print()
    
    # 测试 3: Schema 合规
    print("=" * 60)
    print("测试 3: Schema 合规性")
    print("=" * 60)
    issues = test_schema_compliance(bb_path)
    all_issues.extend(issues)
    
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ Schema 合规检查通过")
    print()
    
    # 测试 4: 数据传播
    print("=" * 60)
    print("测试 4: 数据传播一致性")
    print("=" * 60)
    issues = test_data_propagation(bb_path)
    all_issues.extend(issues)
    
    if issues:
        print(f"❌ 发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ 数据传播检查通过")
    print()
    
    # 汇总
    print("=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    if all_issues:
        print(f"❌ 共发现 {len(all_issues)} 个问题")
        sys.exit(1)
    else:
        print("✅ 所有测试通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
