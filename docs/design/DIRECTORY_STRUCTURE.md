# DeepFlow Directory Structure

> **Last updated**: 2026-06-22
> **Project**: DeepFlow v0.4.0 — Multi-agent collaborative automation pipeline on OpenClaw
> **Scope**: This document maps the full directory tree and explains the purpose of each directory and key file.

---

## Quick Reference

| Section | What it is |
|---------|------------|
| `core/` | Pure infrastructure — orchestrator, blackboard, cage engine, quality gates |
| `domains/` | Business domains — each self-contained (code + prompts + config + tests) |
| `contracts/` | Global contracts (LLM-readable `.md` rules for all modules) |
| `cage/` | Module-level scene contracts (`.yaml` behavioral definitions) |
| `prompts/` | Cross-module shared prompts only |
| `config/` | Global config only (domain config lives in `domains/*/config/`) |
| `tests/` | Cross-module integration tests only |
| `frontend/` | Independent sub-project (React + FastAPI web UI) |
| `scripts/` | Ops/CI/validation scripts |
| `docs/` | Reference documentation (not contracts) |
| `eval/` | Evaluation harnesses and prompt rename contracts |
| `super_loop/` | Phase 2: Ship Package → Code execution pipeline |
| `ARCHIVED/` | Legacy code/docs archived from v1.0 |
| `blackboard/` | Runtime data (gitignored, not in repo) |

---

## Directory Tree

```
.deepflow/
├── README.md                              # Readme 中文版
├── readme-en.md                           # Readme 英文版
├── SKILL.md                               # OpenClaw skill definition (triggers & usage)
├── CHANGELOG.md                           # Version history (v0.4.0 current)
├── CONTRACTS.md                           # Contract system specification (format & lifecycle)
├── QUICKSTART.md                          # 5-minute quickstart guide
├── QUALITY_GUIDE.md                       # Quality standards for all domains
├── __init__.py                            # Package init
├── pyproject.toml                         # Python project config
├── pytest.ini                             # Pytest configuration
├── .gitignore                             # Git ignore rules
│
├── core/                                  # Pure infrastructure layer
│   ├── unified_entry.py                   # Unified entry point for all domains
│   ├── config_loader.py                   # YAML config loader
│   ├── prompt_registry.py                 # Prompt registry (loads prompts/registry.yaml)
│   ├── prompt_utils.py                    # Prompt utility functions
│   ├── checkpoint_manager.py              # Pipeline checkpoint/resume
│   ├── app_config.py                      # App-level configuration
│   ├── config/                            # Path & module config
│   │   ├── __init__.py
│   │   └── path_config.py                 # PathConfig: resolve all project paths
│   ├── orchestrator/                      # Orchestration engine
│   │   ├── __init__.py
│   │   ├── orchestrator_base.py           # Base orchestrator class
│   │   └── pipeline_orchestrator.py       # Pipeline orchestrator
│   ├── blackboard/                        # Blackboard system (agent communication)
│   │   ├── blackboard_manager.py          # Blackboard lifecycle management
│   │   └── blackboard_bridge.py           # Bridge between domains
│   ├── cage/                              # Cage engine (contract enforcement)
│   │   ├── __init__.py
│   │   ├── cage_loader.py                 # Load YAML contracts
│   │   ├── cage_validator.py              # Validate code against contracts
│   │   └── cage_checkpoint.py             # Checkpoint integration
│   ├── quality/                           # Quality gates & observability
│   │   ├── __init__.py
│   │   ├── quality_gate.py                # Quality gate enforcement
│   │   ├── entry_harness.py               # Entry-level harness checks
│   │   └── observability.py               # Logging & metrics
│   └── agents/                            # Scheduled/webhook task agents
│       ├── __init__.py
│       ├── cron_task_checker.py           # Cron task checker
│       ├── webhook_task_processor.py      # Webhook task processor
│       └── spawn_resolver.py              # Spawn resolver
│
├── domains/                               # Business domains (self-contained)
│   ├── code.yaml                          # Code domain config
│   ├── general.yaml                       # General domain config
│   ├── architecture.yaml                  # Architecture domain config
│   │
│   ├── spec_pro/                          # Spec Pro: Requirements collection engine
│   │   ├── __init__.py
│   │   ├── _overview.md                   # Domain overview (30-sec onramp)
│   │   ├── coordinator.py                 # Main coordinator (Socratic dialog)
│   │   ├── models.py                      # Data models (LivingSpec, QualityLevel)
│   │   ├── merge_spec.py                  # Incremental spec merging
│   │   ├── utils.py                       # Utility functions
│   │   ├── worker_fallback.py             # Worker fallback on failure
│   │   ├── process_guard.py               # Process guarding
│   │   ├── spec_pro_api.py                # CLI API (init/next_round/status)
│   │   ├── schemas.py                     # JSON schemas
│   │   ├── response_normalizer.py         # Response normalization
│   │   ├── update_conversation_log.py     # Conversation log updates
│   │   ├── QUALITY_GUIDE.md               # Domain quality guide
│   │   ├── IMPROVEMENTS.md                # Improvement tracking
│   │   ├── VERSION.md                     # Version info
│   │   ├── REMEDIATION_PLAN.md            # Remediation plan
│   │   ├── prompts/                       # Domain prompts (7 files)
│   │   │   ├── orchestrator.md
│   │   │   ├── guide.md, assess.md, structure.md
│   │   │   ├── parse.md, harness.md, parse_response.md
│   │   │   └── assess_guide.md
│   │   ├── config/spec_pro.yaml           # Domain config
│   │   └── eval/harness.py                # Evaluation harness
│   │
│   ├── solution/                          # Solution Pro: Solution design engine
│   │   ├── __init__.py
│   │   ├── _overview.md                   # Domain overview
│   │   ├── README.md                      # Domain readme
│   │   ├── SKILL.md                       # Domain skill
│   │   ├── orchestrator_agent.py          # _SolutionDispatcher orchestrator
│   │   ├── task_builder.py                # Worker task builder + schema + validator
│   │   ├── control_contract.py            # Post-planning control_contract.json refresh
│   │   ├── completion_handler.py          # Completion check + runtime schema validation
│   │   ├── blackboard.py                  # Blackboard management + STAGE_PATH_REGISTRY
│   │   ├── frozen_spec.py                 # REQ-ID frozen spec generation
│   │   ├── security_validator.py          # Input sanitization + path traversal detection
│   │   ├── harness_scorer.py              # Harness scoring
│   │   ├── harness_scoring.py             # Harness scoring helper
│   │   ├── harness_validator.py           # Harness validation
│   │   ├── harness_check_expert.py        # Harness expert
│   │   ├── planner.py                     # Planner helper
│   │   ├── prefix_extractor.py            # Session ID prefix extraction
│   │   ├── progress_tracker.py            # Progress tracking
│   │   ├── check_contract.py              # Contract validation
│   │   ├── normalize.py                   # Normalization
│   │   ├── spec_context.py                # Spec context
│   │   ├── lightweight_spec_agent.py      # Lightweight spec agent
│   │   ├── config.py                      # Domain config
│   │   ├── QUALITY_GUIDE.md               # Domain quality guide
│   │   ├── config/solution.yaml           # Domain config
│   │   ├── data_sources/solution.yaml     # Data source config
│   │   ├── prompts/                       # 36 worker prompts (10 stages + harness)
│   │   │   ├── planner.md, reviewer.md, summarizer.md
│   │   │   ├── designer.md, deliver.md, consolidator.md
│   │   │   ├── data_collection.md, cron_watcher.md
│   │   │   ├── harness_v3.md, harness_scoring.md
│   │   │   ├── harness_check v2 prompts (auditor, fixer, reviewer, etc.)
│   │   │   ├── pipeline_orchestrator.md, pipeline_orchestrator_v4.md
│   │   │   ├── orchestrator_completion.md, REQ_DEDUP_DESIGN.md
│   │   │   └── researcher/planner/consolidator v2 harness variants
│   │   ├── prompts_archive/               # Archived old prompts (~20 files)
│   │   ├── eval/                          # Evaluation tools
│   │   │   ├── propagation_checker.py
│   │   │   └── test_v6_improvements.py
│   │   ├── scripts/validate_req_dedup.py  # REQ dedup validator
│   │   └── reviews/                       # Review documents (3 files)
│   │
│   ├── research_pro/                      # Research Pro: Deep research engine
│   │   ├── __init__.py
│   │   ├── _overview.md                   # Domain overview
│   │   ├── README.md                      # Domain readme
│   │   ├── SKILL.md                       # Domain skill
│   │   ├── orchestrator.py                # ResearchProOrchestrator
│   │   ├── citation_verifier.py           # Citation verification
│   │   ├── keyword_generator.py           # Keyword generation
│   │   ├── source_registry.py             # Source registration
│   │   ├── tier_classifier.py             # Tier classification
│   │   ├── url_utils.py                   # URL utilities
│   │   ├── safe_fetcher.py                # Safe HTTP fetcher (SSRF protection)
│   │   ├── ddgs_client.py                 # DuckDuckGo search client
│   │   ├── prompts/                       # Domain prompts (5 files)
│   │   │   ├── search.md, planning.md
│   │   │   ├── citation_verify.md
│   │   │   ├── finance_analysis.md, tech_analysis.md
│   │   ├── config/                        # Domain config (4 files)
│   │   │   ├── research_pro.yaml
│   │   │   ├── completion_criteria.json
│   │   │   ├── tier_domains.json
│   │   │   └── time_budgets.json
│   │   ├── tests/                         # Domain tests (9 files)
│   │   ├── expert_consultation/           # Expert consultation docs (5 files)
│   │   ├── reviews/                       # Review documents (5 files)
│   │   └── audit reports (6 files)
│   │
│   └── ship_pro/                          # Ship Pro: AI-native multi-agent coding engine
│       ├── _overview.md                   # Domain overview
│       ├── SKILL.md                       # Domain skill
│       ├── decomposer.py                  # WP decomposition
│       ├── scripts/                       # Orchestration scripts
│       │   ├── orchestrator.py            # Orchestrator (run_config generation)
│       │   ├── e2e_test.py                # E2E test harness
│       │   ├── e2e_prepare.py, e2e_validate.py, e2e_report.py, e2e_common.py
│       │   ├── validate_input.py          # Input validation
│       │   └── run_pipeline.py            # Pipeline runner
│       ├── prompts/                       # 11 agent prompts
│       │   ├── architect.md, decomposer.md, specifier.md
│       │   ├── reviewer.md, packager.md
│       │   ├── ship_reviewer.md, ship_harness.md, ship_orchestrator.md
│       │   ├── ship_pre_scanner.md, ship_fixer.md, cron_watcher.md
│       ├── schemas/                       # JSON schemas
│       │   ├── final_result_v3.schema.json
│       │   └── ship_package_v3.schema.json
│       ├── eval/                          # Evaluation tools
│       │   ├── gates.py, eval_code_checks.py
│       │   ├── test_gates.py, test_eval_checks.py
│       ├── audit/                         # Audit documents (4 files)
│       ├── audit_v2/                      # V2 audit (3 files)
│       ├── docs/                          # Design docs (2 files)
│       ├── cage/active/ship_pro_v3.0.yaml # Scene contract
│       └── test_output/                   # Test output data (many subdirectories)
│
├── contracts/                             # Global contracts (LLM-readable .md)
│   ├── directory_structure.md             # Directory structure contract (v3.1.0)
│   ├── coding_standards.md                # Coding standards
│   ├── development_workflow.md            # Development workflow
│   ├── cage_framework.md                  # Cage framework specification
│   ├── version_control.md                 # Version control contract
│   ├── skill_md_unification_contract.md   # SKILL.md unification
│   ├── integration/                       # Cross-module integration contracts
│   │   └── spec_to_solution.md            # Spec Pro → Solution Pro handoff
│   └── shared/                            # Shared design docs
│       ├── pipeline_watcher_design.md
│       └── pipeline_watcher_v2_design.md
│
├── cage/                                  # Scene contracts (module-level .yaml)
│   ├── spec_pro_direct_driver.yaml        # Spec Pro direct driver contract
│   ├── active/                            # Active contracts
│   │   ├── spec_pro_v2.0.yaml
│   │   ├── solution_v1.0.yaml
│   │   ├── research_pro_v1.0.yaml
│   │   ├── ship_pro_v3.0.yaml
│   │   ├── integrate_codegraph.yaml
│   │   ├── version_mgmt_migration.yaml
│   │   └── root_cleanup_v1.0.yaml
│   ├── archive/                           # Archived contracts (~20 files)
│   │   └── templates/module_contract.yaml  # Contract template
│   └── assess_guide_merge/                # Assess guide merge contract
│
├── prompts/                               # Cross-module shared prompts only
│   ├── registry.yaml                      # Prompt registry (maps domain → prompts)
│   ├── general/                           # General-purpose prompts
│   │   └── auditor.md, verifier.md, researcher.md, planner.md, fixer.md
│   ├── code/                              # Code-domain prompts
│   │   └── verifier.md, planner.md, fixer.md, correctness.md, security.md
│   ├── architecture/                      # Architecture-domain prompts
│   │   └── auditor.md, researcher.md, planner.md, fixer.md
│   │   └── correctness.md, security.md, performance.md
│   └── system/                            # System prompts
│       ├── deepflow_navigator.md
│       ├── summarizer.md
│       ├── data_manager_agent.md
│       ├── report_extractor.md
│       └── pipeline_engine_orchestrator.md
│
├── config/                                # Global config only
│   ├── global_config.yaml                 # Global settings
│   ├── resilience_config.yaml             # Resilience/retry settings
│   ├── delivery_config.yaml               # Delivery settings
│   ├── timeout_config.yaml                # Timeout settings
│   └── notification_config.yaml           # Notification settings
│
├── frontend/                              # Web UI (independent sub-project)
│   ├── README.md                          # Frontend readme
│   ├── STATUS.md                          # Frontend status
│   ├── backend/                           # FastAPI backend (Python)
│   │   ├── main.py                        # FastAPI entry point
│   │   ├── database.py                    # SQLite database
│   │   ├── spec_extractor.py              # Spec extraction
│   │   ├── requirements.txt               # Python dependencies
│   │   ├── routers/                       # API routers
│   │   │   ├── tasks.py, tasks_v2.py      # Task CRUD
│   │   │   ├── status.py, status_v2.py    # Status endpoints
│   │   │   ├── upload.py                  # File upload
│   │   │   ├── consumer.py                # Consumer endpoint
│   │   │   └── health.py                  # Health check
│   │   └── utils/feishu_doc.py            # Feishu doc integration
│   └── web/                               # React frontend (TypeScript + Tailwind)
│       ├── index.html, package.json, vite.config.ts
│       ├── src/
│       │   ├── App.tsx, main.tsx, index.css
│       │   ├── api/client.ts              # API client
│       │   ├── contexts/SettingsContext.tsx
│       │   ├── config/defaults.ts
│       │   ├── hooks/useTask.ts
│       │   ├── components/
│       │   │   ├── Header.tsx
│       │   │   ├── SpecUpload.tsx
│       │   │   └── SettingsDialog.tsx
│       │   └── pages/
│       │       ├── TaskForm.tsx
│       │       ├── ProgressPage.tsx
│       │       ├── PipelineDetails.tsx
│       │       ├── ReportPage.tsx
│       │       └── HistoryPage.tsx
│       └── public/favicon.svg
│
├── scripts/                               # Ops/CI/validation scripts
│   ├── protocols.py                       # Protocol definitions
│   ├── validate.py                        # Validation runner
│   ├── prompt_loader.py                   # Prompt loader
│   ├── pipeline_watcher.py                # Pipeline watcher
│   ├── pipeline_progress_notify.py        # Progress notification
│   ├── start_solution_pro.py              # Solution Pro starter
│   ├── v3_v4_analysis.py                  # V3→V4 migration analysis
│   ├── migrate_version_headers.py         # Version header migration
│   ├── data_collect_smic.py               # SMIC data collection
│   ├── git_auto_backup.sh                 # Git auto-backup
│   ├── extract_ship_review_data.py        # Ship review data extractor
│   ├── golden_solution_pro_dry_run.py     # Golden case dry-run
│   ├── validate_solution_pro_contract.py  # Solution Pro contract validator
│   ├── verify_solution_pro_entry.py       # Entry verification
│   ├── setup_webhook_config.sh            # Webhook config setup
│   ├── setup_cron_job.sh                  # Cron job setup
│   ├── verify_webhook.sh                  # Webhook verification
│   ├── ci/                                # CI scripts
│   │   ├── ci.sh, test_run.sh, run_tests.sh
│   ├── checks/                            # Validation checks (~30 files)
│   │   ├── check_pipeline_engine.py
│   │   ├── check_orchestrator_v2.py, v4.py
│   │   ├── check_data_manager.py, v4.py
│   │   ├── check_standards.py
│   │   ├── check_phase1_fix.py → phase3_fix.py
│   │   ├── check_p0_fix.py, check_p0_p1_fix.py
│   │   └── ... (many more)
│   ├── runners/                           # Task runners
│   │   ├── run_spec_pro.py, run_solution_task.py
│   │   ├── run_all_tasks.py, run_task_1.py
│   │   └── run_orchestrator.sh
│   └── maintenance/cleanup_plan.sh        # Maintenance scripts
│
├── tests/                                 # Cross-module integration tests
│   ├── __init__.py, conftest.py
│   ├── test_path_config.py
│   ├── test_prompt_registry.py
│   ├── test_frontend_e2e.py
│   ├── e2e_solution_test.py
│   ├── smoke_solution_pro.py
│   ├── test_e2e_living_spec_v2.py
│   ├── unit/                              # Unit tests
│   │   ├── test_init_pipeline.py
│   │   ├── test_e2e_production.py
│   │   ├── test_regression.py
│   │   ├── test_spec_pro_regressions.py
│   │   └── fixtures/test_helpers.py
│   ├── contract/                          # Contract tests
│   │   ├── test_data_manager.py
│   │   ├── test_quality_gate.py
│   │   └── test_blackboard_manager.py
│   ├── e2e/run_real_e2e.py                # E2E test runner
│   ├── golden/                            # Golden case tests
│   │   ├── golden_case_001.json
│   │   ├── verify_golden_case.py
│   │   └── run_golden_e2e.py
│   ├── results/                           # Test results (many JSON/MD files)
│   └── _archived/                         # Archived tests (~8 files)
│
├── docs/                                  # Reference documentation
│   ├── ARCHITECTURE.md                    # Architecture design (v1.4)
│   ├── ARCHITECTURE_FLOW.md               # Architecture flow diagram
│   ├── QUICKSTART.md                      # Quickstart guide
│   ├── configuration.md                   # Configuration guide
│   ├── LAUNCH_PROTOCOL.md                 # Launch protocol
│   ├── DEBUG_REVIEW.md                    # Debug review
│   ├── STANDARD_EXECUTION.md              # Standard execution
│   ├── CAGE_PREREQUISITE_BANS.md          # Cage prerequisite bans
│   ├── HARNESS_INSIGHT_ANALYSIS.md        # Harness insight analysis
│   ├── PATH_DESIGN_SPEC.md                # Path design spec
│   ├── SOLUTION_MODULE_DESIGN.md          # Solution module design
│   ├── SPEC_PRO_TECHNICAL_ARCHITECTURE.md # Spec Pro technical architecture
│   ├── SPEC_PRO_CONCEPT_V2.md             # Spec Pro concept v2
│   ├── SPEC_PRO_HARNESS_DESIGN.md         # Spec Pro harness design
│   ├── SOLUTION_PRO_MODE_DESIGN.md        # Solution Pro mode design
│   ├── SOLUTION_AGENT_PROMPT_DESIGN.md    # Solution agent prompt design
│   ├── SOLUTION_DEVELOPMENT_PLAN.md       # Solution development plan
│   ├── REQUIREMENT_COLLECTION_ARCHITECTURE.md
│   ├── REQUIREMENT_COLLECTION_MODULE_ANALYSIS.md
│   ├── REQUIREMENT_ENGINE_DEEP_ANALYSIS.md
│   ├── FRONTEND_DESIGN.md                 # Frontend design
│   ├── FULL_REHEARSAL_REPORT.md           # Full rehearsal report
│   ├── spec_pro_review.md                 # Spec Pro review
│   ├── solution_pro_review_code.md        # Solution Pro code review
│   ├── code-quality-review-engines-reorg.md
│   ├── version_mgmt_review.md
│   ├── deepdive_ARCHITECTURE_DESIGN_FINAL_COMPLETE.md
│   ├── deepdive_ARCHITECTURE_FINAL_REPORT.md
│   ├── RFC-001-prompt-registry.md
│   ├── 前端开发任务指导.md                  # Frontend dev guide (Chinese)
│   ├── 前端 API 契约.md                    # Frontend API contract (Chinese)
│   ├── architecture/                      # Architecture docs
│   │   ├── SOLUTION_PRO_ARCHITECTURE.md
│   │   ├── SOLUTION_PRO_SUMMARY.md
│   │   ├── PROGRESS_NOTIFICATION_DESIGN.md
│   │   └── ORCHESTRATOR_COMPLETION_HANDLER.md
│   ├── contracts/solution_pro_schema.md   # Solution Pro schema
│   ├── cron/deepflow_processor.md         # Cron processor docs
│   ├── design/                            # Design documents
│   │   ├── SYSTEM_PROMPT.md
│   │   ├── PROTOCOLS.md, PROTOCOLS_README.md
│   │   ├── REBUILD_PLAN.md
│   │   ├── PIPELINE_INTEGRITY_REPORT.md
│   │   ├── UNIFIED_ENTRY_IMPLEMENTATION.md
│   │   ├── RECOVERY_VERIFICATION_REPORT.md
│   │   ├── RECOVERY_PENDING_ISSUES.md
│   │   ├── DOMAIN_RECOVERY_PART1-7.md
│   │   ├── SPEC_PRO_RECOVERY_STATUS.md
│   │   ├── SOLUTION_PRO_RECOVERY_STATUS.md
│   │   ├── SHIP_PRO_RECOVERY_STATUS.md
│   │   ├── spec_solution_link_v2.md
│   │   ├── spec_pro_to_solution_pro_link_upgrade.md
│   │   ├── task_builder_checklist_report.md
│   │   ├── blackboard_review_context.md
│   │   ├── blackboard_review_architect.md
│   │   ├── blackboard_system_redesign.md
│   │   ├── review_implementation.md
│   │   ├── review_architect.md
│   │   ├── review_llm_engineer.md
│   │   ├── cage_step1_path_config.md
│   │   └── cage_step2_blackboard.md
│   ├── diagrams/                         # Architecture diagrams
│   │   ├── architecture.png, architecture_v2.png, architecture.html
│   │   ├── global_architecture.png, global_architecture.html
│   │   ├── 01_cover.png, 02_three_layers.png, 03_data_flow.png
│   │   ├── 04_spec_pro.png, 05_solution_pro.png, 06_blackboard.png
│   │   ├── view01_module.png → view06_journey.png
│   │   ├── v3_multi_view.png, v3_multi_view.html
│   │   ├── multi_dim_full.png, multi_dim_v2.png, multi_dim_cards.html
│   │   ├── douyin_deck.html, douyin_deck_v2.html, douyin_deck_full.png
│   │   └── review_expert1_info_arch.md, review_expert2_visual.md
│   ├── guides/SOLUTION_PRO_USAGE_GUIDE.md
│   ├── reference/OPENCLAW_AGENT_MECHANISM_REFERENCE.md
│   ├── reports/                          # Audit & review reports
│   │   ├── ARCHITECTURE_REVIEW_REPORT.md
│   │   ├── CONTRACT_CONFLICT_REPORT.md
│   │   ├── REORGANIZATION_PLAN.md
│   │   ├── REORGANIZATION_DECISION.md
│   │   ├── REORGANIZATION_IMPACT_ANALYSIS.md
│   │   ├── REORGANIZATION_EXECUTION_PLAN.md
│   │   └── docs-review-technical-docs-expert.md
│   ├── reviews/                          # Review documents
│   │   ├── DATA_CONTRACT_REVIEW.md
│   │   ├── PHASE_2.7_REVIEW_SUMMARY.md
│   │   ├── architecture-consistency-review.md
│   │   ├── integration-feasibility-review.md
│   │   ├── validator_quality_review.md
│   │   ├── expert_architecture.md, expert_ux.md, expert_tools.md
│   │   ├── cron_architecture.md, cron_reliability.md
│   │   └── cron_tools_capability.md
│   ├── research/                         # Research & analysis
│   │   ├── phase0_input_analysis.md
│   │   ├── phase1_round2_test_results.md
│   │   ├── phase2_integration_test_plan.md
│   │   ├── phase3_round1_rerun_results.md
│   │   ├── phase3_zhongli_acceptance.md
│   │   ├── industry_best_practices.md
│   │   ├── industry_orchestration_patterns.md
│   │   ├── architecture_pattern_comparison.md
│   │   ├── ai_native_search_1_workflow.md → 4_philosophy.md
│   │   ├── deepflow_capability_assessment.md
│   │   ├── codex_integration_research.md
│   │   ├── claude_code_integration_research.md
│   │   ├── openclaw_orchestration_capabilities.md
│   │   ├── plan_b_implementation_research.md
│   │   ├── solution_optimization_analysis.md
│   │   ├── SOLUTION_E2E_PRE_ANALYSIS.md
│   │   ├── SOLUTION_E2E_DEEP_ANALYSIS.md
│   │   ├── SOLUTION_COMPREHENSIVE_ANALYSIS.md
│   │   └── 2026-06-18_expert_reports/     # 16 expert reports + synthesis
│   ├── openclaw-docs/                    # OpenClaw platform docs
│   │   ├── INDEX.md
│   │   └── multi-agent-routing.md
│   ├── archive/                          # Archived docs (~20 files)
│   └── audit_reports/                    # Audit reports
│       └── prompt_correctness_2026-04-19.md
│
├── eval/                                 # Evaluation harnesses
│   ├── verify_prompt_rename.py
│   ├── review_reliability.md
│   ├── serenity_skills_astock_case_study.md
│   ├── prompt_rename_contract.yaml
│   └── architect_format_fix_contract.yaml
│
├── super_loop/                           # Phase 2: Code execution pipeline
│   └── README.md                         # Super Loop design doc
│
├── skills/                               # OpenClaw skill definitions
│   └── solution-pro/
│       └── orchestrator_prompt_v2.md
│
├── tools/                                # Cross-module tools
│   └── deepflow_cli.py                   # DeepFlow CLI
│
├── wiki/                                 # Wiki docs
│   ├── deepflow_overview.md
│   └── changelog.md
│
├── reviews/                              # Review artifacts
│   ├── spec-to-solution-ux-review.md
│   ├── trigger_chain_review.json
│   ├── solution_pro_trigger_audit.json
│   └── architecture_review.json
│
├── ARCHITECTURE_REVIEW/                  # Architecture review docs
│   └── frozen_spec_v2_review.md
│
├── ARCHIVED/                             # Legacy code (v1.0)
│   ├── V1_BLUEPRINT.md
│   ├── MIGRATION_GUIDE.md
│   └── v1.0_legacy/                      # ~15 legacy Python files
│
├── blackboard/                           # Runtime data (gitignored)
│   └── research_pro_*/                   # Research Pro session data
│
└── logs/                                 # Log files
    └── git_backup_20260622.log
```

---

## File Counts by Type

| Type | Count | Description |
|------|-------|-------------|
| `.md` | 375 | Markdown — prompts, contracts, docs, overviews, audit reports |
| `.py` | 205 | Python — domain code, core infrastructure, tests, scripts |
| `.json` | 121 | JSON — schemas, test data, blackboard artifacts, test results |
| `.yaml` | 41 | YAML — configs, scene contracts, prompt registries |
| `.png` | 20 | PNG — architecture diagrams, deck images |
| `.tsx` | 11 | TSX — React frontend components and pages |
| `.sh` | 9 | Shell — CI scripts, setup scripts, maintenance |
| `.html` | 8 | HTML — interactive architecture diagrams |
| `.ts` | 4 | TypeScript — frontend config, hooks, API |
| `.js` | 2 | JavaScript — Tailwind config, PostCSS config |
| `.toml` | 1 | TOML — pyproject.toml |
| `.ini` | 1 | INI — pytest.ini |
| `.css` | 1 | CSS — frontend styles |
| `.svg` | 1 | SVG — favicon |
| `.log` | 1 | Log — git backup log |
| **Total** | **~811** | (excluding __pycache__, .git, .DS_Store, node_modules) |

---

## Directory Purpose Summary

### Core Layer (`core/`)
| Directory | Purpose |
|-----------|---------|
| `core/config/` | Path resolution and config loading for the entire project |
| `core/orchestrator/` | Base orchestrator and pipeline orchestration engine |
| `core/blackboard/` | Blackboard system for inter-agent communication |
| `core/cage/` | Cage contract engine — load, validate, and checkpoint YAML contracts |
| `core/quality/` | Quality gates, entry harness, and observability |
| `core/agents/` | Scheduled task checker and webhook task processor |

### Domain Layer (`domains/`)
| Directory | Purpose |
|-----------|---------|
| `domains/spec_pro/` | Spec Pro v2.4 — Requirements collection via Socratic dialog → Living Spec |
| `domains/solution/` | Solution Pro V4.4 — 10-stage pipeline for solution design → final_solution.md |
| `domains/research_pro/` | Research Pro — Multi-source search → tiered research → citation-verified reports |
| `domains/ship_pro/` | Ship Pro V3 — AI-native multi-agent: Architect → Decomposer → Specifier → Reviewer → Packager |

### Contracts & Rules Layer
| Directory | Purpose |
|-----------|---------|
| `contracts/` | Global contracts — LLM-readable `.md` rules that all modules must follow |
| `contracts/integration/` | Cross-module integration contracts (e.g., Spec Pro → Solution Pro handoff) |
| `cage/active/` | Active scene contracts — module-level `.yaml` behavioral definitions |
| `cage/archive/` | Archived/completed scene contracts |

### Shared Resources
| Directory | Purpose |
|-----------|---------|
| `prompts/` | Cross-module shared prompts (general/code/architecture/system) |
| `config/` | Global configuration (resilience, delivery, timeout, notifications) |
| `tests/` | Cross-module integration & E2E tests |
| `tools/` | Cross-module CLI tools |
| `scripts/` | Ops, CI, validation, and maintenance scripts |

### Documentation (`docs/`)
| Directory | Purpose |
|-----------|---------|
| `docs/architecture/` | Architecture design documents |
| `docs/design/` | Detailed design specs and recovery plans |
| `docs/diagrams/` | Visual architecture diagrams (PNG + HTML) |
| `docs/research/` | Research, analysis, and expert reports |
| `docs/reports/` | Audit reports, review records, reorganization plans |
| `docs/reviews/` | Expert review documents |
| `docs/guides/` | Usage guides and tutorials |
| `docs/archive/` | Archived documentation |
| `docs/contracts/` | Contract documentation |
| `docs/openclaw-docs/` | OpenClaw platform reference docs |
| `docs/cron/` | Cron processor documentation |

### Frontend (`frontend/`)
| Directory | Purpose |
|-----------|---------|
| `frontend/backend/` | FastAPI Python backend (REST API, SQLite, routers) |
| `frontend/backend/routers/` | API endpoints (tasks, status, upload, consumer, health) |
| `frontend/web/` | React 18 + TypeScript + Tailwind frontend |

### Other Top-Level Directories
| Directory | Purpose |
|-----------|---------|
| `eval/` | Evaluation harnesses and prompt rename contracts |
| `super_loop/` | Phase 2: Ship Package → Code execution pipeline (planning stage) |
| `skills/` | OpenClaw skill definitions for domain integration |
| `wiki/` | Wiki documentation (overview + changelog) |
| `reviews/` | Review artifacts (JSON + MD) |
| `ARCHITECTURE_REVIEW/` | Architecture review documents |
| `ARCHIVED/` | Legacy v1.0 code and docs |
| `blackboard/` | Runtime blackboard data (gitignored) |
| `logs/` | Application log files |

---

## Key Top-Level Files

| File | Purpose |
|------|---------|
| `README.md` | Main project readme (Chinese) |
| `SKILL.md` | OpenClaw skill definition — triggers (`/spec-pro`, `/solution`, `/research-pro`) |
| `CHANGELOG.md` | Version history — current v0.4.0 (2026-06-05) |
| `CONTRACTS.md` | Contract system specification — defines format and lifecycle of all contracts |
| `QUICKSTART.md` | 5-minute quickstart guide for new users |
| `QUALITY_GUIDE.md` | Quality standards applicable to all domains |
| `__init__.py` | Package init |
| `pyproject.toml` | Python project configuration |
| `pytest.ini` | Pytest configuration |
| `.gitignore` | Git ignore rules (blackboard/, __pycache__, .DS_Store, node_modules, etc.) |

---

## Domain Collaboration Flow

```
User describes requirements
    ↓
┌─────────────────┐
│   Spec Pro      │  Socratic dialog → Living Spec
│   (domains/     │
│    spec_pro/)   │
└────────┬────────┘
         ↓ Living Spec handoff
┌─────────────────┐
│  Solution Pro   │  10-stage pipeline → final_solution.md
│  (domains/      │
│   solution/)    │
└────────┬────────┘
         ↓ final_result.json
┌─────────────────┐
│   Ship Pro      │  Architect→Decomposer→Specifier→Reviewer→Packager
│  (domains/      │  → ship_package.json
│   ship_pro/)    │
└────────┬────────┘
         ↓ ship_package.json
┌─────────────────┐
│  Super Loop     │  Ship Package → Code execution (Phase 2, planning)
│  (super_loop/)  │
└─────────────────┘
```

---

## Architecture Principles

1. **Domains are self-contained**: Each domain has its own code, prompts, config, and tests
2. **Core is pure infrastructure**: No business logic in `core/`
3. **Contracts are layered**: Global contracts (`contracts/`) vs. scene contracts (`cage/active/`)
4. **Domains communicate via Blackboard**: No direct cross-domain imports
5. **Root is clean**: Only approved files at the top level (no stray `.py`/`.sh`/`.yaml`)
6. **Runtime data is gitignored**: `blackboard/` and `logs/` are not in version control

---

*Generated from actual file tree on 2026-06-22. See `contracts/directory_structure.md` for the normative directory structure contract (v3.1.0).*