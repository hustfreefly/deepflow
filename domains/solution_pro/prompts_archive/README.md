# Prompts Archive

This directory contains deprecated prompt files that are no longer used in the current Solution Pro V4.3 implementation.

## Archived Files

### Unused Worker Prompts (23 files)

These files were archived on 2026-06-02 because they are not referenced by any code in the current implementation:

- **Legacy orchestrator prompts**: `pipeline_orchestrator.md`, `pipeline_orchestrator_v3.md`, `pipeline_orchestrator_v4.md`, `pro_pipeline_orchestrator_v3.md`, `pipeline_execution_guide.md`
- **Legacy worker prompts**: `architect.md`, `auditor.md`, `consolidator.md`, `fixer.md`, `fixer_expert.md`, `planner.md`, `researcher.md`, `researcher_template.md`, `summarizer.md`
- **Legacy prefixed prompts**: `worker_auditor.md`, `worker_consolidator.md`, `worker_fixer.md`, `worker_planner.md`, `worker_researcher.md`, `worker_reviewer.md`, `worker_summarizer.md`
- **Other**: `cron_watcher.md`, `solution_planner_pro.md`, `deliver.md`

### Deprecated Python Module (1 file)

- `_deprecated_v3.py`: Deprecated orchestrator implementation from V3, kept for historical reference only

## Current Active Prompts (13 files)

The following prompts are actively used in Solution Pro V4.3 and remain in `domains/solution/prompts/`:

1. `auditor_v2_harness.md` - Auditor worker
2. `consolidator_v2_harness.md` - Consolidator worker
3. `data_collection.md` - Data collection worker
4. `deliver.md` - Deliver worker
5. `designer.md` - Designer worker
6. `fixer_expert_v2_harness.md` - Fixer expert worker
7. `fixer_v2_harness.md` - Fixer worker
8. `harness_scoring.md` - Harness scoring guide
9. `harness_v3.md` - Harness V3 quality gate
10. `planner_v2_harness.md` - Planner worker
11. `researcher_v2_harness.md` - Researcher worker
12. `reviewer_v2_harness.md` - Reviewer worker
13. `summarizer_v2_harness.md` - Summarizer worker

## Policy

- **Do not reference archived files** in new code
- **Do not delete** these files without explicit approval (kept for historical reference)
- If you need to restore a file, move it back to `domains/solution/prompts/` and update the corresponding code references

## Migration Notes

When migrating from archived prompts to current implementation:

- Worker prompts now use the `*_v2_harness.md` naming convention
- All active prompts use template variables (e.g., `{{ stage_name }}`)
- Schema validation is enforced via `validate_stage_output()` in `task_builder.py`
- Exempt stages (`data_collection`, `planning`, `summarizer`) do not require `harness_check`

For questions about archived files, refer to the CHANGELOG or contact the DeepFlow team.

---

**Archive Date**: 2026-06-02  
**Archived by**: Documentation slimming initiative  
**Solution Pro Version**: 4.3.0
