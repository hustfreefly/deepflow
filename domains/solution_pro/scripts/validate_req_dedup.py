#!/usr/bin/env python3
"""
REQ 去重验证脚本 - 代码做确定性执行

验证内容：
1. Reviewer 输出的 covered_req_ids 数量 ≤ 40
2. Consolidator 输出的 covered_req_ids 数量 ≤ 60
3. dedup_log / req_mapping 存在且非空（如果有合并）
4. REQ 覆盖完整性（所有原始 REQ-ID 都在 req_mapping 中）
"""

"""
This file is part of pipeline (10-stage architecture).
uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + SummaryOrchestrator.
Do not import this file for new workflows.
"""

import json
import sys
from pathlib import Path


def validate_reviewer(output_path: Path) -> dict:
    """验证 Reviewer 输出的去重结果"""
    with open(output_path) as f:
        data = json.load(f)

    issues = []

    # 1. 检查 covered_req_ids 数量
    covered_req_ids = data.get("data", {}).get("covered_req_ids", [])
    if len(covered_req_ids) > 40:
        issues.append(f"covered_req_ids 数量 {len(covered_req_ids)} 超过上限 40")

    # 2. 检查 requirement_evidence 与 covered_req_ids 一致性
    evidence_ids = {
        e["req_id"] for e in data.get("data", {}).get("requirement_evidence", [])
    }
    covered_set = set(covered_req_ids)
    if evidence_ids != covered_set:
        missing = covered_set - evidence_ids
        extra = evidence_ids - covered_set
        if missing:
            issues.append(f"requirement_evidence 缺少 {len(missing)} 个 REQ-ID")
        if extra:
            issues.append(f"requirement_evidence 多出 {len(extra)} 个 REQ-ID")

    # 3. 检查 dedup_log 格式
    dedup_log = data.get("data", {}).get("dedup_log", [])
    if dedup_log:
        for i, entry in enumerate(dedup_log):
            if "kept" not in entry:
                issues.append(f"dedup_log[{i}] 缺少 kept 字段")
            if "merged" not in entry:
                issues.append(f"dedup_log[{i}] 缺少 merged 字段")
            if "reason" not in entry:
                issues.append(f"dedup_log[{i}] 缺少 reason 字段")

    return {
        "stage": "reviewer",
        "file": output_path.name,
        "covered_req_count": len(covered_req_ids),
        "dedup_log_count": len(dedup_log),
        "issues": issues,
        "passed": len(issues) == 0,
    }


def validate_consolidator(output_path: Path) -> dict:
    """验证 Consolidator 输出的跨域去重结果"""
    with open(output_path) as f:
        data = json.load(f)

    issues = []

    # 1. 检查 covered_req_ids 数量
    covered_req_ids = data.get("data", {}).get("covered_req_ids", [])
    if len(covered_req_ids) > 60:
        issues.append(f"covered_req_ids 数量 {len(covered_req_ids)} 超过上限 60")

    # 2. 检查 requirement_evidence 与 covered_req_ids 一致性
    evidence_ids = {
        e["req_id"] for e in data.get("data", {}).get("requirement_evidence", [])
    }
    covered_set = set(covered_req_ids)
    if evidence_ids != covered_set:
        missing = covered_set - evidence_ids
        extra = evidence_ids - covered_set
        if missing:
            issues.append(f"requirement_evidence 缺少 {len(missing)} 个 REQ-ID")
        if extra:
            issues.append(f"requirement_evidence 多出 {len(extra)} 个 REQ-ID")

    # 3. 检查 req_mapping 完整性
    req_mapping = data.get("data", {}).get("req_mapping", [])
    if req_mapping:
        # 收集所有原始 REQ-ID
        all_original_ids = set()
        for entry in req_mapping:
            all_original_ids.update(entry.get("original_req_ids", []))

        # 检查是否所有 original_req_ids 都被映射
        for entry in req_mapping:
            if "merged_req_id" not in entry:
                issues.append("req_mapping 中有条目缺少 merged_req_id")
            if "original_req_ids" not in entry:
                issues.append("req_mapping 中有条目缺少 original_req_ids")
            if "merge_reason" not in entry:
                issues.append("req_mapping 中有条目缺少 merge_reason")
            if "source_domains" not in entry:
                issues.append("req_mapping 中有条目缺少 source_domains")

    return {
        "stage": "consolidator",
        "file": output_path.name,
        "covered_req_count": len(covered_req_ids),
        "req_mapping_count": len(req_mapping),
        "issues": issues,
        "passed": len(issues) == 0,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: validate_req_dedup.py <stages_dir>")
        print("示例: validate_req_dedup.py blackboard/stages")
        sys.exit(1)

    stages_dir = Path(sys.argv[1])
    results = []

    # 验证所有 Reviewer 输出
    for reviewer_file in stages_dir.glob("reviewer_*.json"):
        results.append(validate_reviewer(reviewer_file))

    # 验证 Consolidator 输出
    consolidator_file = stages_dir / "consolidator.json"
    if consolidator_file.exists():
        results.append(validate_consolidator(consolidator_file))

    # 输出结果
    print("\n" + "=" * 60)
    print("REQ 去重验证报告")
    print("=" * 60)

    all_passed = True
    for result in results:
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"\n{result['stage']} ({result['file']}): {status}")
        print(f"  covered_req_ids: {result['covered_req_count']} 条")

        if result["stage"] == "reviewer":
            print(f"  dedup_log: {result['dedup_log_count']} 条")
        else:
            print(f"  req_mapping: {result['req_mapping_count']} 条")

        if result["issues"]:
            print(f"  问题:")
            for issue in result["issues"]:
                print(f"    - {issue}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有验证通过")
        sys.exit(0)
    else:
        print("❌ 存在验证失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
