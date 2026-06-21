# Audit Task 3: Stale / Outdated Content Scan

> **Date**: 2026-06-22
> **Scope**: All `.md` files under `.deepflow/`, excluding ARCHIVED/, prompts_archive/, blackboard/, test_output/, AUDIT_*.md

---

## Summary

| Category | Count |
|----------|------:|
| TODO markers | 0 |
| FIXME markers | 0 |
| HACK / WORKAROUND markers | 0 |
| Chinese stale markers (尚未/暂未/待实现/待完成/待更新) | 7 |
| Old version file references | 12 |
| Deprecated references | 10 |
| **Total** | **29** |

---

## 1. TODO Markers

**No actionable TODO markers found.** All "TODO" occurrences are references to a "TODO app" used as a test case example in research/review documents, not incomplete work items.

---

## 2. FIXME Markers

**None found.**

---

## 3. HACK / WORKAROUND Markers

**None found.**

---

## 4. Chinese Stale Markers (尚未/暂未/待实现/待完成/待更新)

> Filtered out false positives: "等待完成" (wait-for-completion) is normal operational language in orchestrator prompts, not a stale marker. "暂未出现" in retry documentation describes expected transient states.

| # | File (relative) | Line | Content (truncated) |
|---|-----------------|------|---------------------|
| 1 | `domains/ship_pro/docs/ship_pro_v2_design.md` | 212 | `4. **V2 端到端仅验证 1 个场景**：跨境AI 场景尚未跑 V2 全流程` |
| 2 | `wiki/changelog.md` | 105 | `- **[Unreleased]**：6/11 之后的所有改动（尚未发布到 GitHub）` |
| 3 | `wiki/changelog.md` | 112 | `1. **Blackboard V2 目录结构**：设计完成但尚未实施` |
| 4 | `wiki/changelog.md` | 114 | `3. **端到端测试**：尚未验证所有恢复的代码` |
| 5 | `docs/SOLUTION_DEVELOPMENT_PLAN.md` | 30 | `\| **Prompt 深度优化** \| 🟢 P2 \| 输出质量依赖 prompt 设计，尚未精细调优 \|` |
| 6 | `docs/reviews/DATA_CONTRACT_REVIEW.md` | 12 | `v3_protocols.py 文件不存在！协议层尚未创建` |
| 7 | `docs/research/2026-06-19_pipeline_architecture_diagnosis.md` | 89 | `outputs 需要从零定义（项目结构尚未存在）` |

### Assessment
- Items 1–4 are **genuine incomplete work** — V2 end-to-end not validated, changelog unreleased, Blackboard V2 not implemented.
- Item 5 is a **known gap** — prompt optimization acknowledged as not yet tuned.
- Items 6–7 are in **review/diagnosis reports** — these describe state at time of writing, may be outdated.

---

## 5. Old Version File References

> References to `pipeline_orchestrator_v4.md`, `pipeline_orchestrator_v3.md`, `pro_pipeline_orchestrator_v3.md`, `pipeline_orchestrator_v6.md` in active (non-archive) context.

| # | File (relative) | Line | Content (truncated) |
|---|-----------------|------|---------------------|
| 1 | `domains/solution/README.md` | 76 | `[prompts/pipeline_orchestrator_v4.md](prompts/pipeline_orchestrator_v4.md) \| Orchestrator 指令 \| 运行时` |
| 2 | `docs/design/DIRECTORY_STRUCTURE.md` | 142 | `pipeline_orchestrator.md, pipeline_orchestrator_v4.md` |
| 3 | `docs/design/SOLUTION_PRO_RECOVERY_STATUS.md` | 33 | `pipeline_orchestrator.md \| ✅ \| 从 pipeline_orchestrator_v4.md 复制` |
| 4 | `docs/design/SOLUTION_PRO_RECOVERY_STATUS.md` | 107 | `pipeline_orchestrator_v4.md → pipeline_orchestrator.md` |
| 5 | `docs/design/RECOVERY_PENDING_ISSUES.md` | 95 | `pipeline_orchestrator.md ← pipeline_orchestrator_v4.md` |
| 6 | `docs/design/RECOVERY_PENDING_ISSUES.md` | 107 | `验证 Prompt 路径是否从 pipeline_orchestrator_v6.md 改为 pipeline_orchestrator.md` |
| 7 | `docs/design/RECOVERY_PENDING_ISSUES.md` | 114 | `确认引用的是 pipeline_orchestrator.md 而不是 pipeline_orchestrator_v6.md` |
| 8 | `docs/architecture/SOLUTION_PRO_ARCHITECTURE.md` | 297 | `pipeline_orchestrator_v4.md - Orchestrator Prompt` |
| 9 | `docs/architecture/SOLUTION_PRO_SUMMARY.md` | 162 | `pipeline_orchestrator_v4.md - Orchestrator Prompt` |
| 10 | `docs/guides/SOLUTION_PRO_USAGE_GUIDE.md` | 35 | `task=read("domains/solution/prompts/pipeline_orchestrator_v4.md").format(**plan)` |
| 11 | `docs/guides/SOLUTION_PRO_USAGE_GUIDE.md` | 272 | `pipeline_orchestrator_v4.md - Orchestrator Prompt` |
| 12 | `docs/design/RECOVERY_VERIFICATION_REPORT.md` | 68 | `solution/prompts/pipeline_orchestrator_v4.md \| 1` |

### Assessment
- `pipeline_orchestrator_v4.md` **still exists** in `domains/solution/prompts/` and is referenced as active in 5+ docs. This is a **stale reference** — the active file should be `pipeline_orchestrator.md` per recovery status.
- `pipeline_orchestrator_v6.md` is referenced in recovery pending issues as something that needs to be migrated away from — **migration may be incomplete**.
- Multiple architecture/usage docs still point to `_v4.md` instead of the canonical `pipeline_orchestrator.md`.

---

## 6. Deprecated / 废弃 / 已弃用 References

| # | File (relative) | Line | Content (truncated) |
|---|-----------------|------|---------------------|
| 1 | `domains/spec_pro/FIX_2026-06-04.md` | 24 | `_build_v3_main_eval_prompt()` 添加 DEPRECATED 标注（此方法返回值从未被使用） |
| 2 | `docs/design/PIPELINE_INTEGRITY_REPORT.md` | 76 | `build_fixer_task() marked @deprecated but still importable` |
| 3 | `docs/design/PIPELINE_INTEGRITY_REPORT.md` | 259 | `build_deliver_task() unused — Remove or document as deprecated` |
| 4 | `docs/design/PIPELINE_INTEGRITY_REPORT.md` | 260 | `build_fixer_task() deprecated but importable` |
| 5 | `docs/design/blackboard_system_redesign.md` | 25 | `final_solution.md ← 交付文件（即将废弃）` |
| 6 | `docs/design/blackboard_system_redesign.md` | 37 | `summarizer.json ← ⚠️ 即将废弃` |
| 7 | `docs/solution_pro_review_code.md` | 79 | `pipeline_orchestrator.md \| 2.0.0 \| 8 阶段 \| ❌ 废弃，无引用` |
| 8 | `contracts/skill_md_unification_contract.md` | 29 | `旧入口（run_v3/run_legacy）标记为 deprecated` |
| 9 | `docs/research/codex_integration_research.md` | 625 | `item/fileChange/outputDelta — 文件变更输出（已弃用）` |
| 10 | `docs/research/codex_integration_research.md` | 878 | `旧的 "body hash" 字段已弃用` |

### Assessment
- Items 1–4: **Known dead code** — flagged in reports but not yet cleaned up.
- Items 5–6: **Planned deprecation** — blackboard files marked "即将废弃" but not yet removed.
- Item 7: `pipeline_orchestrator.md` flagged as deprecated but **still exists on disk**.
- Item 8: Contract says old entry points should be deprecated — **action item may be pending**.
- Items 9–10: In a research doc about Codex API — **informational**, not actionable for DeepFlow code.

---

## Recommendations

### High Priority
1. **Resolve `pipeline_orchestrator_v4.md` references** — 5+ docs point to `_v4.md` but the active file is `pipeline_orchestrator.md`. Update all references or delete `_v4.md` if truly superseded.
2. **Complete `pipeline_orchestrator_v6.md` migration** — `RECOVERY_PENDING_ISSUES.md` flags this as unresolved.
3. **Address `wiki/changelog.md` unreleased items** — 3 entries marked "尚未" (unreleased, not implemented, not verified).

### Medium Priority
4. **Clean up deprecated Python functions** — `build_fixer_task()`, `build_deliver_task()`, `_build_v3_main_eval_prompt()` still in codebase.
5. **Execute blackboard file deprecation** — `final_solution.md` and `summarizer.json` marked "即将废弃".
6. **Ship Pro V2 end-to-end validation** — only 1 scenario validated, full flow not yet run.

### Low Priority
7. **Prompt tuning** — `SOLUTION_DEVELOPMENT_PLAN.md` acknowledges prompts are not yet fine-tuned.
8. **Update architecture docs** — `SOLUTION_PRO_ARCHITECTURE.md` and `SOLUTION_PRO_SUMMARY.md` reference old file paths.
