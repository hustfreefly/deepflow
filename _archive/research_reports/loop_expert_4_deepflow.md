# Expert 4: DeepFlow 多域编排架构师 — LoOP × DeepFlow 深度整合设计

> 版本: 1.0 | 日期: 2026-06-24 | 角色: 多域编排架构师

---

## 一、核心问题：为什么 DeepFlow 需要 LoOP？

DeepFlow 当前的 `loop_runner.py` 本质是一个**文件匹配状态机**——通过检查预期文件是否存在来判断 phase 完成。这有三个致命缺陷：

1. **无语义理解**：文件存在 ≠ 质量达标（一个空 JSON 也能通过）
2. **无跨域能力**：4 个域各自独立，没有"需求→交付"的端到端编排
3. **恢复靠 LLM 续接**：resume-prompt 依赖 LLM 理解上下文继续执行，成功率 ~33%

LoOP 的 6 组件（Automation + Worktrees + Skills + Connectors + Sub-agents + Memory）恰好补齐这三个缺口。

---

## 二、跨域 Meta-Loop：四域端到端编排

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    META-LOOP ORCHESTRATOR                        │
│  (OpenClaw sessions_spawn + Python control plane)               │
│                                                                  │
│  ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────┐ │
│  │ Spec Pro │──▶│ Solution Pro │──▶│ Ship Pro │──▶│Research   │ │
│  │ (需求域) │   │ (方案域)     │   │ (交付域) │   │Pro (研究) │ │
│  └────┬─────┘   └──────┬───────┘   └────┬─────┘   └────┬─────┘ │
│       │                │                │               │        │
│       └────────────────┴────────────────┴───────────────┘        │
│                        │                                         │
│                  ┌─────▼──────┐                                  │
│                  │  CONTRACT  │                                  │
│                  │  BUS       │                                  │
│                  └────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Contract Bus：跨域契约总线

核心设计：每个域完成后产出一个**标准化契约**，下一个域从契约读取输入，而非直接依赖文件。

```python
# contract_bus.py — 跨域契约总线
class ContractBus:
    """跨域契约总线：域间通信的唯一通道"""
    
    def __init__(self, session_id: str):
        self.state_path = Path(f"runs/{session_id}/meta_state.json")
        self.contracts = {}
    
    def publish(self, domain: str, artifact: dict, quality_score: float):
        """域完成后发布契约"""
        self.contracts[domain] = {
            "artifact": artifact,
            "quality_score": quality_score,
            "published_at": datetime.now().isoformat(),
            "status": "published"
        }
        self._save()
    
    def subscribe(self, domain: str) -> dict | None:
        """域启动时订阅上游契约"""
        # Spec Pro → living_spec.json
        # Solution Pro → final_result.json  
        # Ship Pro → ship_package.json
        # Research Pro → research_report.md
        return self.contracts.get(domain)
    
    def can_trigger(self, downstream: str) -> bool:
        """检查下游域的触发条件是否满足"""
        dependencies = {
            "solution_pro": ["spec_pro"],
            "ship_pro": ["solution_pro"],
            "research_pro": ["spec_pro"],  # 研究可以并行
        }
        deps = dependencies.get(downstream, [])
        return all(
            self.contracts.get(d, {}).get("status") == "published"
            and self.contracts[d]["quality_score"] >= self._min_quality(d)
            for d in deps
        )
```

### 2.3 回环机制：Ship Pro → Spec Pro

当 Ship Pro Reviewer 发现需求不清时，不是简单"失败"，而是触发**定向回环**：

```python
# 回环决策器
class BackloopDecider:
    """判断是否需要回环到上游域"""
    
    def evaluate(self, ship_review: dict, spec: dict) -> BackloopDecision:
        issues = ship_review.get("issues", [])
        
        # 分类问题
        spec_issues = [i for i in issues if i.get("root_cause") == "spec_ambiguity"]
        design_issues = [i for i in issues if i.get("root_cause") == "design_flaw"]
        
        if len(spec_issues) >= 2:
            # 需求不清 → 回环 Spec Pro，附带具体问题
            return BackloopDecision(
                action="backloop",
                target_domain="spec_pro",
                context={
                    "ambiguous_requirements": spec_issues,
                    "ship_review_feedback": ship_review,
                    "partial_work": ship_review.get("completed_components", [])
                },
                priority="high"
            )
        
        if len(design_issues) >= 2:
            # 设计缺陷 → 回环 Solution Pro
            return BackloopDecision(
                action="backloop",
                target_domain="solution_pro",
                context={"design_feedback": design_issues}
            )
        
        return BackloopDecision(action="proceed")
```

---

## 三、域内 Loop 引擎升级

### 3.1 Phase State Machine

将 `loop_runner.py` 的文件匹配升级为**显式状态机**：

```
┌─────────┐    ┌─────────┐    ┌───────────────┐    ┌──────┐
│ PENDING │───▶│ RUNNING │───▶│ GATE_CHECKING │───▶│ DONE │
└─────────┘    └────┬────┘    └───────┬───────┘    └──────┘
                    │                 │
                    │          ┌──────▼──────┐
                    │          │   FAILED    │
                    │          └──────┬──────┘
                    │                 │ (retry < max)
                    │          ┌──────▼──────┐
                    └──────────│  RETRYING   │
                               └─────────────┘
```

```python
# loop_engine.py — 升级版 Loop 引擎
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class PhaseState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    GATE_CHECKING = "gate_checking"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"  # DAG 中不需要的分支

@dataclass
class PhaseCheckpoint:
    """每个 phase 的持久化 checkpoint"""
    phase_id: int
    phase_name: str
    state: PhaseState
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    artifacts: list[str] = field(default_factory=list)
    gate_result: Optional[dict] = None
    retry_count: int = 0
    token_usage: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "phase_name": self.phase_name,
            "state": self.state.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "artifacts": self.artifacts,
            "gate_result": self.gate_result,
            "retry_count": self.retry_count,
            "token_usage": self.token_usage,
            "error_message": self.error_message,
        }
```

### 3.2 DAG 支持：并行 Phase 声明

Solution Pro 的 Phase 3 (reviewers) 和 Phase 4 (research) 可以并行：

```python
# DAG 定义（从当前 loop_runner.py 的 phases 列表升级）
DAG_DEFINITIONS = {
    "solution_pro": {
        "nodes": [
            ("data_collection", [], "serial"),        # Phase 1: 无依赖
            ("planning", ["data_collection"], "serial"),  # Phase 2: 依赖 Phase 1
            ("reviewers", ["planning"], "parallel"),     # Phase 3: 依赖 Phase 2
            ("research", ["planning"], "parallel"),      # Phase 4: 依赖 Phase 2（可与 Phase 3 并行！）
            ("consolidator", ["reviewers", "research"], "serial"),  # Phase 5: 等待 3+4
            ("audit", ["consolidator"], "serial"),
            ("fix", ["audit"], "serial"),
            ("fixer_expert", ["fix"], "serial"),
            ("harness_final", ["fixer_expert"], "serial"),
            ("summarizer", ["harness_final"], "serial"),
        ],
        # 关键优化：Phase 3 和 Phase 4 并行 → 节省 ~30% 时间
    }
}
```

### 3.3 Checkpoint 持久化

不再依赖"文件存在 = 完成"，而是写入结构化 checkpoint：

```python
def write_checkpoint(session_id: str, checkpoint: PhaseCheckpoint):
    """每个 phase 完成后写入 checkpoint"""
    ckpt_dir = Path(f"runs/{session_id}/checkpoints")
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    ckpt_file = ckpt_dir / f"phase_{checkpoint.phase_id}_{checkpoint.phase_name}.json"
    with open(ckpt_file, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
    
    # 同时更新全局进度
    progress_file = Path(f"runs/{session_id}/loop_progress.json")
    progress = load_progress(progress_file)
    progress["phases"][checkpoint.phase_id] = checkpoint.to_dict()
    progress["last_updated"] = datetime.now().isoformat()
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)
```

---

## 四、Domain-Specific Goal Checkers

每个域的"完成"定义不同，用 Goal Checker 模式统一：

```python
# goal_checkers.py — 域专属目标检查器
from abc import ABC, abstractmethod

class GoalChecker(ABC):
    """域目标检查器基类"""
    
    @abstractmethod
    def check(self, artifacts: dict) -> GoalResult:
        """检查域目标是否达成"""
        pass
    
    @abstractmethod
    def score(self, artifacts: dict) -> float:
        """返回 0-1 的质量分数"""
        pass

class SpecProGoalChecker(GoalChecker):
    """Spec Pro 目标检查器"""
    
    def check(self, artifacts: dict) -> GoalResult:
        spec = artifacts.get("living_spec.json")
        harness = artifacts.get("harness_result.json")
        
        if not spec or not harness:
            return GoalResult(passed=False, reason="缺少核心产出物")
        
        # 检查 harness 评分
        harness_score = harness.get("overall_score", 0)
        if harness_score < 0.8:
            return GoalResult(passed=False, reason=f"Harness 评分 {harness_score} < 0.8")
        
        # 检查需求覆盖率
        coverage = spec.get("requirement_coverage", 0)
        if coverage < 0.9:
            return GoalResult(passed=False, reason=f"需求覆盖率 {coverage} < 0.9")
        
        return GoalResult(passed=True, score=harness_score)
    
    def score(self, artifacts: dict) -> float:
        harness = artifacts.get("harness_result.json", {})
        return harness.get("overall_score", 0)

class SolutionProGoalChecker(GoalChecker):
    """Solution Pro 目标检查器"""
    
    def check(self, artifacts: dict) -> GoalResult:
        result = artifacts.get("final_result.json")
        if not result:
            return GoalResult(passed=False, reason="final_result.json 不存在")
        
        quality_score = result.get("quality_score", 0)
        if quality_score < 0.85:
            return GoalResult(passed=False, reason=f"质量分 {quality_score} < 0.85")
        
        # 检查所有 REQ-ID 都被覆盖
        covered = set(result.get("covered_req_ids", []))
        required = set(result.get("required_req_ids", []))
        if not required.issubset(covered):
            missing = required - covered
            return GoalResult(passed=False, reason=f"未覆盖需求: {missing}")
        
        return GoalResult(passed=True, score=quality_score)

class ShipProGoalChecker(GoalChecker):
    """Ship Pro 目标检查器"""
    
    GATES = [
        "structure_valid",      # 包结构正确
        "tests_pass",           # 测试通过
        "docs_complete",        # 文档完整
        "security_scan_clean",  # 安全扫描干净
        "performance_baseline", # 性能基线达标
    ]
    
    def check(self, artifacts: dict) -> GoalResult:
        package = artifacts.get("ship_package.json")
        if not package:
            return GoalResult(passed=False, reason="ship_package.json 不存在")
        
        gate_results = package.get("gate_results", {})
        failed_gates = [g for g in self.GATES if not gate_results.get(g, False)]
        
        if failed_gates:
            return GoalResult(passed=False, reason=f"Gate 未通过: {failed_gates}")
        
        return GoalResult(passed=True, score=1.0)

class ResearchProGoalChecker(GoalChecker):
    """Research Pro 目标检查器"""
    
    def check(self, artifacts: dict) -> GoalResult:
        report = artifacts.get("research_report.md")
        if not report:
            return GoalResult(passed=False, reason="research_report.md 不存在")
        
        # 字数检查
        word_count = len(report.get("content", ""))
        if word_count < 5000:
            return GoalResult(passed=False, reason=f"报告字数 {word_count} < 5000")
        
        # 引用源检查
        sources = report.get("sources", [])
        if len(sources) < 10:
            return GoalResult(passed=False, reason=f"引用源 {len(sources)} < 10")
        
        return GoalResult(passed=True, score=min(word_count / 10000, 1.0))
```

---

## 五、Loop 触发模式

### 5.1 触发矩阵

| 触发条件 | 触发方式 | Loop 范围 | 示例 |
|---------|---------|----------|------|
| 用户显式请求 | 自然语言意图识别 | 全 4 域 Meta-Loop | "帮我做一个完整方案" |
| Cron 定时巡检 | OpenClaw heartbeat | 单域 Loop | 每日检查方案是否需要更新 |
| 质量门失败 | Gate Checker 触发 | 回环 Loop | Ship Pro Reviewer 发现需求不清 |
| 代码审查 | CI/CD 钩子 | Ship Pro Fix Loop | PR 质量不达标 |
| 外部事件 | Webhook / 飞书消息 | Research Pro Loop | 竞品发布新功能 |

### 5.2 意图识别 → Meta-Loop

```python
# trigger_router.py — 触发路由器
class TriggerRouter:
    """根据输入决定触发哪个 Loop"""
    
    PATTERNS = {
        "full_pipeline": [
            "帮我做一个完整的解决方案",
            "从零开始做一个项目",
            "完整需求到交付",
        ],
        "solution_only": [
            "帮我设计方案",
            "做一个技术方案",
        ],
        "research_only": [
            "调研一下",
            "深入研究",
            "帮我研究",
        ],
        "ship_only": [
            "打包交付",
            "生成 ship package",
        ],
    }
    
    def route(self, user_input: str) -> TriggerDecision:
        # 用 LLM 做语义匹配（AI Native 原则）
        intent = self.classify_intent(user_input)
        
        if intent == "full_pipeline":
            return TriggerDecision(
                loop_type="meta_loop",
                domains=["spec_pro", "solution_pro", "ship_pro"],
                auto_chain=True,
                timeout_seconds=1800,  # 30 分钟
            )
        elif intent == "solution_only":
            return TriggerDecision(
                loop_type="domain_loop",
                domains=["solution_pro"],
                auto_chain=False,
                timeout_seconds=900,
            )
        # ...
```

---

## 六、DeepFlow Doctor 整合

### 6.1 带病模式检测

```python
# doctor/loop_diagnoser.py — Loop 诊断器
class LoopDiagnoser:
    """诊断 Loop 运行异常"""
    
    # T1: 工具错误 — Worker 调用失败
    T1_SIGNALS = [
        "spawn_failed",
        "timeout_exceeded",
        "api_rate_limit",
    ]
    
    # T2: 门控失效 — Gate 该拦没拦
    T2_SIGNALS = [
        "gate_passed_but_quality_low",   # Gate 通过但质量低
        "harness_score_dropped",         # Harness 分数下降
        "missing_req_ids",               # 需求 ID 丢失
    ]
    
    # T3: 静默降级 — LLM 跳过步骤但不报错
    T3_SIGNALS = [
        "phase_skipped_without_checkpoint",  # Phase 被跳过
        "artifact_empty_but_marked_done",    # 产出物为空但标记完成
        "retry_count_high",                  # 重试次数异常高
    ]
    
    # T4: 范围失控 — 做了不该做的事
    T4_SIGNALS = [
        "extra_phases_executed",         # 执行了额外 phase
        "scope_creep_detected",          # 范围蔓延
        "unauthorized_file_modification", # 未授权文件修改
    ]
    
    def diagnose(self, session_id: str) -> DiagnosisReport:
        checkpoints = self.load_checkpoints(session_id)
        signals = []
        
        for ckpt in checkpoints:
            # T1 检测
            if ckpt.error_message and "spawn" in ckpt.error_message:
                signals.append(Signal("T1", "spawn_failed", ckpt))
            
            # T2 检测
            if ckpt.gate_result and ckpt.gate_result.get("score", 0) < 0.7:
                signals.append(Signal("T2", "gate_passed_but_quality_low", ckpt))
            
            # T3 检测
            if ckpt.state == PhaseState.DONE and not ckpt.artifacts:
                signals.append(Signal("T3", "artifact_empty_but_marked_done", ckpt))
            
            # T4 检测
            expected_phases = self.get_expected_phases(session_id)
            if ckpt.phase_id not in expected_phases:
                signals.append(Signal("T4", "extra_phases_executed", ckpt))
        
        # 浪费量化
        total_tokens = sum(c.token_usage for c in checkpoints)
        wasted_tokens = sum(
            c.token_usage for c in checkpoints 
            if c.state in (PhaseState.FAILED, PhaseState.RETRYING)
        )
        
        return DiagnosisReport(
            signals=signals,
            token_waste=wasted_tokens,
            token_waste_pct=wasted_tokens / total_tokens if total_tokens else 0,
            time_waste=self._calc_time_waste(checkpoints),
            severity=self._calc_severity(signals),
        )
```

---

## 七、创新架构设计

### 7.1 Loop DNA：运行基因图谱

每个 Loop run 生成一个完整的"基因图谱"，记录从 prompt → worker → 结果 → gate 的全链路：

```python
# loop_dna.py — Loop DNA 记录器
@dataclass
class LoopDNA:
    """一次 Loop run 的完整基因图谱"""
    run_id: str
    domain: str
    started_at: str
    completed_at: str
    
    # 基因序列：每个 phase 是一个"碱基"
    sequence: list[PhaseGene]
    
    # 表型：最终产出
    phenotype: {
        "artifacts": list[str],
        "quality_score": float,
        "total_tokens": int,
        "total_time_seconds": float,
    }
    
    # 可遗传变异：哪些 prompt 修改带来了改进
    mutations: list[Mutation]

@dataclass  
class PhaseGene:
    """单个 phase 的基因"""
    phase_id: int
    phase_name: str
    prompt_hash: str          # prompt 的 SHA256
    worker_model: str         # 使用的模型
    temperature: float
    input_tokens: int
    output_tokens: int
    gate_score: float
    gate_passed: bool
    retry_count: int
    duration_seconds: float

# 用途：
# 1. 回溯：哪个 phase 引入了质量问题？查 DNA
# 2. 复制：成功的 run 可以精确复现
# 3. 进化：对比高分 run 和低分 run 的 DNA 差异
```

### 7.2 Evolutionary Loop：自动优化 Phase Prompts

利用 Loop DNA 数据，自动优化 worker prompts：

```python
# evolutionary_loop.py — 进化式 Loop
class EvolutionaryLoop:
    """利用历史 DNA 数据自动优化 prompts"""
    
    def analyze(self, dna_history: list[LoopDNA]) -> list[PromptSuggestion]:
        """分析历史 run，生成优化建议"""
        
        # 分组：按 phase_name 聚合
        by_phase = defaultdict(list)
        for dna in dna_history:
            for gene in dna.sequence:
                by_phase[gene.phase_name].append(gene)
        
        suggestions = []
        
        for phase_name, genes in by_phase.items():
            # 高分组（gate_score > 0.9）vs 低分组
            high_score = [g for g in genes if g.gate_score > 0.9]
            low_score = [g for g in genes if g.gate_score < 0.7]
            
            if not high_score or not low_score:
                continue
            
            # 提取差异特征
            high_avg_tokens = mean(g.output_tokens for g in high_score)
            low_avg_tokens = mean(g.output_tokens for g in low_score)
            
            high_avg_retries = mean(g.retry_count for g in high_score)
            low_avg_retries = mean(g.retry_count for g in low_score)
            
            # 生成优化建议
            if high_avg_tokens > low_avg_tokens * 1.5:
                suggestions.append(PromptSuggestion(
                    phase=phase_name,
                    suggestion=f"高分 run 平均输出 {high_avg_tokens:.0f} tokens，"
                              f"低分 run 只有 {low_avg_tokens:.0f}。"
                              f"建议在 prompt 中增加更详细的输出格式要求。",
                    confidence=0.7,
                ))
            
            if low_avg_retries > high_avg_retries + 1:
                suggestions.append(PromptSuggestion(
                    phase=phase_name,
                    suggestion=f"低分 run 平均重试 {low_avg_retries:.1f} 次，"
                              f"高分 run 只有 {high_avg_retries:.1f} 次。"
                              f"建议简化 prompt 或增加示例。",
                    confidence=0.8,
                ))
        
        return suggestions
    
    def auto_evolve(self, suggestion: PromptSuggestion):
        """自动应用优化（需要人工确认）"""
        # 1. 读取当前 prompt
        # 2. 用 LLM 根据 suggestion 修改 prompt
        # 3. 生成新版本（不覆盖原版）
        # 4. 下次 run 使用新版本
        # 5. 对比 DNA，验证是否改进
        pass
```

### 7.3 架构全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DEEPFLOW + LoOP 全景                            │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   META-LOOP LAYER                            │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │  │ Spec Pro │─▶│Solution  │─▶│ Ship Pro │─▶│Research  │    │    │
│  │  │          │  │   Pro    │  │          │  │   Pro    │    │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │    │
│  │       │              │              │              │          │    │
│  │       └──────────────┴──────────────┴──────────────┘          │    │
│  │                         │                                     │    │
│  │                   ┌─────▼──────┐                              │    │
│  │                   │Contract Bus│                              │    │
│  │                   └────────────┘                              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                      │
│  ┌───────────────────────────▼─────────────────────────────────┐   │
│  │                   LOOP ENGINE LAYER                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │   │
│  │  │Phase State   │  │Checkpoint    │  │DAG Scheduler     │   │   │
│  │  │Machine       │  │Manager       │  │(并行 Phase)      │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌───────────────────────────▼─────────────────────────────────┐   │
│  │                   INTELLIGENCE LAYER                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │   │
│  │  │Goal Checkers │  │Loop DNA      │  │Evolutionary Loop │   │   │
│  │  │(域专属)      │  │Recorder      │  │(自动优化)        │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌───────────────────────────▼─────────────────────────────────┐   │
│  │                   DIAGNOSIS LAYER                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │   │
│  │  │DeepFlow      │  │Waste         │  │Backloop          │   │   │
│  │  │Doctor        │  │Quantifier    │  │Decider           │   │   │
│  │  │(T1-T4检测)   │  │(token/时间)  │  │(回环决策)        │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌───────────────────────────▼─────────────────────────────────┐   │
│  │                   OPENCLAW INTEGRATION LAYER                  │   │
│  │  sessions_spawn │ sessions_yield │ cron │ memory │ message    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 八、实施路线图

| 阶段 | 内容 | 周期 | 优先级 |
|------|------|------|--------|
| P0 | Phase State Machine + Checkpoint 持久化 | 1 周 | 🔴 最高 |
| P1 | Contract Bus + 跨域触发 | 1 周 | 🔴 最高 |
| P2 | Domain-Specific Goal Checkers | 3 天 | 🟡 高 |
| P3 | DAG Scheduler（Phase 3/4 并行） | 3 天 | 🟡 高 |
| P4 | Loop DNA 记录器 | 2 天 | 🟢 中 |
| P5 | DeepFlow Doctor 整合（T1-T4） | 1 周 | 🟢 中 |
| P6 | Evolutionary Loop（自动优化） | 2 周 | 🔵 低 |
| P7 | Backloop Decider（回环机制） | 1 周 | 🔵 低 |

---

## 九、关键结论

1. **Meta-Loop 的核心是 Contract Bus**：域间通信必须通过标准化契约，不能直接依赖文件。这让跨域编排成为可能。

2. **Phase State Machine 是升级的基石**：从"文件存在=完成"升级到显式状态机 + checkpoint，让恢复不再依赖 LLM 续接。

3. **Goal Checker 必须域专属**：每个域的"完成"定义不同，统一接口 + 域专属实现是唯一可扩展的方案。

4. **Loop DNA 是进化的前提**：没有完整的运行记录，就无法做自动优化。DNA 记录器是 P6 Evolutionary Loop 的基础。

5. **回环机制要谨慎**：Ship Pro → Spec Pro 的回环虽然理论上完美，但实际中可能导致无限循环。必须设置最大回环次数（建议 ≤ 2）。

---

*Expert 4 研讨完成。本文档从多域编排角度设计了 LoOP × DeepFlow 的深度整合方案，涵盖跨域 Meta-Loop、域内 Loop 引擎升级、Goal Checker、触发模式、Doctor 整合、以及两个创新架构（Loop DNA + Evolutionary Loop）。*
