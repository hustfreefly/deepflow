#!/usr/bin/env python3
"""
Propagation Checker - 验证 Solution Pro 输出中的需求传播完整性

检查项:
1. final_result.json 存在性
2. covered_req_ids 字段完整性
3. requirement_evidence 传播
4. REQ-ID 一致性
"""
import json
import sys
from pathlib import Path
from typing import List, Dict, Any


def check_propagation_breaks(final_json: Dict[str, Any]) -> List[str]:
    """
    检查传播断裂问题
    
    Args:
        final_json: final_result.json 的输出 JSON
    
    Returns:
        传播断裂的问题列表（空列表 = 全部通过）
    """
    issues = []
    
    # 检查 covered_req_ids 存在
    if "covered_req_ids" not in final_json:
        issues.append("❌ 缺少 covered_req_ids 字段")
    elif not isinstance(final_json["covered_req_ids"], list):
        issues.append("❌ covered_req_ids 不是列表类型")
    elif len(final_json["covered_req_ids"]) == 0:
        issues.append("⚠️  covered_req_ids 为空列表")
    
    # 检查 requirement_evidence 存在
    if "requirement_evidence" not in final_json:
        issues.append("❌ 缺少 requirement_evidence 字段")
    elif not isinstance(final_json["requirement_evidence"], dict):
        issues.append("❌ requirement_evidence 不是字典类型")
    elif len(final_json["requirement_evidence"]) == 0:
        issues.append("⚠️  requirement_evidence 为空字典")
    
    # 检查 REQ-ID 一致性
    if "covered_req_ids" in final_json and "requirement_evidence" in final_json:
        covered_ids = set(final_json["covered_req_ids"])
        evidence_ids = set(final_json["requirement_evidence"].keys())
        
        # covered_req_ids 应该有对应的 evidence
        missing_evidence = covered_ids - evidence_ids
        if missing_evidence:
            issues.append(f"⚠️  {len(missing_evidence)} 个 REQ-ID 缺少 evidence: {list(missing_evidence)[:5]}")
        
        # evidence 应该在 covered_req_ids 中
        extra_evidence = evidence_ids - covered_ids
        if extra_evidence:
            issues.append(f"⚠️  {len(extra_evidence)} 个 evidence 不在 covered_req_ids 中: {list(extra_evidence)[:5]}")
    
    return issues


def check_quality_issues(final_json: Dict[str, Any]) -> List[str]:
    """
    检查质量问题
    
    Args:
        final_json: final_result.json 的输出 JSON
    
    Returns:
        质量问题列表（空列表 = 全部通过）
    """
    issues = []
    
    # 检查 final_solution 存在
    if "final_solution" not in final_json:
        issues.append("❌ 缺少 final_solution 字段")
    else:
        fs = final_json["final_solution"]
        
        # 检查 executive_summary
        if "executive_summary" not in fs:
            issues.append("❌ 缺少 final_solution.executive_summary")
        
        # 检查 detailed_solution
        if "detailed_solution" not in fs:
            issues.append("⚠️  缺少 final_solution.detailed_solution")
    
    # 检查 status
    if "status" not in final_json:
        issues.append("⚠️  缺少 status 字段")
    elif final_json["status"] not in ["completed", "partial", "failed"]:
        issues.append(f"⚠️  status 值异常: {final_json['status']}")
    
    return issues


def main():
    if len(sys.argv) < 2:
        print("用法: python propagation_checker.py <blackboard_path>")
        print("示例: python propagation_checker.py .deepflow/blackboard/DeepFlow_xxx")
        sys.exit(1)
    
    bb_path = Path(sys.argv[1])
    
    if not bb_path.exists():
        print(f"❌ Blackboard 路径不存在: {bb_path}")
        sys.exit(1)
    
    # 读取 final 输出
    final_path = bb_path / "final_result.json"
    if not final_path.exists():
        print(f"❌ final_result.json 不存在")
        sys.exit(1)
    
    try:
        with open(final_path, "r", encoding="utf-8") as f:
            final_json = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ final_result.json 解析失败: {e}")
        sys.exit(1)
    
    print(f"📋 检查: {final_path}")
    print(f"   文件大小: {final_path.stat().st_size} bytes")
    print()
    
    # 检查传播断裂
    print("=" * 60)
    print("1. 传播断裂检查")
    print("=" * 60)
    propagation_issues = check_propagation_breaks(final_json)
    
    if propagation_issues:
        print(f"❌ 发现 {len(propagation_issues)} 个问题:")
        for issue in propagation_issues:
            print(f"   {issue}")
    else:
        print("✅ 传播完整性检查通过")
    
    print()
    
    # 检查质量问题
    print("=" * 60)
    print("2. 质量问题检查")
    print("=" * 60)
    quality_issues = check_quality_issues(final_json)
    
    if quality_issues:
        print(f"⚠️  发现 {len(quality_issues)} 个问题:")
        for issue in quality_issues:
            print(f"   {issue}")
    else:
        print("✅ 质量检查通过")
    
    print()
    
    # 汇总
    total_issues = len(propagation_issues) + len(quality_issues)
    
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    
    if total_issues == 0:
        print("✅ 所有检查通过")
        sys.exit(0)
    else:
        print(f"❌ 共发现 {total_issues} 个问题")
        print(f"   传播断裂: {len(propagation_issues)}")
        print(f"   质量问题: {len(quality_issues)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
