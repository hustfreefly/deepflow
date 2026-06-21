# DeepFlow Pipeline Integrity Report

> **Generated**: 2026-06-22 01:54 GMT+8  
> **Scope**: Solution Pro 10-Stage Pipeline · Ship Pro V3.1 Pipeline · Spec Pro → Solution Pro Interface  
> **Method**: Static code analysis of prompts, task builders, blackboard registry, gate functions, and pipeline orchestrator

---

## Executive Summary

| Pipeline | Integrity Score | Verdict |
|----------|----------------|---------|
| Solution Pro 10-Stage | **82/100** | 🟡 Functional with structural gaps |
| Ship Pro V3.1 | **88/100** | 🟢 Well-structured, minor naming debt |
| Spec Pro → Solution Pro Interface | **75/100** | 🟡 Working but fragile fallback path |

**Overall**: Both pipelines are operationally functional. The primary risks are in cross-pipeline data contracts and orphaned code paths that could cause silent degradation.

---

## Part 1: Solution Pro 10-Stage Pipeline

### 1.1 Stage Map & Data Flow

```
Stage 1: data_collection  →  data/collection.json
Stage 2: planning         →  stages/planning.json + data/structured_requirements.json
Stage 3: reviewers (×3)   →  stages/reviewer_{technical,business,risk}.json
Stage 4: research (×3)    →  stages/research_expert_{1,2,3}.json
Stage 5: consolidator     →  stages/consolidator.json
Stage 6: audit            →  stages/audit.json
Stage 7: fix              →  stages/fix.json
Stage 8: fixer_expert     →  stages/fixer_expert.json
Stage 9: harness_final    →  stages/harness_final.json + requirements_traceability_matrix.json
Stage 10: summarizer      →  stages/summarizer.json + final_result.json + final_solution.md
```

### 1.2 Stage-by-Stage Analysis

| Stage | Input Sources | Output Target | REQ-ID Tracking | Score |
|-------|--------------|---------------|-----------------|-------|
| 1. data_collection | topic, constraints, living_spec | data/collection.json | ✅ covered_req_ids | 9/10 |
| 2. planning | collection.json, living_spec | stages/planning.json + data/structured_requirements.json | ✅ covered_req_ids + structured REQ generation | 9/10 |
| 3. reviewers (×3) | planning.json, frozen_spec.json, living_spec | stages/reviewer_{type}.json | ✅ covered_req_ids + requirement_evidence | 8/10 |
| 4. research (×3) | planning.json, frozen_spec.json, living_spec | stages/research_expert_{n}.json | ✅ covered_req_ids + requirement_evidence | 8/10 |
| 5. consolidator | research_expert_{1,2,3}.json, planning.json, frozen_spec.json | stages/consolidator.json | ✅ covered_req_ids | 7/10 |
| 6. audit | consolidator.json, design.json?, frozen_spec.json | stages/audit.json | ✅ covered_req_ids | 7/10 |
| 7. fix | audit.json, frozen_spec.json | stages/fix.json | ✅ covered_req_ids | 8/10 |
| 8. fixer_expert | audit.json, fix.json, frozen_spec.json | stages/fixer_expert.json | ✅ covered_req_ids | 8/10 |
| 9. harness_final | consolidator.json, all prior stages, frozen_spec.json | stages/harness_final.json + requirements_traceability_matrix.json | ✅ Full RTM generation | 9/10 |
| 10. summarizer | all stages, frozen_spec.json, living_spec | stages/summarizer.json + final_result.json | ✅ covered_req_ids + coverage annotation | 8/10 |

### 1.3 REQ-ID Traceability Chain

```
frozen_spec.json (权威源, generated at init)
    ↓ injected into every worker prompt via REQ_TRACEABILITY_INSTRUCTION
    ↓ each worker must output covered_req_ids[] + requirement_evidence[]
    ↓
Stage 9: harness_final generates requirements_traceability_matrix.json
    ↓ maps every REQ-XXX → covered|partial|missing with evidence
    ↓
Stage 10: summarizer annotates final report with coverage per REQ-ID
```

**Verdict**: REQ-ID chain is **end-to-end designed** but depends on LLM compliance with no code-level enforcement of the `requirement_evidence` field during pipeline execution (only validated in `validate_stage_output` which is called at gate time, not enforced as a hard barrier).

### 1.4 Issues Found

| ID | Severity | Issue | Location |
|----|----------|-------|----------|
| SP-01 | 🟡 Medium | **`design` stage is orphaned** — registered in STAGE_PATH_REGISTRY and `build_designer_task()` exists, but not included in PIPELINE_STAGES tuple. The 10-stage pipeline skips design entirely. | blackboard.py, PIPELINE_STAGES |
| SP-02 | 🟡 Medium | **`deliver` task builder exists but is unused** — `build_deliver_task()` is defined but not called in the 10-stage flow. Summarizer handles final output instead. | task_builder.py |
| SP-03 | 🟠 Low | **Harness decision enum mismatch** — `harness_scorer.py` defines 4 decisions (PASS/WARNING/CRITICAL_WARNING/BLOCK_RECOMMENDATION), but `task_builder.py` STAGE_OUTPUT_SCHEMA allows 5 (adds PASS_WITH_CONDITIONS). Workers may output PASS_WITH_CONDITIONS which harness_scorer can't produce. | harness_scorer.py vs task_builder.py |
| SP-04 | 🟠 Low | **Consolidator receives inline JSON, not file paths** — `build_consolidator_task()` serializes `research_outputs` as inline JSON in the prompt, while also listing file paths. Potential confusion for LLM about which to use. | task_builder.py |
| SP-05 | 🟠 Low | **`build_fixer_task()` marked @deprecated but still importable** — Dead code that could be accidentally called. | task_builder.py |
| SP-06 | 🟡 Medium | **Frozen spec generated as side-effect, not a pipeline stage** — `write_frozen_spec()` is called in `__init__` (line 264 of orchestrator_agent.py), outside the 10-stage flow. If init fails silently, frozen_spec.json won't exist but pipeline will proceed. | orchestrator_agent.py |
| SP-07 | 🟠 Low | **Lightweight Spec Agent (Step 0) has no code path in run_solution_pro** — SKILL.md describes it but `run_solution_pro()` only accepts `living_spec` as a kwarg. The LLM-based inference is the main agent's responsibility, not enforced. | SKILL.md Step 0 |

### 1.5 Solution Pro Score Breakdown

| Dimension | Score | Notes |
|-----------|-------|-------|
| Input clarity | 9/10 | Each stage has explicit input sources via file paths |
| Output clarity | 8/10 | STAGE_PATH_REGISTRY is single source of truth; orphaned stages cause minor confusion |
| Inter-stage coherence | 8/10 | Data flows logically; consolidator reads research outputs; harness reads all |
| REQ-ID tracing | 8/10 | Designed end-to-end; enforcement is LLM-dependent |
| Error handling | 7/10 | Fallback mechanisms exist but frozen_spec absence not detected mid-pipeline |

**Total: 82/100**

---

## Part 2: Ship Pro V3.1 Pipeline

### 2.1 Agent Chain & Data Flow

```
Input (Format A/B/C/D)
    ↓
[Architect] → architect_output.json (blueprint)
    ↓ gate_architect (modules≠∅, deps acyclic, reqs≠∅)
[Decomposer] → decomposer_output.json (work_packages)
    ↓ gate_decomposer (WPs≠∅, 100% module coverage, deps acyclic)
[Specifier] → specifier_output.json (wp_specs with AC, budget, complexity)
    ↓ gate_specifier (budget filled, AC≥2, schema names correct)
[Reviewer] → reviewer_output.json (semantic review, no code gate)
    ↓ auto-pass (no code gate)
[Packager] → packager_output.json (ship_package.json)
    ↓ gate_packager (schema compliant, AC text not count, deps acyclic)
Output: ship_package.json
```

### 2.2 Quality Gate V2 Analysis

| Gate | Critical Checks | Major Checks | Retry Limit | Verdict |
|------|----------------|--------------|-------------|---------|
| gate_architect | modules_non_empty, dependencies_acyclic, requirements_non_empty | requirements_mapped, project_type_exists | 2 | ✅ Well-defined |
| gate_decomposer | wps_non_empty, module_coverage_100, dependencies_acyclic | all_wps_have_source_modules, all_wps_have_rationale | 2 | ✅ Well-defined |
| gate_specifier | budget_filled, complexity_filled, outputs_non_empty, ac_non_empty(≥2), schema_field_names | requirements_non_empty, ac_score_70 | 2 | ✅ Most rigorous |
| gate_reviewer | *(none — auto-pass)* | *(none)* | 5 | 🟡 No code gate |
| gate_packager | schema_compliant, ac_text_not_count, dependency_graph_acyclic | all_wps_present, summary_exists | 2 | ✅ Well-defined |

### 2.3 Input Format Coverage

| Format | Detection Logic | Architect Handling | Coverage |
|--------|----------------|-------------------|----------|
| Format A | `final_solution` key exists | Extracts from `final_solution.detailed_solution.architecture.components[]` | ✅ Full |
| Format B | `project` + `architecture` keys | Extracts from `architecture.components[]` / `.core_components[]` / `.layers[]` | ✅ Full |
| Format B-tech | Architecture as key-value map | Extracts from map values as tech domains | ✅ Full |
| Format C | `pipeline_summary` or `executive_summary` | Minimal extraction, low confidence | ✅ Full |
| Format D | Fallback | `[数据不足]` markers, low confidence | ✅ Full |

### 2.4 Issues Found

| ID | Severity | Issue | Location |
|----|----------|-------|----------|
| SHP-01 | 🟠 Low | **V2 prompt files coexist with V3 prompts** — `ship_pre_scanner.md`, `ship_reviewer.md`, `ship_fixer.md`, `ship_harness.md` are V2 artifacts. V3.1 uses `architect.md`, `decomposer.md`, etc. Dead files cause confusion. | prompts/ directory |
| SHP-02 | 🟡 Medium | **Reviewer has no code gate** — `GATE_CONFIG["reviewer"]["gate_fn"] = None` means reviewer always auto-passes. Semantic review quality depends entirely on LLM. If reviewer produces garbage, packager inherits it. | run_pipeline.py GATE_CONFIG |
| SHP-03 | 🟠 Low | **Reviewer retry limit is 5 but others are 2** — Asymmetric retry limits without documentation of rationale. Reviewer could consume disproportionate time. | run_pipeline.py GATE_CONFIG |
| SHP-04 | 🟠 Low | **File naming convention inconsistency** — Prompts specify `{agent}_output.json` but gates CLI in `gates.py` main() uses `architect-output.json` (hyphen) for architect while run_pipeline uses `architect_output.json` (underscore). | gates.py CLI vs run_pipeline.py |
| SHP-05 | 🟢 Info | **Packager prompt references `blueprint.json`** but actual file is `architect_output.json`. The run_pipeline.py injects correct paths, but the prompt template uses conceptual names. | prompts/packager.md |
| SHP-06 | 🟠 Low | **No validation that specifier reads both blueprint AND wp_structure** — Specifier depends on both architect and decomposer outputs, but gate_specifier only checks specifier's own output structure, not whether it consumed both inputs. | gates.py gate_specifier |

### 2.5 Ship Pro Score Breakdown

| Dimension | Score | Notes |
|-----------|-------|-------|
| 5-Agent chain completeness | 9/10 | All 5 agents defined with clear roles and prompts |
| Quality Gate coverage | 8/10 | 4/5 agents have code gates; reviewer is auto-pass |
| Input format coverage | 10/10 | Format A/B/C/D all handled with explicit extraction rules |
| Retry/upgrade mechanism | 9/10 | Clear escalation: retry → conditional → skip |
| Data contract consistency | 8/10 | Minor naming debt between V2/V3 artifacts |

**Total: 88/100**

---

## Part 3: Spec Pro → Solution Pro Interface

### 3.1 Data Flow Path

```
Spec Pro Output: living_spec (dict)
    │
    ├── confirmed: { objective, pain_points, users, capabilities, quality_attributes, ... }
    ├── inferred: [{ dimension, content, confidence, status }]
    ├── solution_pro_hints: { focus_areas, layer2_hints, anti_patterns }
    └── guardrails: { always_do, never_do }
    │
    ▼
spec_context.py: build_worker_context_section(living_spec, worker_role)
    │
    ├── Extracts user_directives from confirmed
    ├── Extracts inferred_pending (status=="pending")
    ├── Extracts solution_pro_hints (structured)
    └── Formats for prompt injection per worker_role
    │
    ▼
frozen_spec.py: build_frozen_spec(topic, constraints, living_spec)
    │
    ├── Generates REQ-001..N from confirmed capabilities/quality_attributes/constraints
    ├── Groups into 5 categories: Core, Functional, NonFunctional, Boundaries, Context
    └── Writes data/frozen_spec.json (REQ-ID权威源)
    │
    ▼
task_builder.py: injects living_spec context into every worker prompt
    │
    ├── Global understanding (executive_summary) injection
    ├── Per-worker requirement group assignment
    ├── REQ_TRACEABILITY_INSTRUCTION appended to all non-exempt workers
    └── spec_context.build_worker_context_section() appended
```

### 3.2 Interface Contract Verification

| Contract Point | Status | Notes |
|---------------|--------|-------|
| living_spec → frozen_spec generation | ✅ Working | `write_frozen_spec()` called at init, generates REQ-IDs from confirmed |
| frozen_spec → worker prompt injection | ✅ Working | `REQ_TRACEABILITY_INSTRUCTION` appended to all non-exempt workers |
| living_spec → worker context injection | ✅ Working | `build_worker_context_section()` called for every build_*_task() |
| confirmed.capabilities → REQ-ID mapping | ✅ Working | always_do→P0, should_do→P1, never_do→P0(prohibition) |
| quality_attributes → REQ-ID mapping | ✅ Working | Mapped to NonFunctional group |
| guardrails → worker prompts | ✅ Working | Injected as "禁止做的事" in fixer/auditor/researcher prompts |
| inferred_pending → worker awareness | 🟡 Partial | Only injected for planner/researcher/consolidator; reviewer/auditor/fixer don't see pending inferences |
| Lightweight Spec Agent fallback | 🟡 Fragile | Described in SKILL.md but no code enforcement; depends on main agent LLM |

### 3.3 Issues Found

| ID | Severity | Issue | Location |
|----|----------|-------|----------|
| IF-01 | 🟡 Medium | **No validation that frozen_spec.json exists before pipeline starts** — If `write_frozen_spec()` fails silently, workers will read a non-existent file. The `REQ_TRACEABILITY_INSTRUCTION` says "read frozen_spec.json" but doesn't specify what to do if it's missing. | orchestrator_agent.py, task_builder.py |
| IF-02 | 🟡 Medium | **Lightweight Spec Agent has no implementation in run_solution_pro** — SKILL.md Step 0 describes `infer_living_spec()` but `run_solution_pro()` only accepts `living_spec` as kwarg. If main agent doesn't provide it, frozen_spec degrades to topic-only with minimal REQ-IDs. | SKILL.md vs __init__.py |
| IF-03 | 🟠 Low | **inferred_pending not propagated to reviewer/auditor/fixer** — These workers may make decisions affecting pending inferences without knowing they exist. | spec_context.py build_worker_context_section() |
| IF-04 | 🟡 Medium | **Living spec context injection is duplicated** — Both `living_spec_context` (manually built in each build_*_task) AND `build_worker_context_section()` are appended. This means workers receive global understanding twice (once manual, once via spec_context). | task_builder.py |
| IF-05 | 🟠 Low | **No schema validation on living_spec input** — `run_solution_pro(living_spec=...)` accepts any dict. Malformed living_spec could cause silent degradation of frozen_spec quality. | __init__.py |

### 3.4 Interface Score Breakdown

| Dimension | Score | Notes |
|-----------|-------|-------|
| Data path completeness | 8/10 | Main path works; fallback path fragile |
| Schema contract | 7/10 | No input validation on living_spec |
| Context propagation | 7/10 | Duplicate injection; not all workers see inferred_pending |
| Failure detection | 6/10 | No validation that frozen_spec exists before workers read it |
| Backward compatibility | 9/10 | Pipeline works without living_spec (degrades gracefully) |

**Total: 75/100**

---

## Part 4: Consolidated Findings

### Critical (Must Fix)

_None found — both pipelines are operationally functional._

### High Priority

| ID | Pipeline | Issue | Recommendation |
|----|----------|-------|----------------|
| SP-06 | Solution Pro | Frozen spec generated as side-effect, not validated mid-pipeline | Add pre-flight check: verify frozen_spec.json exists before Stage 1 spawn |
| IF-02 | Interface | Lightweight Spec Agent has no code implementation | Either implement in `run_solution_pro()` or remove from SKILL.md to avoid confusion |
| SHP-02 | Ship Pro | Reviewer has no code gate | Add at minimum a structural check (e.g., review_report has findings array, verdict field) |

### Medium Priority

| ID | Pipeline | Issue | Recommendation |
|----|----------|-------|----------------|
| SP-01 | Solution Pro | `design` stage orphaned | Remove from STAGE_PATH_REGISTRY or add to PIPELINE_STAGES |
| SP-03 | Solution Pro | Harness decision enum mismatch | Unify to 5-value enum across harness_scorer.py and task_builder.py |
| IF-04 | Interface | Duplicate living_spec context injection | Consolidate to single injection via `build_worker_context_section()` |
| IF-01 | Interface | No frozen_spec.json existence validation | Add to orchestrator pre-flight or Stage 1 worker prompt fallback |

### Low Priority

| ID | Pipeline | Issue | Recommendation |
|----|----------|-------|----------------|
| SP-02 | Solution Pro | `build_deliver_task()` unused | Remove or document as deprecated |
| SP-05 | Solution Pro | `build_fixer_task()` deprecated but importable | Add deprecation warning or move to _deprecated.py |
| SHP-01 | Ship Pro | V2 prompt files coexist with V3 | Move V2 prompts to `prompts/v2_archive/` |
| SHP-04 | Ship Pro | File naming inconsistency in gates CLI | Standardize on underscore convention |
| IF-03 | Interface | inferred_pending not in reviewer/auditor | Evaluate if these workers need pending inference awareness |

---

## Part 5: Architecture Observations

### Strengths

1. **Blackboard pattern is well-implemented** — STAGE_PATH_REGISTRY as single source of truth prevents path drift
2. **REQ-ID traceability is comprehensive** — End-to-end from frozen_spec through RTM to final report
3. **Ship Pro gate functions are rigorous** — Critical/Major/Minor tiered checks with clear thresholds
4. **3-level degradation strategy** in Ship Pro V2 (retry → simplify → fallback) is resilient
5. **Living spec context injection** per worker role is well-designed (global understanding + per-role groups)

### Risks

1. **LLM-dependent quality gates** — REQ-ID tracking, reviewer quality, and consolidator synthesis all depend on LLM compliance with no hard enforcement
2. **Silent degradation** — Missing frozen_spec.json or malformed living_spec can degrade output quality without raising errors
3. **Code rot** — Orphaned builders (design, deliver) and V2/V3 prompt coexistence indicate the codebase is evolving faster than cleanup

---

## Appendix: File Index

### Solution Pro Files Analyzed
- `domains/solution/SKILL.md` — Pipeline definition (V4.4)
- `domains/solution/blackboard.py` — STAGE_PATH_REGISTRY, BlackboardManager
- `domains/solution/task_builder.py` — All build_*_task() functions
- `domains/solution/harness_scorer.py` — 4-dimension scoring
- `domains/solution/frozen_spec.py` — REQ-ID generation
- `domains/solution/spec_context.py` — Living spec → worker context adapter
- `domains/solution/__init__.py` — run_solution_pro() entry point
- `domains/solution/orchestrator_agent.py` — _SolutionDispatcher
- `domains/solution/prompts/` — 22 prompt files

### Ship Pro Files Analyzed
- `domains/ship_pro/SKILL.md` — V2 三段式 pipeline definition
- `domains/ship_pro/scripts/run_pipeline.py` — V3.1 dynamic pipeline orchestrator
- `domains/ship_pro/eval/gates.py` — 4 gate functions (architect, decomposer, specifier, packager)
- `domains/ship_pro/eval/eval_code_checks.py` — Schema compliance, dependency graph checks
- `domains/ship_pro/prompts/` — 11 prompt files (5 V3 + 4 V2 + 2 support)

---

*Report generated by DeepFlow Pipeline Integrity Audit*  
*Next scheduled audit: After next major version bump*
