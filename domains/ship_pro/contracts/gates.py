"""
Ship Pro - Gate Implementations (契约笼子)

三步模式：
  Step 1: Gate.build_judge_prompt() → 声明 LLM 判断需求
  Step 2: Agent spawn Judge 子 Agent → 执行判断
  Step 3: Gate.check(judge_results=...) → 消费结果

契约铁律：
  - 确定性检查用代码（Pydantic、拓扑排序、前缀匹配）
  - 语义判断用 LLM（信息守恒、MUST 约束、Harness）
  - 没有 fallback：缺 judge_results → raise ValueError
"""
from pydantic import ValidationError
from typing import Dict, Any, List
import json


class GateResult:
    """Gate 检查结果"""
    
    def __init__(self, passed: bool, issues: List[str], details: Dict[str, Any] = None):
        # 契约笼子 B1-FIX: 智能 bool 转换，防止 LLM 返回 "false"/0 等非 bool truthy 值
        if isinstance(passed, str):
            self.passed = passed.lower() in ("true", "1", "yes")
        else:
            self.passed = bool(passed)
        self.issues = issues
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "details": self.details
        }


# ============================================================================
# PlannerGate — 纯确定性检查，不需要 LLM
# ============================================================================

class PlannerGate:
    """Phase 1 Planner 输出验证（确定性）"""
    
    @staticmethod
    def check(planner_output: Dict[str, Any]) -> GateResult:
        from ..pipeline_designer import PipelinePlan
        
        issues = []
        
        # 1. Pydantic Schema (unified: PipelinePlan replaces PlannerOutput)
        try:
            PipelinePlan.model_validate(planner_output)
        except ValidationError as e:
            return GateResult(passed=False, issues=[f"Schema 验证失败: {e}"])
        
        # 2. Worker 数量 [2, 8]
        workers = planner_output.get("workers", [])
        if not (2 <= len(workers) <= 8):
            return GateResult(passed=False, issues=[f"Worker 数量 {len(workers)} 不在 [2,8]"])
        
        # 3. DAG 无环（Kahn 拓扑排序）
        roles = [w["role"] for w in workers]
        roles_set = set(roles)
        deps_map = {w["role"]: w.get("depends_on", []) for w in workers}
        in_deg = {r: 0 for r in roles}
        for r, deps in deps_map.items():
            for d in deps:
                if d in in_deg:
                    in_deg[r] += 1
        queue = [r for r, d in in_deg.items() if d == 0]
        visited = 0
        while queue:
            cur = queue.pop(0)
            visited += 1
            for r, deps in deps_map.items():
                if cur in deps:
                    in_deg[r] -= 1
                    if in_deg[r] == 0:
                        queue.append(r)
        if visited != len(roles):
            return GateResult(passed=False, issues=["依赖图存在环"])
        
        # 3.5 depends_on 引用有效性（契约笼子：引用不存在的 Worker = 运行时崩溃）
        for w in workers:
            for dep in w.get("depends_on", []):
                if dep not in roles_set:
                    issues.append(
                        f"Worker '{w['role']}' depends_on '{dep}' 不存在于 Worker 列表中"
                    )
        
        # 3.6 input-output 接口兼容性（确定性 Layer 1）
        # 收集每个 Worker 的 interface_provides
        provides_map: Dict[str, set] = {}
        for w in workers:
            provides_map[w["role"]] = set(w.get("interface_provides", []))
        
        for w in workers:
            deps = w.get("depends_on", [])
            requires = w.get("interface_requires", [])
            # 向后兼容：空 requires 或空 deps 跳过
            if not requires or not deps:
                continue
            # 收集所有直接依赖的 interface_provides 并集
            dep_provides: set = set()
            for dep in deps:
                dep_provides.update(provides_map.get(dep, set()))
            # 检查每个 require 是否被依赖的 provides 覆盖
            for req in requires:
                if req not in dep_provides:
                    issues.append(
                        f"Worker '{w['role']}' 需要接口 '{req}' "
                        f"但依赖 {deps} 的 interface_provides 均未提供"
                    )
        
        # 4. 约束引用非空
        for w in workers:
            if not w.get("must_constraints") and not w.get("solution_pro_refs"):
                issues.append(f"Worker {w['role']} 没有约束引用")
        
        # 5. wp_id_prefix 必须存在
        for w in workers:
            if not w.get("wp_id_prefix"):
                issues.append(f"Worker {w['role']} 缺少 wp_id_prefix")
        
        if issues:
            return GateResult(passed=False, issues=issues)
        return GateResult(passed=True, issues=[], details={"worker_count": len(workers)})


# ============================================================================
# WorkerGate — 确定性 + 语义（MUST 约束）
# ============================================================================

class WorkerGate:
    """Phase 2 Worker 输出验证"""
    
    @staticmethod
    def check(worker_spec: Dict[str, Any], worker_output: Dict[str, Any],
              judge_results: Dict[str, Any] = None) -> GateResult:
        """
        契约笼子：
        - 确定性：Pydantic + WP ID 前缀
        - 语义：MUST 约束 → judge_results[f"worker_must_{role}"] 必须存在
        """
        from .worker_deliverable import WorkerDeliverable
        from .repair_adapters import legacy_array_to_worker_deliverable
        
        issues = []
        role = worker_spec.get("role", "unknown")
        
        # 0. 兼容修复：Worker 可能输出 JSON 数组（旧格式），转换为 WorkerDeliverable object
        if isinstance(worker_output, list):
            worker_output = legacy_array_to_worker_deliverable(worker_spec, worker_output)
        
        # 1. Pydantic Schema
        try:
            WorkerDeliverable.model_validate(worker_output)
        except ValidationError as e:
            return GateResult(passed=False, issues=[f"Schema 验证失败: {e}"])
        
        # 2. WP ID 前缀
        prefix = worker_spec.get("wp_id_prefix", "")
        if prefix:
            for wp in worker_output.get("work_packages", []):
                if not wp.get("id", "").startswith(prefix):
                    issues.append(f"WP ID '{wp.get('id')}' 不符合前缀 '{prefix}'")
        
        # 2.5 内容深度验证（契约铁律：代码化约束 > Prompt 声明）
        for wp in worker_output.get("work_packages", []):
            wp_id = wp.get("id", "?")
            
            # description 深度：≥100 字符
            desc = wp.get("description", "")
            if len(desc) < 100:
                issues.append(f"{wp_id}: description 太短（{len(desc)} chars，要求 ≥100）")
            
            # acceptance_criteria：≥2 条
            acs = wp.get("acceptance_criteria", [])
            if len(acs) < 2:
                issues.append(f"{wp_id}: acceptance_criteria 不足（{len(acs)} 条，要求 ≥2）")
            
            # deliverables：≥1 项
            dels = wp.get("deliverables", [])
            if len(dels) < 1:
                issues.append(f"{wp_id}: deliverables 为空（要求 ≥1 项）")
        
        # 3. MUST 约束（语义 — 契约笼子）
        must_constraints = worker_spec.get("must_constraints", [])
        if must_constraints:
            task_name = f"worker_must_{role}"
            if judge_results is None or task_name not in judge_results:
                raise ValueError(
                    f"契约笼子违规: Worker {role} MUST 约束 Judge '{task_name}' 未提供"
                )
            verdict = judge_results[task_name]
            if not verdict.get("passed", False):
                issues.extend(verdict.get("issues", ["MUST 约束检查失败"]))
        
        # 4. web_search 结构性检查
        # 确定性：需要搜索时是否有搜索日志
        if worker_spec.get("needs_web_search") and not worker_output.get("web_search_logs"):
            issues.append("需要 web_search 但无搜索日志")
        # 语义检查（搜索是否在范围内）交给 Layer 2 MUST Judge
        # 不在代码层做关键词匹配 — 关键词匹配是反模式（用尺子量温度）
        
        return GateResult(passed=len(issues) == 0, issues=issues)
    
    @staticmethod
    def build_judge_prompt(worker_spec: Dict[str, Any],
                           worker_output: Dict[str, Any]) -> str:
        """构建 MUST 约束 Judge prompt（Step 1）"""
        mc = worker_spec.get("must_constraints", [])
        wps = worker_output.get("work_packages", [])
        web_search_scope = worker_spec.get("web_search_scope", "")
        search_logs = worker_output.get("web_search_logs", [])
        return f"""你是一个约束验证专家。判断 Worker 交付物是否保留了所有 MUST 约束。

## MUST 约束
{json.dumps(mc, indent=2, ensure_ascii=False)}

## Worker 交付物摘要
角色: {worker_spec.get('role')}
工作包: {json.dumps([wp.get('title','') for wp in wps], ensure_ascii=False)}
验收标准数: {sum(len(wp.get('acceptance_criteria',[])) for wp in wps)}

## 附加语义检查

### 1. Worker 不应在 description 中写代码
检查每个工作包的 description 字段。如果 description 中包含实际代码逻辑
（函数定义、类定义、算法实现等，而非仅仅是技术术语或文件名），标记为问题。
注意：技术术语（如 "使用 Redis 缓存"）不算代码，实际代码片段（如 def foo(): ...）才算。

### 2. web_search 范围检查
{f'要求的搜索范围: {web_search_scope}' if web_search_scope else '无搜索范围要求'}
{f'搜索日志:\n' + json.dumps([l.get('query','') for l in search_logs], ensure_ascii=False) if search_logs else '无搜索日志'}
{f'判断每次搜索是否在 "{web_search_scope}" 范围内。语义判断即可，不要求关键词精确匹配。' if web_search_scope else ''}

## 判断标准
- 每个 MUST 约束必须有语义对应（不要求字面匹配）
- 违反或遗漏必须指出
- 上述附加检查项也需要判断

## 输出 JSON
{{"passed": true/false, "issues": ["..."]}}

只输出 JSON。"""


# ============================================================================
# InformationConservationGate — 语义（信息守恒）
# ============================================================================

class InformationConservationGate:
    """G1: 信息守恒检查"""
    
    @staticmethod
    def check(solution_pro_output: Dict[str, Any], ship_package: Dict[str, Any],
              judge_results: Dict[str, Any] = None) -> GateResult:
        """
        契约笼子：judge_results["info_conservation"] 必须存在。
        """
        task_name = "info_conservation"
        if judge_results is None or task_name not in judge_results:
            raise ValueError(
                f"契约笼子违规: InformationConservationGate 需要 '{task_name}' Judge 结果"
            )
        
        verdict = judge_results[task_name]
        passed = verdict.get("passed", False)
        issues = verdict.get("issues", [])
        details = {"conservation_rate": verdict.get("conservation_rate", 0.0)}
        return GateResult(passed=passed, issues=issues, details=details)
    
    @staticmethod
    def build_judge_prompt(solution_pro_output: Dict[str, Any],
                           ship_package: Dict[str, Any]) -> str:
        """构建信息守恒 Judge prompt（Step 1）"""
        sol_decisions = [
            d.get('description', d.get('decision', ''))[:80]
            for d in solution_pro_output.get('key_decisions', [])
        ]
        sol_components = [
            c.get('name', str(c)[:60])
            for c in solution_pro_output.get('architecture', {}).get('components', [])
            if isinstance(c, dict)
        ]
        sol_requirements = solution_pro_output.get('requirements', [])
        if not sol_requirements:
            sol_requirements = [
                {'id': rid} for rid in solution_pro_output.get('covered_req_ids', [])
            ]
        ship_wps = ship_package.get('work_packages', [])
        
        # 契约笼子：提取 semantic_anchors 纳入信息守恒检查
        sol_anchors = solution_pro_output.get('semantic_anchors', [])
        anchor_names = [a.get('name', '?') for a in sol_anchors] if sol_anchors else []
        ship_anchor_coverage = ship_package.get('anchor_coverage', {})
        ship_anchors_preserved = ship_package.get('semantic_anchors', [])
        
        anchors_section = ""
        if anchor_names:
            # 检查哪些 anchor 被 WP 引用了
            ship_wp_anchors = set()
            for wp in ship_wps:
                for a in wp.get('anchored_to', []):
                    ship_wp_anchors.add(a)
            uncovered_anchors = set(anchor_names) - ship_wp_anchors
            anchors_section = f"""

## Semantic Anchors（{len(anchor_names)} 个 — 契约笼子强制检查）
上游 anchors: {json.dumps(anchor_names, ensure_ascii=False)}
Ship Package 保留: {json.dumps([a.get('name','?') for a in ship_anchors_preserved], ensure_ascii=False)}
被 WP 引用的 anchors: {json.dumps(sorted(ship_wp_anchors), ensure_ascii=False)}
未被引用的 anchors: {json.dumps(sorted(uncovered_anchors), ensure_ascii=False)}
"""
        
        return f"""你是一个信息守恒验证专家。判断 Ship Package 是否保留了 Solution Pro 的完整意图。

## Solution Pro 关键决策（{len(sol_decisions)} 个）
{json.dumps(sol_decisions, indent=2, ensure_ascii=False)}

## Solution Pro 组件（{len(sol_components)} 个）
{json.dumps(sol_components, ensure_ascii=False)}

## Solution Pro 需求（{len(sol_requirements)} 个）
{json.dumps([r.get('description', r.get('id', str(r)[:60]))[:80] for r in sol_requirements[:15]], ensure_ascii=False)}{anchors_section}

## Ship Package 摘要
工作包数: {len(ship_wps)}
标题: {json.dumps([wp.get('title','') for wp in ship_wps], ensure_ascii=False)}
依赖边数: {len(ship_package.get('dependency_graph', dict()).get('edges', []))}
延迟需求: {json.dumps(ship_package.get('metadata', dict()).get('pending_req_ids', []), ensure_ascii=False)}

## 判断标准
1. 决策保持：每个关键决策必须有对应工作包实现
2. 组件保持：每个架构组件必须有对应工作包
3. 需求保持：每个覆盖需求必须有对应工作包语义覆盖（不要求字面匹配）
4. 信息新增：不允许引入 Solution Pro 没有的功能
5. 延迟需求：pending_req_ids 必须在 metadata 中显式记录
6. **Semantic Anchor 守恒**：每个上游 anchor 必须出现在 ship_package.semantic_anchors 中，且至少被一个 WP 的 anchored_to 引用。未引用的 anchor = 信息丢失。

## 输出 JSON
{{"passed": true/false, "issues": ["..."], "conservation_rate": 0.0-1.0}}

只输出 JSON。"""


# ============================================================================
# CompletenessGate — 纯确定性（REQ-ID 覆盖）
# ============================================================================

def legacy_string_completeness_check(solution_pro_output: Dict[str, Any],
                                      planner_output: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy REQ-ID 字符串匹配（仅供 diagnostics，不再作为 Gate 判定）。
    
    Returns:
        {"mode": "string_match", "total_req_ids": int, "covered": int,
         "coverage_rate": float, "worker_coverage": dict, "missing": list}
    """
    def _extract_req_ids(data: dict) -> list:
        if isinstance(data, dict) and 'covered_req_ids' in data:
            return list(set(data['covered_req_ids']))
        return []
    
    def _extract_covered(planner: dict) -> list:
        ids = []
        for w in planner.get('workers', []):
            ids.extend(w.get('covered_req_ids', []))
        return list(set(ids))
    
    req_ids = _extract_req_ids(solution_pro_output)
    covered = _extract_covered(planner_output)
    missing = set(req_ids) - set(covered)
    rate = len(set(req_ids) & set(covered)) / len(req_ids) if req_ids else 1.0
    worker_cov = {
        w.get('role', '?'): len(w.get('covered_req_ids', []))
        for w in planner_output.get('workers', [])
    }
    return {
        "mode": "string_match",
        "total_req_ids": len(req_ids),
        "covered": len(covered),
        "coverage_rate": rate,
        "worker_coverage": worker_cov,
        "missing": sorted(missing),
    }


class CompletenessGate:
    """
    G2: 完整性验证
    
    契约铁律：judge_results["completeness"] 必须存在。
    不再有 string-match fallback — 缺失 judge 结果 = raise ValueError。
    """
    
    @staticmethod
    def check(solution_pro_output: Dict[str, Any],
              planner_output: Dict[str, Any],
              judge_results: Dict[str, Any] = None) -> GateResult:
        # 契约笼子：judge_results 必须存在且包含 completeness key
        if judge_results is None or "completeness" not in judge_results:
            raise ValueError(
                "契约笼子违规: CompletenessGate 需要 judge_results['completeness']。"
                "缺失 judge 结果不允许 fallback 到字符串匹配。"
                "请先执行 prepare_gate_judge_tasks() 并 spawn Judge Agent。"
            )
        
        verdict = judge_results["completeness"]
        passed = verdict.get("passed", False)
        issues = verdict.get("issues", [])
        rate = verdict.get("coverage_rate", 0.0)
        
        # 契约笼子 B2-FIX: 确定性二次校验 — LLM 声称 passed 但数据不支撑 → 强制 False
        if passed:
            if isinstance(rate, (int, float)) and rate < 0.8:
                passed = False
                issues.append(f"B2 契约笼子: coverage_rate={rate} < 0.8，强制覆盖 passed=False")
            critical_issues = [
                i for i in issues
                if isinstance(i, dict) and i.get("severity") == "CRITICAL"
            ]
            if critical_issues:
                passed = False
                issues.append(f"B2 契约笼子: {len(critical_issues)} 个 CRITICAL issue，强制覆盖 passed=False")
        
        details = {
            "mode": "llm_judge",
            "coverage_rate": rate,
            "covered_decisions": verdict.get("covered_decisions", []),
            "uncovered_decisions": verdict.get("uncovered_decisions", []),
            "covered_risks": verdict.get("covered_risks", []),
            "uncovered_risks": verdict.get("uncovered_risks", []),
        }
        return GateResult(passed=passed, issues=issues, details=details)

    @staticmethod
    def build_adversarial_prompt(solution_pro_output: Dict[str, Any],
                                  planner_output: Dict[str, Any],
                                  ship_package: Dict[str, Any]) -> str:
        """
        L2 对抗审查 Agent prompt。

        与原有 CompletenessGate 的区别:
        1. 默认立场: "这个 ship_package 有问题"（对抗心态）
        2. 输出结构化修复建议（不只是报告问题）
        3. 检查维度更广（语义偏离、矛盾、耦合等）
        """
        decisions = solution_pro_output.get('key_decisions', [])
        requirements = solution_pro_output.get('requirements', [])
        risks = solution_pro_output.get('risk_mitigations', [])
        wps = ship_package.get('work_packages', [])
        workers = planner_output.get('workers', [])

        return f"""# 对抗完整性审查 Agent

> **角色定位**: 你是 Ship Pro 的完整性上限守卫。
> 你的默认立场是"这个 Ship Package 有遗漏"。
> Ship Package 必须用证据说服你它是完整的，而不是你默认它完整然后找问题。

## 审查维度

### 1. 决策覆盖（关键）
每个 key_decision 是否有对应的 WP 实现？
- 不仅检查"有没有 WP 提到这个决策"
- 还要检查"WP 的实现方案是否与决策一致"
- 例: 决策说"Fallback chain + charset-normalizer"，WP 只说"UTF-8 读取" → 不算覆盖

### 2. 需求覆盖
每个 requirement 是否有 WP 语义覆盖？
- 不要求字面匹配，但要求实质覆盖

### 3. 风险缓解覆盖
每个 risk_mitigation 是否有 WP 的 AC 或 description 覆盖？

### 4. 架构一致性
Ship Package 的依赖图是否与 Solution Pro 的架构组件关系一致？

### 5. 语义偏离检测
是否有 WP 的实现方案偏离了 Solution Pro 的设计意图？

## 输入
### Solution Pro key_decisions
{json.dumps(decisions, indent=2, ensure_ascii=False)}

### Solution Pro requirements
{json.dumps(requirements, indent=2, ensure_ascii=False)}

### Solution Pro risk_mitigations
{json.dumps(risks, indent=2, ensure_ascii=False)}

### Ship Package WPs
{json.dumps(wps, indent=2, ensure_ascii=False)}

### Planner Workers
{json.dumps(workers, indent=2, ensure_ascii=False)}

## 输出格式（JSON）
{{
  "passed": true/false,
  "coverage_rate": 0.0-1.0,
  "issues": [
    {{
      "severity": "CRITICAL/MAJOR/MINOR",
      "dimension": "decision/requirement/risk/architecture/semantic",
      "description": "问题描述",
      "repair_suggestion": "具体修复建议（建议新增/修改哪个 WP）"
    }}
  ],
  "covered_decisions": ["D1", ...],
  "uncovered_decisions": ["D5", ...],
  "covered_risks": [...],
  "uncovered_risks": [...]
}}

## 判断标准
- coverage_rate >= 0.9 且无 CRITICAL issue → passed = true
- 否则 → passed = false

请直接输出 JSON。"""


# ============================================================================
# HarnessV3 — 确定性 + 语义（质量评估）
# ============================================================================

class HarnessV3:
    """G3: Harness 验证"""
    
    @staticmethod
    def check(ship_package: Dict[str, Any],
              judge_results: Dict[str, Any] = None) -> GateResult:
        """
        契约笼子：
        - 确定性：WP 数量、AC 数量
        - 语义：judge_results["harness_v3"] 必须存在
        """
        issues = []
        wps = ship_package.get('work_packages', [])
        
        # Layer 1: 确定性
        if not (3 <= len(wps) <= 80):
            issues.append(f"WP 数量 {len(wps)} 不在 [3,80]")
        low_ac = [wp.get('id','?') for wp in wps if len(wp.get('acceptance_criteria',[])) < 2]
        if low_ac:
            issues.append(f"{len(low_ac)} 个 WP 的 AC < 2")
        
        # Layer 2: 语义（契约笼子）
        task_name = "harness_v3"
        if judge_results is None or task_name not in judge_results:
            raise ValueError(
                f"契约笼子违规: HarnessV3 需要 '{task_name}' Judge 结果"
            )
        
        verdict = judge_results[task_name]
        llm_issues = verdict.get("issues", [])
        score = verdict.get("score", 0)
        all_issues = issues + llm_issues
        
        # B1-FIX: 先转换 verdict passed，再做 and 运算（防止 "false" and True = True）
        raw_passed = verdict.get("passed", False)
        if isinstance(raw_passed, str):
            llm_passed = raw_passed.lower() in ("true", "1", "yes")
        else:
            llm_passed = bool(raw_passed)
        
        return GateResult(
            passed=llm_passed and len(issues) == 0,
            issues=all_issues,
            details={"score": score, "code_issues": len(issues), "llm_issues": len(llm_issues)}
        )
    
    @staticmethod
    def build_judge_prompt(ship_package: Dict[str, Any]) -> str:
        """构建 Harness Judge prompt（Step 1）"""
        wps = ship_package.get('work_packages', [])
        summaries = [
            {"id": wp.get('id'), "title": wp.get('title',''),
             "ac": len(wp.get('acceptance_criteria',[])),
             "deps": len(wp.get('dependencies',[]))}
            for wp in wps[:20]
        ]
        return f"""你是一个工程验证专家。验证 Ship Package 是否满足 Harness 标准。

## 摘要
WP 数: {len(wps)}
依赖边: {len(ship_package.get('dependencies', []))}
执行层: {len(ship_package.get('execution_layers', []))}

## WP 详情（前 20）
{json.dumps(summaries, indent=2, ensure_ascii=False)}

## 标准
1. 粒度合理
2. 无过度耦合
3. AC 可验证（非模糊描述）

## 输出 JSON
{{"passed": true/false, "score": 0-10, "issues": ["..."]}}

只输出 JSON。"""
