# Broken File References Audit

**Scan Date**: 2026-06-22
**Files Scanned**: 326
**Broken References Found**: 111

## Methodology

- Scanned all `.md` files excluding `ARCHIVED/`, `prompts_archive/`, `test_output/`, `blackboard/`
- Extracted `[text](path)` links and bare path references (e.g. `domains/xxx/SKILL.md`)
- Skipped HTTP/HTTPS URLs, anchor-only links, placeholders (`xxx`, `*`, `<...>`)
- Resolved paths both relative to source file AND relative to project root; marked broken only if NEITHER exists
- Filtered out code references (e.g. `self.config`), non-.md paths

## Broken References

| Source File | Referenced Path |
|:---|:---|
| CONTRACTS.md | `docs/design/CODING_STANDARDS.md` |
| CONTRACTS.md | `docs/design/DEVELOPMENT_RULES.md` |
| README.md | `docs/archive/CODING_STANDARDS.md` |
| README.md | `docs/archive/DEVELOPMENT_RULES.md` |
| README.md | `skills/research-pro/SKILL.md` |
| contracts/skill_md_unification_contract.md | `skills/solution-pro/SKILL.md` |
| docs/ARCHITECTURE.md | `docs/harness_architecture_v4.md` |
| docs/architecture/SOLUTION_PRO_ARCHITECTURE.md | `docs/CRON_DESIGN.md` |
| docs/architecture/SOLUTION_PRO_ARCHITECTURE.md | `docs/CRON_EARLY_EXIT_POSTMORTEM.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `docs/CRON_EARLY_EXIT_POSTMORTEM.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `docs/SOLUTION_PRO_ARCHITECTURE.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `docs/SOLUTION_PRO_USAGE_GUIDE.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `domains/solution_pro/prompts/audit.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `domains/solution_pro/prompts/fix.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `domains/solution_pro/prompts/fixer_expert.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `domains/solution_pro/prompts/harness_final.md` |
| docs/architecture/SOLUTION_PRO_SUMMARY.md | `domains/solution_pro/prompts/planning.md` |
| docs/archive/ARCHIVE_STATUS.md | `docs/V4_FINAL_DESIGN.md` |
| docs/archive/ARCHIVE_STATUS.md | `docs/V4_IMPLEMENTATION_SPEC.md` |
| docs/archive/V4_ARCHITECTURE_PLAN.md | `ARCHITECTURE.md` |
| docs/archive/V4_COMPLETE_SPEC.md | `ARCHITECTURE.md` |
| docs/archive/V4_FINAL_DESIGN.md | `ARCHITECTURE.md` |
| docs/archive/deepclaw_dev_instructions.md | `skills/deep-research/SKILL.md` |
| docs/archive/deepclaw_dev_instructions.md | `skills/deep-research/prompts/citation_verify.md` |
| docs/archive/deepclaw_dev_instructions.md | `skills/deep-research/prompts/finance_analysis.md` |
| docs/archive/deepclaw_dev_instructions.md | `skills/deep-research/prompts/planning.md` |
| docs/archive/deepclaw_dev_instructions.md | `skills/deep-research/prompts/search.md` |
| docs/archive/exec_rename_v2.md | `skills/deepflow/SKILL.md` |
| docs/archive/frontend_design_requirements.md | `docs/harness_architecture_v2_final.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/deep-dive-v3-architecture-input.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/v3-architecture-inputs-comprehensive.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/v3-architecture-inputs-inventory.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/v3-architecture-inputs-summary.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/v3-p0-validation-report.md` |
| docs/deepdive_ARCHITECTURE_FINAL_REPORT.md | `docs/reports/v3-pre-design-spec.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `../../../skills/research-pro/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `../ARCHITECTURE_INPUT_OPENCLAW_EVOLUTION_2026.4.10-4.15.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `../OPENCLAW_AGENT_MECHANISM_REFERENCE.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/ARCHITECTURE_REVIEW_REPORT.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/CONTRACT_CONFLICT_REPORT.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/CRON_DESIGN.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/CRON_EARLY_EXIT_POSTMORTEM.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/SOLUTION_PRO_ARCHITECTURE.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/SOLUTION_PRO_USAGE_GUIDE.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/V4_FINAL_DESIGN.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/V4_IMPLEMENTATION_SPEC.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/api_gateway_config.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/archive/CODING_STANDARDS.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/archive/DEVELOPMENT_RULES.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/compliance_requirements.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/conversation_service_design.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/data_layer_architecture.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/design/CODE_CHANGES_JUNE18_21.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/design/CODING_STANDARDS.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/design/DEVELOPMENT_RULES.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/design/DOMAIN_RECOVERY_PART1-7.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/docs-review-technical-docs-expert.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/harness_architecture_v2_final.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/harness_architecture_v4.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/input_format_spec.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/deep-dive-v3-architecture-input.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/v3-architecture-inputs-comprehensive.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/v3-architecture-inputs-inventory.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/v3-architecture-inputs-summary.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/v3-p0-validation-report.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `docs/reports/v3-pre-design-spec.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/investment/CHANGES.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/solution_pro/prompts/audit.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/solution_pro/prompts/fix.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/solution_pro/prompts/fixer_expert.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/solution_pro/prompts/harness_final.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `domains/solution_pro/prompts/planning.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deep-research/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deep-research/prompts/citation_verify.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deep-research/prompts/finance_analysis.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deep-research/prompts/planning.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deep-research/prompts/search.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/deepflow/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/research-pro/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/solution-pro/SKILL.md` |
| docs/design/AUDIT_TASK1_BROKEN_LINKS.md | `skills/spec-pro/SKILL.md` |
| docs/design/RECOVERY_VERIFICATION_REPORT.md | `docs/design/CODE_CHANGES_JUNE18_21.md` |
| docs/guides/SOLUTION_PRO_USAGE_GUIDE.md | `docs/CRON_EARLY_EXIT_POSTMORTEM.md` |
| docs/guides/SOLUTION_PRO_USAGE_GUIDE.md | `docs/SOLUTION_PRO_ARCHITECTURE.md` |
| docs/guides/SOLUTION_PRO_USAGE_GUIDE.md | `domains/solution_pro/prompts/planning.md` |
| docs/openclaw-docs/INDEX.md | `../ARCHITECTURE_INPUT_OPENCLAW_EVOLUTION_2026.4.10-4.15.md` |
| docs/openclaw-docs/INDEX.md | `../OPENCLAW_AGENT_MECHANISM_REFERENCE.md` |
| docs/reports/REORGANIZATION_EXECUTION_PLAN.md | `domains/investment/CHANGES.md` |
| docs/reports/REORGANIZATION_IMPACT_ANALYSIS.md | `domains/investment/CHANGES.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/ARCHITECTURE_REVIEW_REPORT.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/CONTRACT_CONFLICT_REPORT.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/SKILL.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/design/CODING_STANDARDS.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/design/DEVELOPMENT_RULES.md` |
| docs/reports/REORGANIZATION_PLAN.md | `docs/docs-review-technical-docs-expert.md` |
| docs/reports/docs-review-technical-docs-expert.md | `design/SPEC_PRO_CONCEPT.md` |
| docs/research/2026-06-19_phase2_review_wp_quality.md | `docs/api_gateway_config.md` |
| docs/research/2026-06-19_phase2_review_wp_quality.md | `docs/compliance_requirements.md` |
| docs/research/2026-06-19_phase2_review_wp_quality.md | `docs/conversation_service_design.md` |
| docs/research/2026-06-19_phase2_review_wp_quality.md | `docs/data_layer_architecture.md` |
| docs/research/phase3_round1_rerun_results.md | `docs/input_format_spec.md` |
| domains/research_pro/README.md | `skills/research-pro/SKILL.md` |
| domains/research_pro/SKILL.md | `../../../skills/research-pro/SKILL.md` |
| domains/spec_pro/FIX_2026-06-04.md | `skills/spec-pro/SKILL.md` |
| frontend/README.md | `../cage/frontend_webhook_integration_v1.0.yaml` |
| frontend/STATUS.md | `../cage/frontend_phase4_cron_v1.0.yaml` |
| frontend/STATUS.md | `../cage/frontend_phase5_client_v1.0.yaml` |
| frontend/STATUS.md | `../cage/frontend_webhook_fix_v1.0.yaml` |
| frontend/STATUS.md | `../cage/frontend_webhook_integration_v1.0.yaml` |
| wiki/changelog.md | `docs/design/DOMAIN_RECOVERY_PART1-7.md` |
