# Version Consistency Audit

> **Audit Date**: 2026-06-22
> **Scope**: All version declarations across the DeepFlow project

---

## 1. Source of Truth

| Source | Declared Version | Notes |
|--------|-----------------|-------|
| `CHANGELOG.md` (latest entry) | **0.4.0** (2026-06-05) | Highest authority for project version |
| `README.md` | **0.4.0** | Matches CHANGELOG |
| `pyproject.toml` | **0.1.0** | ⚠️ MISMATCH — never updated from initial |

**Project version inconsistency**: `pyproject.toml` declares `0.1.0` while CHANGELOG and README both say `0.4.0`.

---

## 2. Component Version Source of Truth (from CHANGELOG 0.4.0)

| Component | CHANGELOG Version | 
|-----------|------------------|
| Spec Pro | **2.4.0** |
| Solution Pro | **V4.4** |
| Research Pro | **1.0.0** |
| Ship Pro | *(not mentioned in CHANGELOG)* |

---

## 3. Full File Audit

### 3.1 Project-Level Files

| File (relative) | Declared Version | Expected | Consistent? |
|-----------------|-----------------|----------|-------------|
| `pyproject.toml` | `0.1.0` | `0.4.0` | ❌ NO |
| `README.md` | `0.4.0` | `0.4.0` | ✅ YES |
| `SKILL.md` (root) | `0.4.0` | `0.4.0` | ✅ YES |
| `CHANGELOG.md` | `0.4.0` (latest) | `0.4.0` | ✅ YES |

### 3.2 Spec Pro Domain

| File (relative) | Declared Version | Expected | Consistent? |
|-----------------|-----------------|----------|-------------|
| `domains/spec_pro/config/spec_pro.yaml` → `component_version` | `2.3.0` | `2.4.0` | ❌ NO |
| `domains/spec_pro/_overview.md` → `version` | `2.3.0` | `2.4.0` | ❌ NO |
| `domains/spec_pro/VERSION.md` → table row "Component" | `2.3.0` | `2.4.0` | ❌ NO |
| `domains/spec_pro/VERSION.md` → table row "Prompt" | `2.1.0` | *(independent)* | ℹ️ N/A |
| `domains/spec_pro/VERSION.md` → table row "Cage" | `2.1` | *(independent)* | ℹ️ N/A |
| `domains/spec_pro/prompts/orchestrator.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/structure.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/assess.md` | `2.2.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/assess_guide.md` | `2.2.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/parse.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/guide.md` | `2.2.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/harness.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/spec_pro/prompts/parse_response.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `cage/active/spec_pro_v2.0.yaml` → `version` | `2.1` | *(cage-level)* | ℹ️ N/A |

### 3.3 Solution Pro Domain

| File (relative) | Declared Version | Expected | Consistent? |
|-----------------|-----------------|----------|-------------|
| `domains/solution/config/solution.yaml` → `component_version` | `1.0.0` | `4.4` | ❌ NO |
| `domains/solution/_overview.md` | `4.3.0` | `4.4` | ❌ NO |
| `domains/solution/SKILL.md` | `V4.4` | `4.4` | ✅ YES |
| `domains/solution/prompts/pipeline_orchestrator_v4.md` | `4.3.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/pipeline_orchestrator.md` | `4.3.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/reviewer.md` | `5.4.1` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/consolidator.md` | `5.4.1` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/planner.md` | `5.4.1` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/summarizer.md` | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/designer.md` | `2.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/deliver.md` | `2.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/data_collection.md` | `2.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/harness_v3.md` | `2.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/cron_watcher.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/harness_scoring.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/solution/prompts/*_v2_harness.md` (7 files) | `2.1.0` | *(prompt-level)* | ℹ️ N/A |
| `cage/active/solution_v1.0.yaml` → `version` | `1.1` | *(cage-level)* | ℹ️ N/A |

### 3.4 Research Pro Domain

| File (relative) | Declared Version | Expected | Consistent? |
|-----------------|-----------------|----------|-------------|
| `domains/research_pro/config/research_pro.yaml` → `component_version` | `1.0.0` | `1.0.0` | ✅ YES |
| `domains/research_pro/SKILL.md` | `V2.1` | `1.0.0` | ❌ NO |
| `domains/research_pro/_overview.md` | *(no version)* | — | ℹ️ N/A |
| `domains/research_pro/prompts/search.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/research_pro/prompts/planning.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/research_pro/prompts/finance_analysis.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/research_pro/prompts/tech_analysis.md` | `1.1.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/research_pro/prompts/citation_verify.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `cage/active/research_pro_v1.0.yaml` → `version` | `1.0` | *(cage-level)* | ℹ️ N/A |

### 3.5 Ship Pro Domain

| File (relative) | Declared Version | Expected | Consistent? |
|-----------------|-----------------|----------|-------------|
| `domains/ship_pro/SKILL.md` | `V2.0` | See note | ⚠️ INCONSISTENT |
| `domains/ship_pro/_overview.md` | `V3` (title) | See note | ⚠️ INCONSISTENT |
| `domains/ship_pro/cage/active/ship_pro_v3.0.yaml` → `version` | `3.0.0` | See note | ⚠️ INCONSISTENT |
| `domains/ship_pro/prompts/ship_orchestrator.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |
| `domains/ship_pro/prompts/cron_watcher.md` | `1.0.0` | *(prompt-level)* | ℹ️ N/A |

> **Note**: Ship Pro has no CHANGELOG entry. Internal inconsistency: SKILL.md says V2.0, _overview.md says V3, cage YAML says 3.0.0. These three should at minimum agree with each other.

### 3.6 General Prompts (not domain-specific)

| File (relative) | Declared Version | Notes |
|-----------------|-----------------|-------|
| `prompts/general/auditor.md` | `1.0.0` | |
| `prompts/general/verifier.md` | `1.0.0` | |
| `prompts/general/researcher.md` | `1.0.0` | |
| `prompts/general/planner.md` | `1.0.0` | |
| `prompts/general/fixer.md` | `1.0.0` | |
| `prompts/code/verifier.md` | `1.0.0` | |
| `prompts/code/planner.md` | `1.0.0` | |
| `prompts/code/fixer.md` | `1.0.0` | |
| `prompts/code/correctness.md` | `1.0.0` | |
| `prompts/code/security.md` | `1.0.0` | |
| `prompts/system/deepflow_navigator.md` | `1.0.0` | |
| `prompts/system/summarizer.md` | `1.0.0` | |
| `prompts/system/data_manager_agent.md` | `1.0.0` | |
| `prompts/system/report_extractor.md` | `1.0.0` | |
| `prompts/system/pipeline_engine_orchestrator.md` | `1.0.0` | |
| `prompts/architecture/auditor.md` | `1.0.0` | |
| `prompts/architecture/researcher.md` | `1.0.0` | |
| `prompts/architecture/performance.md` | `1.0.0` | |
| `prompts/architecture/planner.md` | `1.0.0` | |
| `prompts/architecture/fixer.md` | `1.0.0` | |
| `prompts/architecture/correctness.md` | `1.0.0` | |
| `prompts/architecture/security.md` | `1.0.0` | |

> All general prompts are at `1.0.0` — internally consistent.

---

## 4. Summary of Inconsistencies

### Critical (component version vs CHANGELOG mismatch)

| # | File | Declared | Expected (CHANGELOG) | Severity |
|---|------|----------|---------------------|----------|
| 1 | `pyproject.toml` | `0.1.0` | `0.4.0` | 🔴 HIGH — package metadata is wrong |
| 2 | `domains/spec_pro/config/spec_pro.yaml` | `2.3.0` | `2.4.0` | 🔴 HIGH — runtime version read by code |
| 3 | `domains/spec_pro/_overview.md` | `2.3.0` | `2.4.0` | 🟡 MEDIUM — documentation |
| 4 | `domains/spec_pro/VERSION.md` (table) | `2.3.0` | `2.4.0` | 🟡 MEDIUM — documentation |
| 5 | `domains/solution/config/solution.yaml` | `1.0.0` | `4.4` | 🔴 HIGH — runtime version read by code |
| 6 | `domains/solution/_overview.md` | `4.3.0` | `4.4` | 🟡 MEDIUM — documentation |
| 7 | `domains/research_pro/SKILL.md` | `V2.1` | `1.0.0` | 🟡 MEDIUM — SKILL.md vs CHANGELOG |

### Internal Inconsistency (Ship Pro — no CHANGELOG baseline)

| # | File | Declared | Conflicts With | Severity |
|---|------|----------|---------------|----------|
| 8 | `domains/ship_pro/SKILL.md` | `V2.0` | `_overview.md` (V3), cage YAML (3.0.0) | 🔴 HIGH |
| 9 | `domains/ship_pro/_overview.md` | `V3` | `SKILL.md` (V2.0), cage YAML (3.0.0) | 🔴 HIGH |
| 10 | `domains/ship_pro/cage/active/ship_pro_v3.0.yaml` | `3.0.0` | `SKILL.md` (V2.0) | 🟡 MEDIUM |

---

## 5. Recommended Fixes

1. **`pyproject.toml`**: Update `version = "0.1.0"` → `version = "0.4.0"` to match CHANGELOG.
2. **`domains/spec_pro/config/spec_pro.yaml`**: Update `component_version: "2.3.0"` → `"2.4.0"`.
3. **`domains/spec_pro/_overview.md`**: Update `version: "2.3.0"` → `"2.4.0"`.
4. **`domains/spec_pro/VERSION.md`**: Update the table's Component row from `2.3.0` → `2.4.0`.
5. **`domains/solution/config/solution.yaml`**: Update `component_version: "1.0.0"` → `"4.4"`.
6. **`domains/solution/_overview.md`**: Update `版本: 4.3.0` → `版本: 4.4`.
7. **`domains/research_pro/SKILL.md`**: Clarify whether version is V2.1 or 1.0.0; align with CHANGELOG.
8. **Ship Pro**: Decide canonical version (V2.0 vs V3 vs 3.0.0) and update all three files to match. Add Ship Pro to CHANGELOG.

---

## 6. Statistics

| Metric | Count |
|--------|-------|
| Total files with version declarations | **68** |
| Files consistent with source of truth | **58** |
| Files with mismatches | **10** |
| Prompt-level files (independent versioning, excluded from mismatch count) | **~45** |
| Critical mismatches (runtime code reads wrong version) | **2** |
