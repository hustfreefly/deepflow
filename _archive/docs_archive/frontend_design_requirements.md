# DeepFlow Frontend UI - Requirements & Constraints

## Project
**Name**: DeepFlow Frontend UI Design
**Type**: architecture
**Goal**: Design a user-friendly frontend interface for DeepFlow that simplifies task input, visualizes analysis progress, displays Harness quality controls, and presents final results.

## Context
DeepFlow is an extensible multi-agent pipeline framework running on OpenClaw. Currently, users interact with DeepFlow via command line (python3 deepflow.py --code ...), which is not user-friendly for non-technical users.

## Requirements

### Must Have (P0)
1. **Task Input Interface**: User-friendly form to input task requirements (domain selection, parameters, constraints)
2. **Real-time Progress Visualization**: Show pipeline execution progress (10 stages: Data Collection → Planning → Reviewers → Research → Consolidator → Audit → Fix → Harness Final → Summarizer)
3. **Quality Control Dashboard**: Display Harness V2 scores (Completeness / Necessity / Target Alignment) and allow intervention
4. **Result Presentation**: Render final analysis reports (markdown) with export options (PDF, Feishu)
5. **Session Management**: List historical sessions, resume/review past analyses

### Should Have (P1)
6. **Multi-domain Support**: Switch between Investment Analysis, Solution Design, and future domains
7. **Configuration Management**: Edit search_config.yaml, credentials.yaml via UI
8. **Notification System**: Alert when analysis completes or quality gate fails

### Nice to Have (P2)
9. **Collaborative Features**: Share sessions, comments, annotations
10. **Analytics Dashboard**: Usage statistics, average quality scores, pipeline performance

## Constraints (Hard Rules)

### C1: OpenClaw Dependency (Non-negotiable)
- Frontend is a UI layer ONLY. OpenClaw remains the core engine.
- Frontend CANNOT directly spawn agents or call LLM APIs.
- All agent execution must go through OpenClaw's sessions_spawn.
- Architecture: Frontend ↔ DeepFlow Backend ↔ OpenClaw

### C2: Real-time Progress (Challenge)
- OpenClaw does not provide WebSocket or streaming status API.
- Must use file-system polling or HTTP polling to get progress updates.
- Target latency: < 3 seconds between stage transitions.

### C3: Session Isolation
- Multiple users may use the frontend simultaneously.
- Each session must be isolated (separate blackboard directory).
- Session ID format: {prefix}_{type}_{hash8}, max 50 chars.

### C4: Platform Compatibility
- Must run on macOS (primary), Windows, Linux.
- DeepFlow already uses PathConfig for cross-platform paths.
- Frontend must respect PathConfig path resolution.

### C5: Security
- credentials.yaml contains API keys (Tushare, Feishu, etc).
- Frontend must NOT expose credentials in browser/dev tools.
- Access control: local-only or authenticated (if web deployment).

### C6: Performance
- Analysis pipeline takes 5-30 minutes.
- Frontend must handle long-running tasks without timeout.
- Progress updates should not block pipeline execution.

## Technical Environment
- **Backend**: Python 3.10+, existing DeepFlow codebase
- **Agent Platform**: OpenClaw (sessions_spawn / sessions_yield)
- **Current UI**: None (CLI only)
- **Target Platforms**: Desktop app (primary), optionally web

## Deliverables Expected
1. **Architecture Design Document**: Frontend-Backend-OpenClaw integration architecture
2. **Technology Stack Recommendation**: React/Vue/Electron/Tauri/etc with justification
3. **Data Flow Design**: How frontend gets real-time progress without WebSocket
4. **API Specification**: Interface between Frontend and DeepFlow Backend
5. **UI/UX Wireframes**: Key screens (Task Input, Progress, Quality Dashboard, Report Viewer)
6. **Implementation Roadmap**: Phased approach with effort estimates
7. **Risk Analysis**: Technical risks and mitigation strategies

## Success Criteria
- Non-technical user can submit an analysis task in < 1 minute
- User can understand pipeline progress at a glance
- Quality gate failures are visible and actionable
- Final report is readable and exportable
- Frontend does not compromise OpenClaw's agent scheduling capability

## Reference Documents
- docs/ARCHITECTURE.md - DeepFlow three-layer architecture
- docs/SOLUTION_PRO_MODE_DESIGN.md - Solution Pro 10-stage pipeline
- docs/harness_architecture_v2_final.md - Harness V2 quality gates
- core/entry_harness.py - EntryHarness implementation
- core/pipeline_orchestrator.py - PipelineOrchestrator implementation

## Session Prefix
frontend-ui-design
