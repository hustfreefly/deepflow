"""
P2-4 Consistency Judge (代码部分) - 数值一致性检查器

从 Ship Package 中提取所有数值声明，检测同指标不同值的矛盾。
确定性提取 + 语义分组，LLM 只负责最终裁决。
"""
import re
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Optional


# 单位换算表
UNIT_MULTIPLIERS = {
    "k": 1_000, "K": 1_000,
    "M": 1_000_000,
    "G": 1_000_000_000,
    "T": 1_000_000_000_000,
}

# 语义同义词 (用于分组)
METRIC_SYNONYMS = {
    "throughput": ["tps", "throughput", "吞吐", "写入速率", "write_rate", "ingestion"],
    "latency": ["latency", "延迟", "响应时间", "response_time", "p95", "p99", "p50"],
    "storage": ["storage", "存储", "磁盘", "disk", "容量", "capacity"],
    "availability": ["availability", "可用性", "uptime", "sla"],
    "error_rate": ["error_rate", "错误率", "丢失率", "loss_rate", "error"],
    "retention": ["retention", "保留", "ttl", "数据保留"],
    "reduction": ["reduction", "减少", "压缩比", "compression", "采样率", "sampling"],
    "replication": ["replication", "副本", "replica", "rf", "replication_factor"],
}


def extract_numeric_claims(data: Any, path: str = "") -> List[Dict[str, Any]]:
    """
    递归提取所有数值声明。

    输出: [{
        value: float (标准化后的数值),
        unit: str,
        raw: str (原始文本),
        source_path: str (JSON 路径),
        context: str (上下文文本片段),
    }]
    """
    claims: List[Dict[str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            claims.extend(extract_numeric_claims(value, new_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            claims.extend(extract_numeric_claims(item, new_path))
    elif isinstance(data, str):
        # 提取数值 + 单位
        # 匹配模式: "100k TPS", "500ms", "99.9%", "1M", "3.5GB"
        pattern = r'(\d+(?:,\d+)*(?:\.\d+)?)\s*([kKmMgGtT]?)\s*(%|ms|s|min|MB|GB|TB|TPS|ops/s|ops)?'
        for match in re.finditer(pattern, data):
            num_str = match.group(1).replace(",", "")
            suffix = match.group(2)
            unit = match.group(3) or suffix

            try:
                num = float(num_str)
            except ValueError:
                continue

            # 单位换算
            normalized = num
            if suffix in UNIT_MULTIPLIERS:
                normalized = num * UNIT_MULTIPLIERS[suffix]
            elif unit in UNIT_MULTIPLIERS:
                normalized = num * UNIT_MULTIPLIERS[unit]

            raw = match.group(0).strip()
            context_start = max(0, match.start() - 30)
            context_end = min(len(data), match.end() + 30)
            context = data[context_start:context_end]

            claims.append({
                "value": normalized,
                "unit": unit or suffix,
                "raw": raw,
                "source_path": path,
                "context": context,
            })
    elif isinstance(data, (int, float)):
        if data > 0:  # 只记录正数（0 和负数通常不是 SLA 指标）
            claims.append({
                "value": float(data),
                "unit": "",
                "raw": str(data),
                "source_path": path,
                "context": str(data),
            })

    return claims


def _classify_metric(path: str, context: str) -> Optional[str]:
    """根据路径和上下文将数值分类到语义指标"""
    text = (path + " " + context).lower()

    for metric, synonyms in METRIC_SYNONYMS.items():
        for syn in synonyms:
            if syn in text:
                return metric

    return None


def find_numeric_conflicts(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按语义分组，找同指标不同值。

    输出: [{
        metric: str,
        claims: [claim, ...],
        values: [float, ...],
        severity: "major" | "minor",
        explanation: str,
    }]
    """
    # 按语义指标分组
    groups: Dict[str, List[Dict]] = defaultdict(list)

    for claim in claims:
        metric = _classify_metric(claim["source_path"], claim["context"])
        if metric:
            groups[metric].append(claim)

    conflicts: List[Dict[str, Any]] = []

    for metric, group_claims in groups.items():
        # 去重: 相同值不算冲突
        unique_values = set()
        for c in group_claims:
            # 对于百分比，保留原始值
            if "%" in c.get("unit", "") or c["value"] <= 1.0:
                unique_values.add(round(c["value"], 4))
            else:
                unique_values.add(c["value"])

        if len(unique_values) <= 1:
            continue

        # 有冲突
        values_list = sorted(unique_values)
        max_val = max(values_list)
        min_val = min(values_list)

        if min_val == 0:
            ratio = float("inf")
        else:
            ratio = max_val / min_val

        # severity: 差 >1.5x 为 major
        severity = "major" if ratio > 1.5 else "minor"

        # 检查是否为合理的不同条件（如基准 vs 突发）
        contexts = [c["context"] for c in group_claims]
        is_conditional = any(kw in " ".join(contexts).lower()
                            for kw in ["基准", "突发", "burst", "baseline", "peak", "normal"])

        if is_conditional and severity == "major":
            severity = "minor"  # 不同条件下的数值差异降级

        conflicts.append({
            "metric": metric,
            "claims": group_claims,
            "values": values_list,
            "severity": severity,
            "ratio": round(ratio, 2),
            "is_conditional": is_conditional,
            "explanation": f"{metric}: 发现 {len(unique_values)} 个不同值 {values_list}，"
                          f"比值 {ratio:.1f}x"
                          f"{'（不同条件，降级为 minor）' if is_conditional else ''}",
        })

    # 按 severity 排序
    conflicts.sort(key=lambda x: {"major": 0, "minor": 1}.get(x["severity"], 2))

    return conflicts


def check_numeric_consistency(package: dict) -> Dict[str, Any]:
    """
    完整的数值一致性检查。

    返回: {
        total_claims: int,
        conflicts: [conflict, ...],
        major_count: int,
        minor_count: int,
        verdict: "pass" | "fail",
    }
    """
    claims = extract_numeric_claims(package)
    conflicts = find_numeric_conflicts(claims)

    major_count = sum(1 for c in conflicts if c["severity"] == "major")
    minor_count = sum(1 for c in conflicts if c["severity"] == "minor")

    # verdict: 0 major + minor ≤ 2 → pass
    verdict = "pass" if major_count == 0 and minor_count <= 2 else "fail"

    return {
        "total_claims": len(claims),
        "conflicts": conflicts,
        "major_count": major_count,
        "minor_count": minor_count,
        "verdict": verdict,
    }


if __name__ == "__main__":
    # 测试用例: 模拟 V4 的数值矛盾
    test_package = {
        "sla_constraints": [
            {"metric": "throughput", "threshold": 500000, "description": "Kafka 突发写入吞吐 ≥ 500k TPS"},
        ],
        "architecture_principles": [
            {"id": "PRINCIPLE-002", "description": "支持 10x 正常持续数分钟，基准 100k 则突发 1M TPS"},
            {"id": "PRINCIPLE-003", "description": "Tail-based Sampling 减少 90% 存储量"},
        ],
        "work_packages": [
            {
                "id": "WP-003",
                "acceptance_criteria": [
                    {"text": "突发吞吐达到 1M TPS 持续 5min 无数据丢失"},
                ],
            },
            {
                "id": "WP-002",
                "acceptance_criteria": [
                    {"text": "整体存储量减少 ≥ 80%"},
                ],
            },
        ],
        "domain_details": {
            "kafka": {"burst_throughput": "500k TPS burst (5min)"},
        },
    }

    result = check_numeric_consistency(test_package)

    print("=== 数值一致性检查测试 ===")
    print(f"  总声明: {result['total_claims']}")
    print(f"  冲突: {len(result['conflicts'])}")
    print(f"  Major: {result['major_count']}")
    print(f"  Minor: {result['minor_count']}")
    print(f"  Verdict: {result['verdict']}")

    for conflict in result["conflicts"]:
        print(f"\n  [{conflict['severity'].upper()}] {conflict['metric']}:")
        print(f"    值: {conflict['values']}")
        print(f"    比值: {conflict['ratio']}x")
        print(f"    条件差异: {conflict['is_conditional']}")
        for claim in conflict["claims"]:
            print(f"    - {claim['source_path']}: {claim['raw']} ({claim['context'][:60]})")

    # 验证
    print(f"\n✅ 测试完成 - 检测到 {result['major_count']} major + {result['minor_count']} minor 冲突")
