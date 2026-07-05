"""
AI Native Compliance Checker — 自动审计输出质量

Version: 2.4.0
Author: DeepFlow Solution Pro
Date: 2026-06-03

两层架构：
- Layer 1: 代码检查（确定性，快速）
- Layer 2: LLM 语义检查（5 个检查器，覆盖 D1+D11 / D3 / D4 / D5 / D8）

三级判定：
- score >= 0.8 → PASS
- 0.5 <= score < 0.8 → WARNING
- score < 0.5 → FAIL

[R1-P0-3] 5 个 Layer 2 检查器都需要完整 prompt 设计
[R1-B-P1-6] 三级判定阈值
"""

from typing import Any, Callable, Dict, List, Literal, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json
import re

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

VerdictType = Literal["PASS", "WARNING", "FAIL"]

# Layer 1 weight vs Layer 2 weight
LAYER1_WEIGHT = 0.4
LAYER2_WEIGHT = 0.6

# Thresholds [R1-B-P1-6]
THRESHOLD_PASS = 0.8
THRESHOLD_WARNING = 0.5

# Prompt template directory
PROMPTS_DIR = Path(__file__).parent / "prompts"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """单个检查结果"""
    passed: bool
    score: float  # 0.0-1.0
    detail: str = ""


@dataclass
class ComplianceReport:
    """合规检查完整报告"""
    verdict: VerdictType
    layer1: Dict[str, CheckResult]
    layer2: Dict[str, CheckResult]
    score: float
    failed_checks: List[str]

    def to_dict(self) -> dict:
        """序列化为 dict"""
        return {
            "verdict": self.verdict,
            "layer1": {k: {"passed": v.passed, "score": v.score, "detail": v.detail}
                       for k, v in self.layer1.items()},
            "layer2": {k: {"passed": v.passed, "score": v.score, "detail": v.detail}
                       for k, v in self.layer2.items()},
            "score": round(self.score, 3),
            "failed_checks": self.failed_checks,
        }


# ---------------------------------------------------------------------------
# ComplianceChecker
# ---------------------------------------------------------------------------

class ComplianceChecker:
    """
    AI Native 合规检查器 — 自动审计输出质量

    两层架构：
    - Layer 1: 代码检查（确定性，快速）
    - Layer 2: LLM 语义检查（5 个检查器）

    [R1-P0-3] 5 个 Layer 2 检查器都需要完整 prompt 设计
    """

    def __init__(self, llm_judge_fn: Optional[Callable] = None, spawn_fn: Optional[Callable] = None):
        """
        Args:
            llm_judge_fn: Callable[[prompt: str, temperature: float], dict]
                          返回 {"content": "..."} 或任意含 content 的对象。
                          当为 None 时，Layer 2 自动 fallback 到规则判定（V1 兼容）。
        """
        self.llm_judge_fn = llm_judge_fn
        self._prompt_template: Optional[str] = None

        self.checkers: Dict[str, Callable] = {
            "D1_D11": self._check_d1_d11_information_conservation,
            "D3": self._check_d3_no_fallback_to_code,
            "D4": self._check_d4_prompt_is_contract,
            "D5": self._check_d5_self_validation,
            "D8": self._check_d8_no_human_time_scale,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, output: dict, context: Optional[dict] = None) -> ComplianceReport:
        """
        执行所有合规检查

        Args:
            output: 待审计的输出 dict（任意阶段的产出）
            context: 可选上下文（frozen_spec、stage_name 等）

        Returns:
            ComplianceReport
        """
        # Layer 1: 确定性代码检查
        layer1 = self._run_layer1_checks(output)

        # Layer 2: LLM 语义检查
        layer2 = self._run_layer2_checks(output, context)

        # 综合判定
        score = self._calculate_score(layer1, layer2)
        verdict = self._determine_verdict(score)
        failed = self._collect_failures(layer1, layer2)

        return ComplianceReport(
            verdict=verdict,
            layer1=layer1,
            layer2=layer2,
            score=score,
            failed_checks=failed,
        )

    # ------------------------------------------------------------------
    # Layer 1: 确定性代码检查
    # ------------------------------------------------------------------

    def _run_layer1_checks(self, output: dict) -> Dict[str, CheckResult]:
        """Layer 1: 快速确定性检查"""
        results = {}

        # 1) schema_version 存在
        results["has_schema_version"] = CheckResult(
            passed="schema_version" in output,
            score=1.0 if "schema_version" in output else 0.0,
            detail="schema_version field present" if "schema_version" in output else "missing schema_version",
        )

        # 2) constraints 存在
        has_constraints = "constraints" in output or "unified_constraints" in output
        results["has_constraints"] = CheckResult(
            passed=has_constraints,
            score=1.0 if has_constraints else 0.0,
            detail="constraints field present" if has_constraints else "missing constraints",
        )

        # 3) source citations
        has_citations = self._check_source_citations(output)
        results["has_source_citations"] = CheckResult(
            passed=has_citations,
            score=1.0 if has_citations else 0.0,
            detail="source citations found" if has_citations else "no source citations",
        )

        # 4) no empty fields
        no_empty = self._check_no_empty_fields(output)
        results["no_empty_fields"] = CheckResult(
            passed=no_empty,
            score=1.0 if no_empty else 0.0,
            detail="no empty required fields" if no_empty else "empty required fields detected",
        )

        # 5) req_ids format
        req_ok = self._check_req_id_format(output)
        results["req_ids_format"] = CheckResult(
            passed=req_ok,
            score=1.0 if req_ok else 0.0,
            detail="req_ids format valid" if req_ok else "req_ids format invalid",
        )

        return results

    def _check_source_citations(self, output: dict) -> bool:
        """检查是否存在来源引用"""
        text = json.dumps(output, ensure_ascii=False)
        # 匹配常见引用模式: source, citation, ref, 来源
        patterns = [r'"source"', r'"citation"', r'"ref"', r'"来源"', r'"evidence"']
        return any(re.search(p, text) for p in patterns)

    def _check_no_empty_fields(self, output: dict) -> bool:
        """检查关键字段不为空字符串/空列表/None"""
        required_keys = ["schema_version", "constraints", "unified_constraints"]
        for key in required_keys:
            if key in output:
                val = output[key]
                if val is None or val == "" or val == [] or val == {}:
                    return False
        return True

    def _check_req_id_format(self, output: dict) -> bool:
        """检查 req_id 格式是否合规（REQ-XXX 或类似模式）"""
        text = json.dumps(output, ensure_ascii=False)
        # 如果包含 req_id 字段，检查格式
        if "req_id" not in text and "req_ids" not in text:
            return True  # 没有 req_id 字段则跳过
        # 匹配 REQ- 前缀
        return bool(re.search(r'REQ-\w+', text))

    # ------------------------------------------------------------------
    # Layer 2: LLM 语义检查（5 个检查器）
    # ------------------------------------------------------------------

    def _run_layer2_checks(self, output: dict, context: Optional[dict]) -> Dict[str, CheckResult]:
        """Layer 2: LLM 语义检查，5 个检查器"""
        results = {}
        for checker_name, checker_fn in self.checkers.items():
            results[checker_name] = checker_fn(output, context)
        return results

    def _load_prompt_template(self) -> str:
        """加载 prompt 模板（懒加载 + 缓存）"""
        if self._prompt_template is None:
            prompt_path = PROMPTS_DIR / "compliance_checker_base.md"
            if prompt_path.exists():
                self._prompt_template = prompt_path.read_text(encoding="utf-8")
            else:
                self._prompt_template = self._default_prompt_template()
        return self._prompt_template

    def _call_llm(self, prompt: str, temperature: float = 0.2) -> Optional[dict]:
        """
        调用 LLM Judge，返回解析后的 dict。
        当 llm_judge_fn 为 None 时返回 None（触发 fallback）。
        """
        if self.llm_judge_fn is None:
            return None
        try:
            result = self.llm_judge_fn(prompt, temperature)
            if isinstance(result, dict):
                return result
            if hasattr(result, "content"):
                return json.loads(result.content)
            return None
        except Exception:
            return None

    def _check_d1_d11_information_conservation(self, output: dict, context: Optional[dict]) -> CheckResult:
        """
        D1+D11 合并: 信息守恒 + 知识新鲜度
        检查输出是否完整保留了输入的关键信息，且使用了最新信息。
        """
        prompt = self._build_checker_prompt(
            checker_id="D1_D11",
            description="信息守恒 + 知识新鲜度",
            instruction="检查输出是否完整保留了输入的关键信息，且使用了最新信息。"
                        "重点：1) 输入中的关键需求是否被遗漏？"
                        "2) 是否引用了过时的技术或数据？"
                        "3) 信息是否有丢失或扭曲？",
            output=output,
            context=context,
        )

        result = self._call_llm(prompt)
        if result is None:
            return self._fallback_information_check(output)

        score = float(result.get("score", 0.5))
        passed = score >= 0.6
        return CheckResult(passed=passed, score=score, detail=result.get("reasoning", ""))

    def _check_d3_no_fallback_to_code(self, output: dict, context: Optional[dict]) -> CheckResult:
        """
        D3: 无代码回退
        检查输出中是否有硬编码映射表、3+ if/else 分支等传统代码模式。
        """
        prompt = self._build_checker_prompt(
            checker_id="D3",
            description="无代码回退",
            instruction="检查输出中是否有硬编码映射表、3+ if/else 分支、"
                        "正则做语义分类等传统代码模式。"
                        "AI Native 要求：语义任务用 LLM，格式任务用代码。"
                        "如果发现反模式，给出具体位置和修复建议。",
            output=output,
            context=context,
        )

        result = self._call_llm(prompt)
        if result is None:
            return self._fallback_code_pattern_check(output)

        score = float(result.get("score", 0.5))
        passed = score >= 0.6
        return CheckResult(passed=passed, score=score, detail=result.get("reasoning", ""))

    def _check_d4_prompt_is_contract(self, output: dict, context: Optional[dict]) -> CheckResult:
        """
        D4: Prompt 是契约
        检查 Prompt 是否包含五要素：角色+上下文+约束+示例+输出格式。
        """
        prompt = self._build_checker_prompt(
            checker_id="D4",
            description="Prompt 是契约",
            instruction="检查输出中的 Prompt（如有）是否包含五要素："
                        "1) 角色定义 (Role)"
                        "2) 上下文 (Context)"
                        "3) 约束条件 (Constraints)"
                        "4) 示例 (Examples)"
                        "5) 输出格式 (Output Schema)"
                        "缺少 3 个以上要素则不通过。",
            output=output,
            context=context,
        )

        result = self._call_llm(prompt)
        if result is None:
            return self._fallback_prompt_contract_check(output)

        score = float(result.get("score", 0.5))
        passed = score >= 0.6
        return CheckResult(passed=passed, score=score, detail=result.get("reasoning", ""))

    def _check_d5_self_validation(self, output: dict, context: Optional[dict]) -> CheckResult:
        """
        D5: 自我验证
        检查输出是否包含不确定性标注和自我评估。
        """
        prompt = self._build_checker_prompt(
            checker_id="D5",
            description="自我验证",
            instruction="检查输出是否包含：1) 不确定性标注（如置信度、风险说明）"
                        "2) 自我评估或局限性声明"
                        "3) 对假设条件的显式标注"
                        "完全没有自我验证内容则不通过。",
            output=output,
            context=context,
        )

        result = self._call_llm(prompt)
        if result is None:
            return self._fallback_self_validation_check(output)

        score = float(result.get("score", 0.5))
        passed = score >= 0.6
        return CheckResult(passed=passed, score=score, detail=result.get("reasoning", ""))

    def _check_d8_no_human_time_scale(self, output: dict, context: Optional[dict]) -> CheckResult:
        """
        D8: 非人类时间尺度
        检查输出中是否有人类时间尺度的表述（P0-P2/下周/后续/Phase 0-4）。
        """
        prompt = self._build_checker_prompt(
            checker_id="D8",
            description="非人类时间尺度",
            instruction="检查输出中是否有人类时间尺度的表述，例如："
                        "'P0/P1/P2'、'Phase 0-4'、'下周'、'后续再做'、'未来版本'。"
                        "AI Native 要求：<1min 的修复现在就做，不做时间推诿。"
                        "如果发现人类时间尺度表述，指出具体位置。",
            output=output,
            context=context,
        )

        result = self._call_llm(prompt)
        if result is None:
            return self._fallback_time_scale_check(output)

        score = float(result.get("score", 0.5))
        passed = score >= 0.6
        return CheckResult(passed=passed, score=score, detail=result.get("reasoning", ""))

    # ------------------------------------------------------------------
    # Fallback 规则检查（V1 兼容，llm_judge_fn=None 时）
    # ------------------------------------------------------------------

    def _fallback_information_check(self, output: dict) -> CheckResult:
        """D1+D11 fallback: 基于规则的简单信息守恒检查"""
        text = json.dumps(output, ensure_ascii=False)
        score = 0.7  # 基础分
        if len(text) < 50:
            score = 0.3  # 输出太短，可能信息丢失
        if "source" in text or "ref" in text or "来源" in text:
            score = min(score + 0.15, 1.0)
        return CheckResult(passed=score >= 0.6, score=score, detail="rule_based_fallback")

    def _fallback_code_pattern_check(self, output: dict) -> CheckResult:
        """D3 fallback: 检测硬编码模式"""
        text = json.dumps(output, ensure_ascii=False)
        score = 0.8  # 基础分（假设无问题）
        # 检测 if/else 链
        if_count = len(re.findall(r'\bif\b', text))
        if if_count > 5:
            score -= 0.3
        # 检测硬编码映射
        if re.search(r'mapping\s*=\s*\{', text):
            score -= 0.2
        score = max(score, 0.0)
        return CheckResult(passed=score >= 0.6, score=score, detail="rule_based_fallback")

    def _fallback_prompt_contract_check(self, output: dict) -> CheckResult:
        """D4 fallback: 检查 prompt 五要素"""
        text = json.dumps(output, ensure_ascii=False).lower()
        elements = 0
        for keyword in ["role", "context", "constraint", "example", "output"]:
            if keyword in text:
                elements += 1
        score = elements / 5.0
        return CheckResult(passed=score >= 0.6, score=score, detail="rule_based_fallback")

    def _fallback_self_validation_check(self, output: dict) -> CheckResult:
        """D5 fallback: 检测不确定性标注"""
        text = json.dumps(output, ensure_ascii=False)
        indicators = ["confidence", "uncertain", "risk", "limitation", "假设", "不确定", "风险"]
        found = sum(1 for kw in indicators if kw in text)
        score = min(found / 3.0, 1.0)
        return CheckResult(passed=score >= 0.6, score=score, detail="rule_based_fallback")

    def _fallback_time_scale_check(self, output: dict) -> CheckResult:
        """D8 fallback: 检测人类时间尺度表述"""
        text = json.dumps(output, ensure_ascii=False)
        patterns = [r'P[0-2]', r'[Pp]hase\s*[0-4]', r'下周', r'后续', r'未来版本']
        found = sum(1 for p in patterns if re.search(p, text))
        # 有违规模式则扣分
        score = max(1.0 - found * 0.25, 0.0)
        return CheckResult(passed=score >= 0.6, score=score, detail="rule_based_fallback")

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_checker_prompt(
        self,
        checker_id: str,
        description: str,
        instruction: str,
        output: dict,
        context: Optional[dict],
    ) -> str:
        """构建单个检查器的 prompt"""
        template = self._load_prompt_template()

        output_snippet = json.dumps(output, ensure_ascii=False)[:2000]
        context_snippet = json.dumps(context or {}, ensure_ascii=False)[:500]

        return template.format(
            checker_id=checker_id,
            description=description,
            instruction=instruction,
            output_snippet=output_snippet,
            context_snippet=context_snippet,
        )

    @staticmethod
    def _default_prompt_template() -> str:
        """内嵌默认 prompt 模板（文件不存在时使用）"""
        return """## AI Native Compliance Check: {checker_id}

**检查维度**: {description}

**检查指令**:
{instruction}

**待检查输出**:
```json
{output_snippet}
```

**上下文信息**:
```json
{context_snippet}
```

## 输出要求
请输出 JSON：
{{"score": 0.0-1.0, "reasoning": "简要说明判断依据", "issues": ["问题1", "问题2"]}}

评分标准：
- 0.8-1.0: 完全合规
- 0.6-0.8: 基本合规，有小问题
- 0.4-0.6: 部分合规，需改进
- 0.0-0.4: 严重不合规
"""

    # ------------------------------------------------------------------
    # 综合评分 & 判定
    # ------------------------------------------------------------------

    def _calculate_score(
        self,
        layer1: Dict[str, CheckResult],
        layer2: Dict[str, CheckResult],
    ) -> float:
        """
        综合评分 = Layer1 × 0.4 + Layer2 × 0.6
        每层内部取平均分。
        """
        l1_scores = [r.score for r in layer1.values()]
        l2_scores = [r.score for r in layer2.values()]

        l1_avg = sum(l1_scores) / len(l1_scores) if l1_scores else 0.0
        l2_avg = sum(l2_scores) / len(l2_scores) if l2_scores else 0.0

        return round(l1_avg * LAYER1_WEIGHT + l2_avg * LAYER2_WEIGHT, 3)

    @staticmethod
    def _determine_verdict(score: float) -> VerdictType:
        """
        [R1-B-P1-6] 三级判定
        - score >= 0.8 → PASS
        - 0.5 <= score < 0.8 → WARNING
        - score < 0.5 → FAIL
        """
        if score >= THRESHOLD_PASS:
            return "PASS"
        elif score >= THRESHOLD_WARNING:
            return "WARNING"
        else:
            return "FAIL"

    @staticmethod
    def _collect_failures(
        layer1: Dict[str, CheckResult],
        layer2: Dict[str, CheckResult],
    ) -> List[str]:
        """收集所有未通过的检查项 ID"""
        failures = []
        for name, result in {**layer1, **layer2}.items():
            if not result.passed:
                failures.append(name)
        return failures


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def quick_compliance_check(output: dict, llm_judge_fn: Optional[Callable] = None, spawn_fn: Optional[Callable] = None) -> dict:
    """
    快速合规检查入口（便捷函数）

    Args:
        output: 待审计输出
        llm_judge_fn: 可选 LLM 判定函数

    Returns:
        dict (ComplianceReport.to_dict())
    """
    checker = ComplianceChecker(llm_judge_fn=llm_judge_fn, spawn_fn=spawn_fn)
    report = checker.check(output)
    return report.to_dict()


# ---------------------------------------------------------------------------
# CLI / self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 基础自测
    sample_output = {
        "schema_version": "2.0",
        "constraints": ["latency < 100ms"],
        "source": "frozen_spec_v1",
        "req_ids": ["REQ-001", "REQ-002"],
    }

    checker = ComplianceChecker()  # 无 LLM → fallback 路径
    report = checker.check(sample_output)

    print("Compliance Checker Self-Test")
    print("=" * 50)
    print(f"Verdict: {report.verdict}")
    print(f"Score:   {report.score}")
    print(f"Failed:  {report.failed_checks}")
    print()
    print("Layer 1:")
    for k, v in report.layer1.items():
        status = "✅" if v.passed else "❌"
        print(f"  {status} {k}: {v.score} — {v.detail}")
    print()
    print("Layer 2:")
    for k, v in report.layer2.items():
        status = "✅" if v.passed else "❌"
        print(f"  {status} {k}: {v.score} — {v.detail}")
