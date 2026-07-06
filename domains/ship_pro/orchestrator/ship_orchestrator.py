"""
Ship Pro - Orchestrator (纯工具库)

变更:
- 移除 REQ-ID 前置追踪(本末倒置,违反 AI Native 4.1)
- Worker prompt 增加质量优先级锚定
- 新增 prepare_completeness_judge_task()(后置 LLM Judge 语义验证)
- 状态转换宽松化(warn instead of raise on same-state transitions)
- ShipOrchestrator 降级为纯工具库(Agent 做调度决策)

核心流程:
Phase 1: Planner → PlannerGate 验证
Phase 2: Workers × N → MUST Judge → WorkerGate 验证
Phase 3: Consolidator → InfoConservationJudge + CompletenessJudge + HarnessJudge → 最终验证
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging
import re


def extract_json_from_completion(text: str) -> Optional[Dict[str, Any]]:
    """
    从子 Agent 完成事件的文本中提取 JSON。

    自动处理:
    - ```json ... ``` markdown 包裹
    - 前后多余文字
    - JSON 截断(尝试补全括号)

    Returns:
        解析后的 dict,或 None(如果提取失败)
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # 尝试 1: 直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试 2: 提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass

    # 尝试 3: 找第一个 { 到最后一个 } 的子串
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end + 1]
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            pass
    elif start != -1:
        # 没有 } 或 } 在 { 之前 - 可能是截断的 JSON
        json_str = text[start:]
    else:
        json_str = None

    # 尝试 4: 截断修复 - 尝试补全未闭合的括号
    if json_str:
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')

        # 移除尾部逗号
        fixed = re.sub(r',[\s]*$', '', json_str)
        # 补全括号
        if open_brackets > 0:
            fixed += ']' * open_brackets
        if open_braces > 0:
            fixed += '}' * open_braces

        try:
            result = json.loads(fixed)
            logger.warning("JSON 截断修复成功(结果可能不完整)")
            return result
        except (json.JSONDecodeError, TypeError):
            pass

    logger.warning(f"JSON 提取失败: text[:200] = {text[:200]}")
    return None


from ..contracts import (
    PlannerGate,
    WorkerGate,
    InformationConservationGate,
    CompletenessGate,
    HarnessV3,
    GateResult
)

logger = logging.getLogger(__name__)


class ShipOrchestrator:
    """
    Ship Pro Orchestrator(纯工具库)

    职责:
    1. 提供 prepare_* 方法(返回 spawn 参数)
    2. 提供 verify_* 方法(Gate 验证)
    3. 提供 prepare_*_judge_tasks 方法(LLM Judge 任务声明)
    4. 管理 Blackboard 状态(宽松模式)

    注意:
    - 本类不调用 sessions_spawn(那是 Dispatcher Agent 的职责)
    - 状态转换不再强制校验(由 Dispatcher Agent 自主决定)
    """

    def __init__(self, blackboard_path: Path):
        from .state_manager import StateManager

        self.blackboard_path = Path(blackboard_path)
        self.state_manager = StateManager(blackboard_path)
        self.state = self.state_manager.state

        logger.info

    # ========================================================================
    # Phase 1: Planner
    # ========================================================================

    def prepare_planner_spawn(self, solution_pro_output: Dict[str, Any]) -> Dict[str, Any]:
        """准备 Planner 的 spawn 参数。(统一使用 PipelinePlan schema)"""
        from ..pipeline_designer import PipelinePlan

        self.state_manager.update_stage("planner", "running")

        schema = PipelinePlan.model_json_schema()
        prompt = self._build_planner_prompt(solution_pro_output, schema)

        return {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_planner",
            "task": prompt,
            "thinking": "high",
        }

    def verify_planner_output(self, planner_output: Dict[str, Any],
                               solution_pro_output: Dict[str, Any] = None) -> GateResult:
        """验证 Planner 输出(PlannerGate 结构验证)。"""
        result = PlannerGate.check(planner_output)
        if not result.passed:
            logger.warning(f"PlannerGate failed: {result.issues}")
            return result

        # CompletenessGate 不再在 Planner 级别做 REQ-ID 字符串匹配
        # 改为后置 LLM Judge 语义验证(见 prepare_completeness_judge_task)

        self.state_manager.update_stage("planner", "completed")
        self.state_manager.write_stage("planner_output", planner_output)
        logger.info(f"Planner verified: {len(planner_output['workers'])} workers")
        return result

    # ========================================================================
    # Phase 2: Workers
    # ========================================================================

    def prepare_workers_spawn(self, planner_output: Dict[str, Any],
                               solution_pro_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """准备所有 Worker 的 spawn 参数。"""
        from ..contracts import get_worker_deliverable_schema

        self.state_manager.update_stage("build", "running")

        workers = planner_output["workers"]
        execution_layers = self._topological_sort(workers)

        spawn_params_list = []
        schema = get_worker_deliverable_schema()

        for layer_idx, layer_workers in enumerate(execution_layers):
            for worker_spec in layer_workers:
                prompt = self._build_worker_prompt(worker_spec, solution_pro_output, schema)
                spawn_params = {
                    "runtime": "subagent",
                    "mode": "run",
                    "label": f"ship_worker_{worker_spec['role']}",
                    "task": prompt,
                    "thinking": "high",
                }
                spawn_params_list.append(spawn_params)

        logger.info(f"Prepared {len(spawn_params_list)} workers in {len(execution_layers)} layers")
        return spawn_params_list

    def verify_worker_output(self, worker_spec: Dict[str, Any],
                               worker_output: Dict[str, Any],
                               judge_results: Dict[str, Any] = None) -> GateResult:
        """验证 Worker 输出(WorkerGate)。"""
        result = WorkerGate.check(worker_spec, worker_output, judge_results=judge_results)

        if result.passed:
            stage_name = f"worker_{worker_spec['role']}"
            self.state_manager.write_stage(stage_name, worker_output)
            logger.info(f"Worker {worker_spec['role']} verified")
        else:
            logger.warning(f"Worker {worker_spec['role']} failed: {result.issues}")

        return result

    def complete_build_phase(self):
        """标记 Build 阶段完成"""
        self.state_manager.update_stage("build", "completed")

    # ========================================================================
    # Phase 3: Consolidator
    # ========================================================================

    def prepare_consolidator_spawn(self, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        """准备 Consolidator 的 spawn 参数。"""
        from ..contracts import get_ship_package_schema

        self.state_manager.update_stage("shipper", "running")

        worker_outputs = {}
        for worker_spec in planner_output["workers"]:
            stage_name = f"worker_{worker_spec['role']}"
            worker_output = self.state_manager.read_stage(stage_name)
            if worker_output:
                worker_outputs[worker_spec["role"]] = worker_output

        schema = get_ship_package_schema()
        prompt = self._build_consolidator_prompt(planner_output, worker_outputs, schema)

        return {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_consolidator",
            "task": prompt,
            "thinking": "high",
        }


    def validate_ship_package_structure(self, ship_package: Dict[str, Any],
                                          planner_output: Dict[str, Any]) -> Dict[str, Any]:
        """验证 ShipPackage 结构完整性(契约铁律)。

        确保 Consolidator 输出了完整的 work_packages 数组,
        而不是只有统计摘要。

        Returns: {"valid": bool, "issues": [...], "expected_wp_count": int, "actual_wp_count": int}
        """
        issues = []
        wps = ship_package.get("work_packages", [])

        # 计算预期 WP 数量
        expected_count = 0
        for worker_spec in planner_output.get("workers", []):
            stage_name = f"worker_{worker_spec['role']}"
            worker_output = self.state_manager.read_stage(stage_name)
            if worker_output:
                expected_count += len(worker_output.get("work_packages", []))

        actual_count = len(wps)

        if actual_count == 0:
            issues.append(f"work_packages 数组为空(预期 {expected_count} 个 WP)")
        elif actual_count < expected_count * 0.8:
            issues.append(f"work_packages 数量不足:{actual_count}/{expected_count}(丢失 {expected_count - actual_count} 个)")

        # 检查统计摘要反模式
        if "total_work_packages" in ship_package and actual_count == 0:
            issues.append("统计摘要反模式:有 total_work_packages 字段但无实际 WP 内容")

        # 检查每个 WP 必需字段
        required_fields = ["id", "title", "description"]
        for i, wp in enumerate(wps):
            missing = [f for f in required_fields if not wp.get(f)]
            if missing:
                issues.append(f"WP #{i} ({wp.get('id', '?')}): 缺少必需字段 {missing}")

        valid = len(issues) == 0
        return {
            "valid": valid,
            "issues": issues,
            "expected_wp_count": expected_count,
            "actual_wp_count": actual_count,
        }

    def verify_ship_package(self, solution_pro_output: Dict[str, Any],
                               ship_package: Dict[str, Any],
                               planner_output: Dict[str, Any] = None,
                               judge_results: Dict[str, Any] = None) -> Dict[str, GateResult]:
        """验证 Ship Package(三个 Gate)。"""
        if planner_output is None:
            raise ValueError("planner_output 必须提供")

        results = {}
        results["information_conservation"] = InformationConservationGate.check(
            solution_pro_output, ship_package, judge_results=judge_results
        )
        # CompletenessGate 改为接受 judge_results(LLM Judge 语义验证)
        results["completeness"] = CompletenessGate.check(
            solution_pro_output, planner_output,
            judge_results=judge_results
        )
        results["harness_v3"] = HarnessV3.check(
            ship_package, judge_results=judge_results
        )

        all_passed = all(r.passed for r in results.values())
        if all_passed:
            self.state_manager.update_stage("shipper", "completed")
            self.state_manager.write_stage("ship_package", ship_package)
            logger.info("Ship Package verified")
        else:
            failed = [n for n, r in results.items() if not r.passed]
            logger.warning(f"Ship Package failed: {failed}")

        return results

    # ========================================================================
    # Judge Task Preparation
    # ========================================================================

    def prepare_gate_judge_tasks(self, solution_pro_output: Dict[str, Any],
                                   ship_package: Dict[str, Any],
                                   planner_output: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """准备 Gate 级 LLM Judge 任务(含 CompletenessJudge)。"""
        tasks = []

        # G1: 信息守恒 Judge
        tasks.append({
            "name": "info_conservation",
            "prompt": InformationConservationGate.build_judge_prompt(
                solution_pro_output, ship_package
            ),
            "expected_output": '{"passed": true/false, "issues": [...], "conservation_rate": 0.0-1.0}'
        })

        # G2: 新增 - 完整性语义 Judge(替代字符串匹配 CompletenessGate)
        if planner_output:
            tasks.append({
                "name": "completeness",
                "prompt": self._build_completeness_judge_prompt(
                    solution_pro_output, planner_output, ship_package
                ),
                "expected_output": '{"passed": true/false, "issues": [...], "coverage_rate": 0.0-1.0}'
            })

        # G3: Harness Judge
        tasks.append({
            "name": "harness_v3",
            "prompt": HarnessV3.build_judge_prompt(ship_package),
            "expected_output": '{"passed": true/false, "score": 0-10, "issues": [...]}'
        })

        logger.info(f"Prepared {len(tasks)} gate judge tasks ")
        return tasks

    def prepare_worker_judge_tasks(self, planner_output: Dict[str, Any],
                                     worker_outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """准备 Worker 级 MUST 约束 Judge 任务。"""
        from ..contracts import WorkerGate

        tasks = []
        for w_spec in planner_output.get("workers", []):
            role = w_spec["role"]
            must_constraints = w_spec.get("must_constraints", [])
            if must_constraints and role in worker_outputs:
                tasks.append({
                    "name": f"worker_must_{role}",
                    "prompt": WorkerGate.build_judge_prompt(w_spec, worker_outputs[role]),
                    "expected_output": '{"passed": true/false, "issues": [...]}'
                })

        logger.info(f"Prepared {len(tasks)} worker judge tasks")
        return tasks

    # ========================================================================
    # Completeness Judge Prompt Builder
    # ========================================================================

    def _build_completeness_judge_prompt(self, solution_pro_output: Dict[str, Any],
                                          planner_output: Dict[str, Any],
                                          ship_package: Dict[str, Any]) -> str:
        """
        构建完整性语义 Judge prompt。
        替代 CompletenessGate 字符串匹配。
        """
        req_ids = solution_pro_output.get('covered_req_ids', [])
        work_packages = ship_package.get('work_packages', [])

        return f"""你是 Ship Pro 的完整性验证 Judge。

## 任务

验证 ShipPackage 中的 Work Packages 是否语义覆盖了 Solution Pro 的所有需求。

## 注意
- 你做的是**语义验证**,不是字符串匹配
- 即使 WP 中没有显式出现 REQ-ID,只要 WP 的内容语义上解决了该需求,就算覆盖
- 关注需求的**实质**,不是标签

## 输入

### Solution Pro 的 covered_req_ids({len(req_ids)} 个)
{json.dumps(req_ids, indent=2, ensure_ascii=False)}

### Solution Pro 关键决策(key_decisions)
{json.dumps(solution_pro_output.get('key_decisions', []), indent=2, ensure_ascii=False)}

### Solution Pro 风险缓解(risk_mitigations)
{json.dumps(solution_pro_output.get('risk_mitigations', []), indent=2, ensure_ascii=False)}

### ShipPackage 的 Work Packages({len(work_packages)} 个)
{json.dumps(work_packages, indent=2, ensure_ascii=False)}

### Planner 的 Worker 分配
{json.dumps([{{"role": w["role"], "objective": w.get("module_purpose", w.get("task_description", ""))}} for w in planner_output.get("workers", [])], indent=2, ensure_ascii=False)}

## 评估维度

1. **需求覆盖**:每个 key_decision 是否被至少一个 WP 语义覆盖?
2. **风险覆盖**:每个 risk_mitigation 是否被至少一个 WP 的 acceptance_criteria 或 description 覆盖?
3. **架构覆盖**:Solution Pro 的 architecture 核心组件是否都有对应 WP?

## 输出格式

```json
{{
  "passed": true/false,
  "coverage_rate": 0.0-1.0,
  "issues": [
    {{
      "severity": "CRITICAL/MAJOR/MINOR",
      "dimension": "requirement/risk/architecture",
      "description": "具体问题描述"
    }}
  ],
  "covered_decisions": ["D1", "D2", ...],
  "uncovered_decisions": ["D5", ...],
  "covered_risks": ["R1", "R2", ...],
  "uncovered_risks": ["R3", ...]
}}
```

## 判断标准
- coverage_rate >= 0.8 且无 CRITICAL issue → passed = true
- 否则 → passed = false

请直接输出 JSON。"""

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _topological_sort(self, workers: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """拓扑排序(Kahn 算法),返回分层执行顺序。"""
        worker_map = {w["role"]: w for w in workers}
        depends_on_map = {w["role"]: w.get("depends_on", []) for w in workers}

        in_degree = {role: 0 for role in worker_map}
        for role, deps in depends_on_map.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[role] += 1

        layers = []
        remaining = set(worker_map.keys())

        while remaining:
            current_layer = [role for role in remaining if in_degree[role] == 0]

            if not current_layer:
                current_layer = [min(remaining, key=lambda r: in_degree[r])]
                logger.warning(f"Cycle detected, breaking at: {current_layer}")

            layers.append([worker_map[role] for role in current_layer])

            for role in current_layer:
                remaining.remove(role)
                for other_role, deps in depends_on_map.items():
                    if role in deps and other_role in remaining:
                        in_degree[other_role] -= 1

        return layers

    def _build_planner_prompt(self, solution_pro_output: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Planner prompt(领域无关版,含 domain_analysis 前置步骤)"""
        pending_req_ids = solution_pro_output.get('pending_req_ids', [])
        prompt = f"""你是 Ship Pro 的 Planner。

## 你在 Pipeline 中的位置

上游方案 → **【你(Planner)】** → Workers(并行) → Consolidator(组装) → 用户

你的上游是 Solution Pro(已完成方案设计),你的下游是多个并行 Workers(执行拆解后的任务),
最终由 Consolidator 组装交付物交给用户。

## 你的任务

分析 Solution Pro 的输出,规划如何将其拆解为高质量的、可独立完成的交付单元。

## 第一步:domain_analysis(必须先做)

在拆解之前,你必须先完成领域分析,回答四个问题:
1. **这是什么领域?** - 识别领域性质(软件/金融/内容/制造/...)
2. **最终用户是谁?** - 谁消费最终交付物?他们的角色和期望是什么?
3. **交付物应该是什么形态?** - 代码模块?分析报告?文章?设计方案?
4. **按什么维度拆分?** - 按模块/章节/分析维度/阶段/...

这四个问题决定了你的拆分策略。先想清楚最终用户需要什么形态的交付物,再决定怎么拆。

## 质量优先级

你优先保证拆解方案的**深度、可行性和逻辑合理性**:
- 每个 Worker 的角色定位必须清晰、不重叠
- 每个 Worker 的任务描述必须具体到可执行级别
- 依赖关系必须反映真实的逻辑依赖

## 跨域示例

### 示例 1:软件开发

**domain_analysis:**
- domain: "软件开发"
- end_users: ["开发者", "运维"]
- deliverable_form: "可部署的代码模块 + 测试"
- split_dimension: "按代码内聚性(模块)"
- key_constraints: ["API 兼容性", "性能指标 <200ms"]

**拆分结果(3 Workers):**
- Worker "core-engine": 核心引擎模块 - 数据结构、主循环、内部 API
- Worker "api-layer": API 层 - HTTP 接口、认证、中间件
- Worker "infra-config": 基础设施 - Dockerfile、CI 配置、部署脚本
- 依赖: api-layer → core-engine; infra-config → core-engine

### 示例 2:投资分析

**domain_analysis:**
- domain: "投资分析"
- end_users: ["投资决策者", "投委会"]
- deliverable_form: "完整投资分析报告"
- split_dimension: "按分析维度(行业/公司/财务/估值)"
- key_constraints: ["数据截止日 2026-06", "覆盖 3 年历史"]

**拆分结果(4 Workers):**
- Worker "industry-analyst": 行业分析 - 市场规模、竞争格局、趋势
- Worker "company-analyst": 公司分析 - 商业模式、护城河、管理层
- Worker "financial-analyst": 财务分析 - 三表分析、盈利质量、现金流
- Worker "valuation-analyst": 估值与风险 - DCF/可比估值、风险矩阵、投资建议
- 依赖: valuation-analyst → financial-analyst; valuation-analyst → company-analyst

### 示例 3:内容创作

**domain_analysis:**
- domain: "内容创作"
- end_users: ["读者", "编辑"]
- deliverable_form: "完整文章/书稿"
- split_dimension: "按章节/主题结构"
- key_constraints: ["总字数 8000-12000", "目标读者:技术背景"]

**拆分结果(3 Workers):**
- Worker "researcher": 素材研究 - 背景资料、数据收集、案例整理
- Worker "outline-writer": 大纲与核心章节 - 结构框架、核心论点、关键章节
- Worker "editor-writer": 润色与补充 - 过渡段落、案例填充、全文润色
- 依赖: outline-writer → researcher; editor-writer → outline-writer

## Solution Pro 输出

```json
{json.dumps(solution_pro_output, indent=2, ensure_ascii=False)}
```

## 约束笼子

### 任务边界
- 你只做"拆解+交付",不做"设计+决策"
- Solution Pro 没说的不补充,说了的不修改

### 角色边界
- 你只规划"怎么拆",不讨论"该不该拆"
- 不评价 Solution Pro 方案优劣

### 输出边界
- 输出必须符合 PipelinePlan Schema(统一协议,替代原 PlannerOutput)
- 额外建议标记为 optional_suggestion

## 输出格式(JSON Schema)

PipelinePlan 中必须包含 `domain_analysis` 字段(放在 workers 之前):

```json
{{
  "domain_analysis": {{
    "domain": "领域名称",
    "end_users": ["用户角色1", "用户角色2"],
    "deliverable_form": "交付物形态描述",
    "split_dimension": "拆分维度说明",
    "key_constraints": ["来自上游的硬约束1", "硬约束2"]
  }},
  "workers": [...],
  "execution_order": [...],
  "rationale": "..."
}}
```

完整 Schema:

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 铁律

1. Worker 数量:2 <= N <= 8
2. 依赖图必须是无环 DAG
3. 每个 Worker 必须有约束引用(must_constraints)
4. 角色名称自由命名(不需要从允许列表中选择)
5. **WP ID 前缀**:每个 Worker 必须有 wp_id_prefix(2-6 个字母,如 CORE、LOOP、QG)。
   该 Worker 生成的所有 WP ID 必须以此为前缀(如 CORE-001、LOOP-002)。
6. **透传 pending_req_ids**:Solution Pro 中标记为 deferred 的 REQ-IDs 直接透传到 pending_req_ids 字段。
   不需要为这些 REQ-ID 分配 Worker。

   延迟 REQ-IDs:
   {chr(10).join(f'   - {rid}' for rid in pending_req_ids) if pending_req_ids else '   (无延迟 REQ-ID)'}

## 输出控制(重要)

如果你的输出超过 8000 字符,请先写入文件再确认:
1. 用 exec 写入: `cat > /tmp/pipeline_plan.json << 'JSONEOF'\n...\nJSONEOF`
2. 然后只输出: `{{"status": "written", "path": "/tmp/pipeline_plan.json"}}`

如果输出不超过 8000 字符,直接输出 JSON 即可。

## 输出

请直接输出 JSON,不要包含其他文字。
"""
        return prompt

    def _build_worker_prompt(self, worker_spec: Dict[str, Any], solution_pro_output: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Worker prompt(质量优先级锚定,无 REQ-ID 追踪,精简 context)"""
        wp_id_prefix = worker_spec.get('wp_id_prefix', 'WP')

        # 精简 Solution Pro context - 只保留 Worker 需要的字段
        relevant_context = {
            k: v for k, v in solution_pro_output.items()
            if k not in ('implementation_plan', 'success_metrics')
        }

        prompt = f"""你是 Ship Pro 的 Worker: {worker_spec['role']}

## 架构位置

Planner → **【你（Worker）】** → Consolidator → 用户

你是流水线中的执行环节。Planner 已经把任务分配给你，你的产出会被 Consolidator 组装后交付给最终用户。

## 质量优先级（最高优先级）

你优先保证产出的**深度、可行性和合理性**，而非机械覆盖需求数量。

### 每个 WP 的硬性最小要求（代码层会验证，不满足即拒绝）

| 字段 | 最小要求 | 示例 |
|------|---------|------|
| description | ≥100 字符 | 说清楚做什么、为什么这么做、边界条件、与其他模块的接口 |
| acceptance_criteria | ≥2 条 | 每条必须是可验证的具体标准（"系统能运行"不算，"API 响应时间 <200ms"算） |
| deliverables | ≥1 项 | 明确列出交付物（如"分析文档""数据表格""代码模块""调研报告"） |

**禁止行为**：
- ❌ 不要输出一句话的 description（如"实现 XX 功能"）
- ❌ 不要跳过 acceptance_criteria（没有 AC 的 WP 无法验收）
- ❌ 不要跳过 deliverables（没有交付物的 WP 无法执行）

## 产出模式（从你的 role 和 deliverables 推断）

根据 Planner 分配给你的 role 和 deliverables，判断你的产出应该是哪种模式：

- **代码文件**（如 .py/.js/.ts/.go/.java/.vue/.css）→ 产出 WP 描述（做什么、验收标准），不生成代码实现
- **内容文件**（如 .md/.pdf/.xlsx/.docx/.txt）→ 产出实际内容（段落、数据、分析），可被 Consolidator 直接组装
- **混合类型** → 代码部分写描述，内容部分写实际内容

### 领域自适应参考

| 领域 | 你的产出应该是 | 示例 |
|------|-------------|------|
| 软件开发 | WP 描述（不写代码） | "实现用户认证模块，包含 JWT..." |
| 投资分析 | 实际分析内容 | "新能源汽车行业 2024 年增速 35%..." |
| 内容创作 | 实际文章/章节内容 | "## 引言：LLM 正在改变客服行业..." |
| 市场调研 | 实际调研发现 | "目标市场规模 500 亿，CR3 集中度 45%..." |

## 你的任务

{worker_spec.get('module_purpose', worker_spec.get('task_description', '（未指定）'))}

## Solution Pro 参考信息（精简）

```json
{json.dumps(relevant_context, indent=2, ensure_ascii=False)}
```

## 约束笼子

### 任务边界
- 你只做"拆解+交付"，不做"设计+决策"
- Solution Pro 没说的不补充，说了的不修改

### 角色边界
- 你的角色是 {worker_spec['role']}
- 只生成交付物，不讨论方案优劣
- 不修改其他 Worker 的产出

### 输出边界（契约笼子 — 违反即拒绝）
- 输出必须符合 WorkerDeliverable Schema
- 额外建议标记为 optional_suggestion
- 根据产出模式决定：代码类交付物只写 WP 描述，内容类交付物写实际内容
- ❌ 不要运行测试
- ✅ 只输出符合 Schema 的 JSON

## 最终用户视角自检

完成产出后自检：
- 最终用户能直接使用我的产出吗？
- 我的产出与其他 Worker 的产出能无缝组装吗？
- 我的产出覆盖了 Planner 要求的所有要点吗？

## WP ID 前缀规则（契约笼子 — 违反即拒绝）

你的 WP ID 前缀是: `{wp_id_prefix}`

所有工作包的 ID 必须以此为前缀，格式: `{wp_id_prefix}-NNN`
例如: `{wp_id_prefix}-001`, `{wp_id_prefix}-002`, `{wp_id_prefix}-003`

❌ 不允许使用通用编号（如 WP-001、WP-002）
❌ 不允许使用其他前缀
✅ 必须使用 `{wp_id_prefix}` 作为前缀

## MUST 约束（从 Solution Pro 继承，不可违反）

{json.dumps(worker_spec.get('must_constraints', []), indent=2, ensure_ascii=False)}

## 输出格式（JSON Schema）

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 输出

请直接输出 JSON，不要包含其他文字。
"""
        return prompt

    def _build_consolidator_prompt(self, planner_output: Dict[str, Any], worker_outputs: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """构建 Consolidator prompt"""
        # 计算预期 WP 总数(用于信息守恒验证)
        expected_wp_count = sum(
            len(wo.get("work_packages", []))
            for wo in worker_outputs.values()
        )

        prompt = f"""你是 Ship Pro 的 Consolidator。

## 你的任务

将 {len(worker_outputs)} 个 Worker 的 **全部 work_packages** 合并为一个完整的 Ship Package。

## ⚠️ 信息守恒铁律(最高优先级)

1. **必须合并所有 WP**:遍历每个 Worker 输出的 `work_packages` 数组,将所有 WP 原样合并到 ShipPackage 的 `work_packages` 字段中。
2. **保留完整字段**:每个 WP 必须保留全部字段(id, title, description, acceptance_criteria, dependencies, estimated_effort, deliverables)。不得删减任何字段。
3. **不得摘要化**:不得用统计数字(如 `total_work_packages: 40`)替代实际 WP 内容。
4. **预期数量**:你应该合并 **{expected_wp_count} 个 Work Package** 到输出中。如果数量不匹配,说明你丢失了 WP。

## Planner 的整合策略

{planner_output.get('rationale', planner_output.get('integration_strategy', '(未指定)'))}

## Worker 产出

{json.dumps(worker_outputs, indent=2, ensure_ascii=False)}

## 约束笼子

### 任务边界
- 你只做"整合",不做"设计+决策"
- 不增加新 WP 或新需求
- 不删减已有产出

### 角色边界
- 你只汇总已有产出
- 冲突时选择与 Solution Pro 更一致的方案

### 输出边界
- 输出必须符合 ShipPackage Schema
- `work_packages` 数组必须包含所有 Worker 的全部 WP(共 {expected_wp_count} 个)
- optional_suggestion 物理隔离到 metadata.optional_suggestions

### 延迟需求透传
- Planner 输出中有 pending_req_ids
- 你必须在 metadata.pending_req_ids 中透传这个列表

## ❌ 禁止行为
- ❌ 不要只输出统计摘要(如 `total_work_packages: 40`)而省略实际 WP 内容
- ❌ 不要用 `workers: [{{role, wp_count}}]` 摘要替代完整 WP 数组
- ❌ 不要截断任何 WP 的 description 或 acceptance_criteria

## 输出格式(JSON Schema)

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

## 输出

请直接输出 JSON,不要包含其他文字。确保 `work_packages` 数组包含全部 {expected_wp_count} 个 WP。
"""
        return prompt

    # ========================================================================
    # 三层验证架构(契约笼子)
    # ========================================================================

    def validate_all_worker_outputs_l1(self, blackboard_path: str = None) -> Dict[str, Any]:
        """Layer 1: 确定性硬拦截

        读取所有 worker_*.json 文件 → Pydantic Schema + 内容深度验证

        契约笼子:
        - 无 worker 文件 → raise ValueError
        - Schema 失败 → raise ValueError
        - AC<2 / desc<100 / deliverables<1 → raise ValueError
        - 不使用 judge_results(那是 Layer 2 的职责)
        """
        from ..contracts.worker_deliverable import WorkerDeliverable, WorkPackage

        bp = Path(blackboard_path) if blackboard_path else self.blackboard_path
        stages_dir = bp / "stages"
        worker_files = sorted(stages_dir.glob("worker_*.json"))

        # 契约笼子:必须有 worker 输出
        if not worker_files:
            raise ValueError(f"契约笼子: 未找到任何 worker 输出文件 ({stages_dir}/worker_*.json)")

        results = {"all_passed": True, "workers": {}, "failures": []}

        for f in worker_files:
            worker_name = f.stem.replace("worker_", "")
            try:
                data = json.loads(f.read_text(encoding="utf-8"))

                # 格式兼容:Worker 可能输出 JSON 数组或 WorkerDeliverable 对象
                if isinstance(data, list):
                    wps = data
                elif isinstance(data, dict) and "work_packages" in data:
                    WorkerDeliverable.model_validate(data)
                    wps = data.get("work_packages", [])
                else:
                    raise ValueError(f"未知输出格式: type={type(data).__name__}")

                # 契约笼子:字段名自动映射(Workers 可能用 wp_id/effort_hours)
                for wp in wps:
                    # wp_id → id(双向别名)
                    if "wp_id" in wp and "id" not in wp:
                        wp["id"] = wp["wp_id"]
                    # effort_hours 已是 Schema 原生字段(int),无需转换
                    # 旧字段 estimated_effort (str) → 转为 effort_hours (int)
                    if "estimated_effort" in wp and "effort_hours" not in wp:
                        try:
                            wp["effort_hours"] = int(str(wp["estimated_effort"]).replace("h", "").strip())
                        except (ValueError, TypeError):
                            pass

                # Layer 1a: Pydantic Schema(每个 WP 单独验证)
                for wp in wps:
                    WorkPackage.model_validate(wp)

                # Layer 1b: 内容深度
                wp_issues = []
                for wp in wps:
                    wp_id = wp.get("id", "?")
                    desc = wp.get("description", "")
                    acs = wp.get("acceptance_criteria", [])
                    dels = wp.get("deliverables", [])

                    if len(desc) < 100:
                        wp_issues.append(f"{wp_id}: description {len(desc)} chars < 100")
                    if len(acs) < 2:
                        wp_issues.append(f"{wp_id}: AC {len(acs)} 条 < 2")
                    if len(dels) < 1:
                        wp_issues.append(f"{wp_id}: deliverables 为空")

                if wp_issues:
                    results["all_passed"] = False
                    results["failures"].append({"worker": worker_name, "issues": wp_issues})
                else:
                    results["workers"][worker_name] = {
                        "wp_count": len(wps),
                        "status": "L1_PASS"
                    }

            except Exception as e:
                results["all_passed"] = False
                results["failures"].append({"worker": worker_name, "error": str(e)})

        # 契约笼子:L1 失败直接 raise
        if not results["all_passed"]:
            failure_summary = "; ".join(
                f"{f['worker']}: {f.get('issues', f.get('error', '?'))}"
                for f in results["failures"]
            )
            raise ValueError(f"契约笼子 L1 验证失败: {failure_summary}")

        return results

    def prepare_judge_spawn_all(self, blackboard_path: str = None) -> List[Dict[str, Any]]:
        """Layer 2: 为所有 Worker 准备 Judge spawn params

        读取 planner_output + worker outputs → 构建 MUST 约束 Judge prompts

        契约笼子:
        - 无 planner_output → raise ValueError
        - Worker 有 must_constraints 但无对应 Judge → 不 spawn(由 merge 检测)
        """
        bp = Path(blackboard_path) if blackboard_path else self.blackboard_path
        stages_dir = bp / "stages"

        # 读取 planner output
        planner_path = stages_dir / "pipeline_plan.json"
        if not planner_path.exists():
            raise ValueError(f"契约笼子: pipeline_plan.json 不存在 ({planner_path})")

        planner_output = json.loads(planner_path.read_text(encoding="utf-8"))
        workers = planner_output.get("workers", [])

        judge_params = []
        for worker_spec in workers:
            role = worker_spec.get("role", "unknown")
            must_constraints = worker_spec.get("must_constraints", [])

            if not must_constraints:
                continue  # 无 MUST 约束,不需要 Judge

            # 读取 worker output
            worker_path = stages_dir / f"worker_{role}.json"
            if not worker_path.exists():
                continue  # Worker 未产出,跳过(merge 会检测)

            worker_output = json.loads(worker_path.read_text(encoding="utf-8"))

            # 构建 Judge prompt
            judge_prompt = WorkerGate.build_judge_prompt(worker_spec, worker_output)

            judge_params.append({
                "runtime": "subagent",
                "mode": "run",
                "label": f"worker_must_{role}",
                "task": judge_prompt,
                "thinking": "medium",
            })

        logger.info(f"Prepared {len(judge_params)} Judge spawn params")
        return judge_params

    def merge_gate_results(self, blackboard_path: str = None,
                           l1_results: Dict[str, Any] = None,
                           judge_verdicts: Dict[str, Any] = None) -> Dict[str, Any]:
        """Layer 3: 综合决策

        合并 L1 确定性结果 + L2 Judge 语义结果 → PASS / FAIL

        契约笼子:
        - L1 未通过 → 不可能进入 L3(已在 L1 raise)
        - L2 Judge 缺失 must_constraints 的 Worker → raise ValueError
        """
        bp = Path(blackboard_path) if blackboard_path else self.blackboard_path
        stages_dir = bp / "stages"

        # 读取 planner output 获取 must_constraints 信息
        planner_path = stages_dir / "pipeline_plan.json"
        planner_output = json.loads(planner_path.read_text(encoding="utf-8")) if planner_path.exists() else {}
        workers = planner_output.get("workers", [])

        # 检查 Judge 覆盖
        judge_verdicts = judge_verdicts or {}
        missing_judges = []
        l2_issues = []

        for worker_spec in workers:
            role = worker_spec.get("role", "unknown")
            must_constraints = worker_spec.get("must_constraints", [])

            if must_constraints:
                task_name = f"worker_must_{role}"
                if task_name not in judge_verdicts:
                    missing_judges.append(role)
                else:
                    verdict = judge_verdicts[task_name]
                    if not verdict.get("passed", False):
                        l2_issues.extend(verdict.get("issues", [f"{role}: MUST 约束未通过"]))

        # 契约笼子:Judge 缺失
        if missing_judges:
            raise ValueError(
                f"契约笼子 L3: 以下 Worker 有 MUST 约束但缺少 Judge 结果: {missing_judges}"
            )

        # 综合决策
        passed = (l1_results or {}).get("all_passed", False) and len(l2_issues) == 0

        result = {
            "passed": passed,
            "l1_passed": (l1_results or {}).get("all_passed", False),
            "l2_issues": l2_issues,
            "missing_judges": missing_judges,
            "worker_count": len(workers),
        }

        logger.info(f"Gate merge: L1={'PASS' if result['l1_passed'] else 'FAIL'}, "
                   f"L2 issues={len(l2_issues)}, Final={'PASS' if passed else 'FAIL'}")
        return result

    def prepare_consolidator_spawn_v8(self, blackboard_path: str = None) -> Dict[str, Any]:
        """Consolidator spawn(6 步法)

        读取所有 worker outputs → 构建 6 步法 Consolidator prompt
        """
        bp = Path(blackboard_path) if blackboard_path else self.blackboard_path
        stages_dir = bp / "stages"

        # 收集 worker 输出文件路径
        worker_files = sorted(stages_dir.glob("worker_*.json"))
        if not worker_files:
            raise ValueError(f"契约笼子: 无 worker 输出文件")

        worker_file_paths = ", ".join(str(f) for f in worker_files)
        solution_pro_input_path = str(bp / "solution_pro_input.json")
        output_path = str(stages_dir / "ship_package.json")

        # 读取 consolidator prompt 模板
        prompt_template_path = Path(__file__).parent.parent / "prompts" / "consolidator.md"
        if prompt_template_path.exists():
            prompt = prompt_template_path.read_text(encoding="utf-8")
            prompt = prompt.replace("{stages_dir}", str(stages_dir))
            prompt = prompt.replace("{solution_pro_input_path}", solution_pro_input_path)
            prompt = prompt.replace("{output_path}", output_path)
            prompt = prompt.replace("{worker_file_paths}", worker_file_paths)
            prompt = prompt.replace
        else:
            # fallback: 内嵌 prompt
            prompt = f"""你是 ShipPackage 装配师。

## 输入
- Worker 输出文件: {worker_file_paths}
- Solution Pro 输入: {solution_pro_input_path}

## 6 步法
1. 收集: read 所有 worker_*.json
2. 去重: 同 REQ-ID 多 WP → 保留更详细的
3. 冲突检测: 约束矛盾
4. 依赖图: 跨 Worker WP 依赖
5. 统计: WP 数/effort/覆盖率
6. 组装: write 到 {output_path}

## 禁止
- ❌ 修改 WP 内容
- ❌ 添加新 WP
- ❌ 产出实际代码"""

        return {
            "runtime": "subagent",
            "mode": "run",
            "label": "ship_consolidator_v8",
            "task": prompt,
            "thinking": "high",
        }

    def validate_ship_package_v8(self, blackboard_path: str = None) -> Dict[str, Any]:
        """ShipPackage L1 验证

        契约笼子:
        - ship_package.json 不存在 → raise ValueError
        - work_packages 为空 → raise ValueError
        - WP 缺少必需字段 → raise ValueError
        """
        bp = Path(blackboard_path) if blackboard_path else self.blackboard_path
        stages_dir = bp / "stages"

        sp_path = stages_dir / "ship_package.json"
        if not sp_path.exists():
            raise ValueError(f"契约笼子: ship_package.json 不存在 ({sp_path})")

        ship_package = json.loads(sp_path.read_text(encoding="utf-8"))
        wps = ship_package.get("work_packages", [])

        if not wps:
            raise ValueError("契约笼子: ship_package.json 中 work_packages 为空")

        # 契约笼子:字段名自动映射 + 必需字段检查
        required_fields = ["id", "title", "description", "acceptance_criteria", "deliverables"]
        for wp in wps:
            # wp_id → id 自动映射(Consolidator 可能输出 wp_id)
            if "wp_id" in wp and "id" not in wp:
                wp["id"] = wp["wp_id"]
            missing = [f for f in required_fields if not wp.get(f)]
            if missing:
                raise ValueError(
                    f"契约笼子: WP {wp.get('id', wp.get('wp_id', '?'))} 缺少字段 {missing}"
                )

        # 契约笼子:Semantic Anchors 守恒检查
        # 读取 solution_pro_input 获取上游 anchors
        sol_input_path = bp / "solution_pro_input.json"
        anchor_check = {"checked": False, "upstream_count": 0, "preserved_count": 0, "uncovered": []}

        if sol_input_path.exists():
            sol_input = json.loads(sol_input_path.read_text(encoding="utf-8"))
            upstream_anchors = sol_input.get("semantic_anchors", [])
            upstream_names = [a.get("name", "?") for a in upstream_anchors if isinstance(a, dict)]
            anchor_check["upstream_count"] = len(upstream_names)

            if upstream_names:
                anchor_check["checked"] = True
                # 检查 ship_package 是否保留了 semantic_anchors
                ship_anchors = ship_package.get("semantic_anchors", [])
                ship_anchor_names = [a.get("name", "?") for a in ship_anchors if isinstance(a, dict)]
                anchor_check["preserved_count"] = len(ship_anchor_names)

                # 检查哪些 anchor 被 WP 的 anchored_to 引用了
                wp_referenced = set()
                for wp in wps:
                    for a in wp.get("anchored_to", []):
                        wp_referenced.add(a)

                anchor_check["wp_referenced_count"] = len(wp_referenced)
                anchor_check["uncovered"] = sorted(set(upstream_names) - wp_referenced)

                # 契约笼子:如果上游有 anchors 但 ship_package 完全没有保留 → raise
                if not ship_anchors:
                    logger.warning(
                        f"契约笼子 WARNING: ship_package.json 缺少 semantic_anchors 字段。"
                        f"上游有 {len(upstream_names)} 个 anchors,但 Consolidator 未透传。"
                    )

                # 契约笼子:如果超过 50% 的 anchors 未被任何 WP 引用 → raise
                if len(upstream_names) > 0 and len(anchor_check["uncovered"]) > len(upstream_names) * 0.5:
                    raise ValueError(
                        f"契约笼子: Semantic Anchors 守恒失败 - "
                        f"{len(anchor_check['uncovered'])}/{len(upstream_names)} 个 anchors 未被任何 WP 引用: "
                        f"{anchor_check['uncovered']}"
                    )

        return {
            "valid": True,
            "wp_count": len(wps),
            "total_effort": sum(wp.get("effort_hours", 0) for wp in wps),
            "anchor_check": anchor_check,
        }


def build_ship_pro_input(
    frozen_spec_path: str,
    supplemental_path: str = None,
    output_path: str = None
) -> Dict[str, Any]:
    """自动构建 Ship Pro 输入 - 信息守恒提取

    从 Solution Pro 的 frozen_spec.json 提取完整 requirements/guardrails,
    合并人工补充的 key_decisions/architecture/risk_mitigations。

    解决信息流断裂:frozen_spec (28KB) → solution_pro_input (8KB) 的 71% 丢失。

    Args:
        frozen_spec_path: Solution Pro 的 frozen_spec.json 路径
        supplemental_path: 可选的人工补充字段文件(key_decisions, architecture 等)
        output_path: 可选的输出路径(保存合并后的 JSON)

    Returns:
        合并后的 Ship Pro 输入字典
    """
    from pathlib import Path

    # 1. 加载 frozen_spec(Solution Pro 完整输出)
    frozen_path = Path(frozen_spec_path)
    if not frozen_path.exists():
        raise FileNotFoundError(f"frozen_spec not found: {frozen_spec_path}")

    with open(frozen_path) as f:
        frozen = json.load(f)

    merged = {}

    # 2. 保留 frozen_spec 全部字段(requirements, guardrails, requirement_groups 等)
    for k, v in frozen.items():
        merged[k] = v

    # 3. 合并人工补充字段(如果有)
    if supplemental_path:
        supp_path = Path(supplemental_path)
        if supp_path.exists():
            with open(supp_path) as f:
                supplemental = json.load(f)

            supplement_keys = [
                'key_decisions', 'must_constraints', 'architecture',
                'risk_mitigations', 'implementation_plan', 'constraints_satisfied',
                'solution_name', 'covered_req_ids', 'pending_req_ids'
            ]
            for k in supplement_keys:
                if k in supplemental and k not in merged:
                    merged[k] = supplemental[k]

    # 4. 验证信息守恒
    req_count = len(merged.get('requirements', []))
    has_guardrails = 'guardrails' in merged and merged['guardrails']
    has_key_decisions = 'key_decisions' in merged and len(merged.get('key_decisions', [])) > 0

    if req_count == 0:
        raise ValueError(f"信息守恒违规: requirements 为空 (frozen_spec 应包含 REQ 列表)")

    logging.info(
        f"build_ship_pro_input: {req_count} REQs, "
        f"guardrails={'✅' if has_guardrails else '❌'}, "
        f"key_decisions={'✅' if has_key_decisions else '❌'}, "
        f"total={len(json.dumps(merged, ensure_ascii=False))} chars"
    )

    # 5. 保存(如果指定了输出路径)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved merged Ship Pro input to: {output_path}")

    return merged
