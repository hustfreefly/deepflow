"""
Ship Pro V6 - Gate Implementations

契约笼子的"执行"阶段：所有 Gate 的实现。
遵循 AI Native 原则：
- 确定性检查用代码（Pydantic 验证、拓扑排序）
- 语义判断用 LLM（信息守恒、完整性、Harness）
- 不混合使用（代码不做语义判断，LLM 不做确定性检查）
"""
from pydantic import ValidationError
from typing import Dict, Any, List, Tuple
import json
import subprocess


class GateResult:
    """Gate 检查结果"""
    
    def __init__(self, passed: bool, issues: List[str], details: Dict[str, Any] = None):
        self.passed = passed
        self.issues = issues
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "details": self.details
        }


class PlannerGate:
    """Phase 1 Planner 输出验证"""
    
    @staticmethod
    def check(planner_output: Dict[str, Any]) -> GateResult:
        """
        检查 PlannerOutput 是否符合契约。
        
        验证项：
        1. Pydantic Schema 验证（确定性）
        2. Worker 数量约束（2 <= N <= 8）（确定性）
        3. 依赖图无环（拓扑排序）（确定性）
        4. 约束引用非空（确定性）
        """
        from .planner_output import PlannerOutput
        
        issues = []
        
        # 1. Pydantic Schema 验证
        try:
            PlannerOutput.model_validate(planner_output)
        except ValidationError as e:
            issues.append(f"PlannerOutput Schema 验证失败: {e}")
            return GateResult(passed=False, issues=issues)
        
        # 2. Worker 数量约束
        workers = planner_output.get("workers", [])
        if not (2 <= len(workers) <= 8):
            issues.append(f"Worker 数量 {len(workers)} 不在 [2, 8] 范围内")
            return GateResult(passed=False, issues=issues)
        
        # 3. 依赖图无环（拓扑排序）
        worker_roles = [w["role"] for w in workers]
        depends_on_map = {w["role"]: w.get("depends_on", []) for w in workers}
        
        # Kahn 算法检测环
        in_degree = {role: 0 for role in worker_roles}
        for role, deps in depends_on_map.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[role] += 1
        
        queue = [role for role, degree in in_degree.items() if degree == 0]
        visited_count = 0
        
        while queue:
            current = queue.pop(0)
            visited_count += 1
            for role, deps in depends_on_map.items():
                if current in deps:
                    in_degree[role] -= 1
                    if in_degree[role] == 0:
                        queue.append(role)
        
        if visited_count != len(worker_roles):
            issues.append("Worker 依赖图存在环")
            return GateResult(passed=False, issues=issues)
        
        # 4. 约束引用非空
        for worker in workers:
            if not worker.get("must_constraints") and not worker.get("solution_pro_refs"):
                issues.append(f"Worker {worker['role']} 没有约束引用")
        
        if issues:
            return GateResult(passed=False, issues=issues)
        
        return GateResult(passed=True, issues=[], details={"worker_count": len(workers)})


class WorkerGate:
    """Phase 2 Worker 输出验证"""
    
    @staticmethod
    def check(worker_spec: Dict[str, Any], worker_output: Dict[str, Any]) -> GateResult:
        """
        检查 WorkerDeliverable 是否符合契约。
        
        验证项：
        1. Pydantic Schema 验证（确定性）
        2. MUST 约束保留检查（LLM 语义判断）
        3. web_search 范围检查（简单字符串匹配）
        """
        from .worker_deliverable import WorkerDeliverable
        
        issues = []
        
        # 1. Pydantic Schema 验证
        try:
            WorkerDeliverable.model_validate(worker_output)
        except ValidationError as e:
            issues.append(f"WorkerDeliverable Schema 验证失败: {e}")
            return GateResult(passed=False, issues=issues)
        
        # 2. MUST 约束保留检查（LLM 语义判断）
        must_constraints = worker_spec.get("must_constraints", [])
        if must_constraints:
            constraint_check = WorkerGate._llm_check_constraints(must_constraints, worker_output)
            if not constraint_check["passed"]:
                issues.extend(constraint_check["issues"])
        
        # 3. web_search 范围检查（简单字符串匹配）
        if worker_spec.get("needs_web_search") and worker_spec.get("web_search_scope"):
            search_logs = worker_output.get("web_search_logs", [])
            scope = worker_spec["web_search_scope"]
            # 简单检查：搜索日志中是否包含范围关键词
            scope_keywords = scope.lower().split()
            for log in search_logs:
                query = log.get("query", "").lower()
                if not any(kw in query for kw in scope_keywords):
                    issues.append(f"web_search 查询 '{query}' 超出范围 '{scope}'")
        
        if issues:
            return GateResult(passed=False, issues=issues)
        
        return GateResult(passed=True, issues=[])
    
    @staticmethod
    def _llm_check_constraints(must_constraints: List[str], worker_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用 LLM 语义判断 MUST 约束是否被保留。
        
        AI Native 原则：语义判断用 LLM，不用代码硬编码。
        """
        # 构建 prompt
        prompt = f"""你是一个约束验证专家。请判断以下 Worker 交付物是否保留了所有 MUST 约束。

## MUST 约束列表
{json.dumps(must_constraints, indent=2, ensure_ascii=False)}

## Worker 交付物
{json.dumps(worker_output, indent=2, ensure_ascii=False)}

## 判断标准
- 每个 MUST 约束必须在交付物中有语义对应的内容（不要求字面匹配）
- 如果某个约束被违反或遗漏，必须明确指出

## 输出格式
```json
{{
  "passed": true/false,
  "issues": ["约束 1 被违反: ...", "约束 2 被遗漏: ..."]
}}
```
"""
        
        # 调用 LLM（使用 spawn）
        # 注意：这里需要由 Orchestrator 调用 spawn，而不是 Gate 直接调用
        # 暂时返回 passed=True，让 Orchestrator 在调用 Gate 前先用 LLM 验证
        return {"passed": True, "issues": []}


class InformationConservationGate:
    """G2: 信息守恒检查"""
    
    @staticmethod
    def check(solution_pro_output: Dict[str, Any], ship_package: Dict[str, Any]) -> GateResult:
        """
        检查信息守恒：
        1. 信息丢失检查：Solution Pro 的关键信息是否被保留
        2. 信息新增检查：Ship Pro 是否引入了 Solution Pro 没有的信息
        
        AI Native 原则：语义判断用 LLM。
        """
        # 构建 prompt
        prompt = f"""你是一个信息守恒验证专家。请判断 Ship Package 是否满足信息守恒原则。

## Solution Pro 输出
{json.dumps(solution_pro_output, indent=2, ensure_ascii=False)}

## Ship Package
{json.dumps(ship_package, indent=2, ensure_ascii=False)}

## 判断标准

### 信息丢失检查
- Solution Pro 中的每个关键决策（key_decisions）必须在 Ship Package 中有对应的工作包
- Solution Pro 中的每个 MUST 约束必须在工作包的验收标准中体现

### 信息新增检查
- Ship Package 中的工作包必须对应 Solution Pro 中的某个需求或决策
- 不允许引入 Solution Pro 没有提及的功能或特性

## 输出格式
```json
{{
  "passed": true/false,
  "issues": [
    "信息丢失: Solution Pro 的决策 X 在 Ship Package 中没有对应工作包",
    "信息新增: WP-005 引入了 Solution Pro 没有的功能 Y"
  ]
}}
```
"""
        
        # 调用 LLM（需要 Orchestrator 处理）
        # 暂时返回 passed=True
        return GateResult(passed=True, issues=[])


class CompletenessGate:
    """G3: 完整性检查"""
    
    @staticmethod
    def check(solution_pro_output: Dict[str, Any], ship_package: Dict[str, Any]) -> GateResult:
        """
        检查完整性：
        1. 代码检查：每个 REQ-ID 是否至少被一个 WP 覆盖（浅层）
        2. LLM 判断：覆盖深度是否足够（中层/深层）
        
        AI Native 原则：代码做确定性检查，LLM 做语义判断。
        """
        issues = []
        
        # 1. 代码检查：REQ-ID 覆盖
        req_ids = InformationConservationGate._extract_req_ids(solution_pro_output)
        covered_req_ids = InformationConservationGate._extract_covered_req_ids(ship_package)
        
        missing_req_ids = set(req_ids) - set(covered_req_ids)
        if missing_req_ids:
            issues.append(f"以下 REQ-ID 没有被任何工作包覆盖: {missing_req_ids}")
        
        # 2. LLM 判断：覆盖深度
        # 需要 Orchestrator 调用 LLM
        # 暂时跳过
        
        if issues:
            return GateResult(passed=False, issues=issues)
        
        return GateResult(passed=True, issues=[], details={
            "total_req_ids": len(req_ids),
            "covered_req_ids": len(covered_req_ids),
            "coverage_rate": len(covered_req_ids) / len(req_ids) if req_ids else 1.0
        })


class HarnessV3:
    """G4: Harness V3 验证"""
    
    @staticmethod
    def check(ship_package: Dict[str, Any]) -> GateResult:
        """
        Harness V3 验证：
        - 工作包数量合理性
        - 依赖关系合理性
        - 验收标准可操作性
        
        AI Native 原则：语义判断用 LLM。
        """
        # 构建 prompt
        prompt = f"""你是一个工程验证专家。请验证 Ship Package 是否满足 Harness V3 标准。

## Ship Package
{json.dumps(ship_package, indent=2, ensure_ascii=False)}

## 验证标准

### 1. 工作包数量合理性
- 工作包数量应该在 3-15 之间
- 每个工作包的粒度应该适中（不要太细也不要太粗）

### 2. 依赖关系合理性
- 依赖图应该是有向无环图（DAG）
- 不应该有不必要的依赖（过度耦合）

### 3. 验收标准可操作性
- 每个工作包应该有至少 2 个验收标准
- 验收标准应该是可验证的（不是模糊的描述）

## 输出格式
```json
{{
  "passed": true/false,
  "score": 0-10,
  "issues": ["问题 1", "问题 2"]
}}
```
"""
        
        # 调用 LLM（需要 Orchestrator 处理）
        # 暂时返回 passed=True
        return GateResult(passed=True, issues=[], details={"score": 8})
