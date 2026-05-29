# DeepFlow Frontend UI - Requirements & Constraints (v1.2 Aligned)
# Version: 1.2
# Date: 2026-05-06
# Status: Aligned with user input, pending final confirmation

## 1. Project Definition

**Name**: DeepFlow Frontend UI
**Type**: architecture
**Goal**: A browser-based user interface for DeepFlow that simplifies task submission, visualizes analysis progress, and presents final Markdown reports.

## 2. User Profile (ALIGNED ✅)

**Target Users**: Mixed
- Technical developers (power users, need advanced options)
- Product managers (non-technical, need intuitive UI)
- Investors (non-technical, need simple workflow)

**Implication**: UI must be intuitive for non-technical users while providing advanced options for technical users.

## 3. Deployment Model (ALIGNED ✅)

**Environment**: Personal computer, local-only
**Access Method**: Browser access (http://localhost:PORT)
**Not**: Desktop app, SaaS, or public web deployment

**Architecture**:
```
Browser (User) → HTTP → FastAPI (localhost) → DeepFlow Python → OpenClaw CLI
```

## 4. Real-Time Requirements (ALIGNED ✅)

**Requirement**: "Can see progress is enough"
**Latency Target**: Stage-level updates (not worker-level granularity)
**Polling Interval**: 3-5 seconds acceptable
**Not Required**: Sub-second updates, worker-level progress tracking

## 5. Quality Gate Interaction (ALIGNED ✅)

**Frontend Role**: Display-only
**Decision Authority**: Solution Pro engine (Harness V2)
**User Actions Available**:
- View Harness scores (Completeness / Necessity / Target Alignment)
- View quality gate warnings
- Acknowledge gate results (but not override engine decisions)

**Not in Scope**: Manual quality score adjustment, force-skip gates

## 6. Report Format (ALIGNED ✅)

**Primary Format**: Markdown rendering
**Features**: 
- Markdown-to-HTML rendering with syntax highlighting
- Basic tables and lists
- Code block formatting
**Not in Scope**: PDF export, charts/visualizations, PPT-style reports, interactive widgets

## 7. Extensibility (ALIGNED ✅)

**Plugin System**: NO
**Domain Extension**: Driven by DeepFlow backend module development only
**Frontend Behavior**: Automatically discovers available domains from backend
**New Domain Addition**: Requires DeepFlow backend code changes, not frontend configuration

## 8. Multi-User & Concurrency (ALIGNED ✅)

**Scope**: Single user, single task at a time
**Session Model**: One active analysis session per user
**Not in Scope**: 
- Multiple simultaneous tasks
- User authentication
- Session sharing
- Collaborative features

## 9. Platform Constraints from DeepFlow (ALIGNED ✅)

### C1: Architecture Red Line
- Frontend is UI layer ONLY, OpenClaw is the core engine
- Frontend CANNOT directly call LLM API (must go through OpenClaw)
- Frontend CANNOT directly operate Blackboard (must go through backend API)

### C2: Security Constraints
- credentials.yaml CANNOT be exposed to browser
- API keys CANNOT appear in browser Network panel
- Local development: HTTP acceptable; Production: HTTPS required

### C3: Platform Dependency
- OpenClaw ≥ 2026.4.x is MANDATORY
- Frontend MUST detect OpenClaw status before task submission
- If OpenClaw not running: show "dependency missing" message, not crash

### C4: Execution Mode
- Frontend task submission → Backend FastAPI → Main process calls OpenClaw
- FORBIDDEN: exec environment calling sessions_spawn
- FORBIDDEN: subprocess bypassing OpenClaw to directly call LLM

### C5: File Sending Rules (from TOOLS.md)
- PDF < 20MB: direct send; ≥ 20MB: compress first
- HTML: send to email 81240779@qq.com
- MD: create Feishu document

## 10. User Flow & Experience Design (ALIGNED ✅)

### 10.1 Primary User Journey

```
[1. Landing Page]
    ↓
[2. Domain Selection] (Investment / Solution / future domains)
    ↓
[3. Parameter Input] (Dynamic form based on domain)
    ↓
[4. Task Submission] (Validate → Submit → Start)
    ↓
[5. Progress Monitor] (Pipeline stages, quality scores)
    ↓
[6. Report Viewer] (Markdown report)
    ↓
[7. Session History] (Past analyses list)
```

### 10.2 Key Screens

| Screen | Purpose | User Actions |
|:---|:---|:---|
| Landing | Welcome + quick actions | View recent sessions, quick-start templates |
| Domain Select | Choose analysis type | Click domain card with icon + description |
| Parameter Form | Input task parameters | Fill dynamic form with validation |
| Confirmation | Review before start | View summary, click "Start Analysis" |
| Progress | Monitor running analysis | View stage list, estimated time, quality scores |
| Quality Alert | Display Harness warnings | Acknowledge warnings (display only) |
| Report | Read final output | Read markdown, copy content, start new task |
| History | List past analyses | View past sessions, search, filter by domain |

## 11. OpenClaw Integration Feasibility (CONFIRMED ✅)

### 11.1 Integration Chain

```
Browser → FastAPI (localhost:8000) → DeepFlow Python → OpenClaw CLI
```

### 11.2 Feasibility

| Integration Point | Feasibility | Notes |
|:---|:---:|:---|
| Browser → FastAPI | ✅ High | localhost, no CORS issues |
| FastAPI → DeepFlow | ✅ High | Direct Python import |
| DeepFlow → OpenClaw | ✅ High | CLI subprocess call |
| Progress feedback | ✅ High | File polling, 3-5s interval |
| Report retrieval | ✅ High | Serve from blackboard directory |

### 11.3 Critical Constraint

**OpenClaw sessions_spawn cannot be imported in exec environment.**
**Solution**: FastAPI runs in main process (not exec), calls OpenClaw via CLI.

## 12. Success Criteria (ALIGNED ✅)

| # | Criterion | Measurement |
|:---:|:---|:---|
| 1 | Non-technical user submits task in < 2 minutes | User testing |
| 2 | Progress visible at stage level | Automated test |
| 3 | Quality gate scores displayed | Visual verification |
| 4 | Markdown report readable | User testing |
| 5 | Single-task workflow complete without errors | End-to-end test |
| 6 | Browser-based access works on macOS/Windows/Linux | Cross-platform test |

## 13. Out of Scope (Explicitly Excluded)

| Feature | Reason |
|:---|:---|
| PDF/Excel export | Requirement #6: Markdown only |
| Plugin system | Requirement #7: Not supported |
| Multi-user auth | Requirement #8: Single user |
| Real-time collaboration | Requirement #8: Not needed |
| Worker-level progress | Requirement #4: Stage-level enough |
| Quality gate override | Requirement #5: Engine decides |
| Mobile responsive design | Local browser use, desktop primary |
| Offline mode | Requires OpenClaw online |

---

## 14. PENDING ALIGNMENT - Dimensions Not Yet Discussed

The following dimensions have NOT been explicitly aligned with the user. These should be confirmed before starting Solution Pro design phase.

### P1: Error Handling & Recovery
- [ ] **Question**: If a task fails (e.g., OpenClaw crash, LLM timeout), what should the frontend show?
- [ ] **Options**: 
  - A) Show error message + "Retry" button
  - B) Show error message + "View Logs" button
  - C) Show error message + auto-retry (with max attempts)
  - D) Show error only, user must restart manually

### P2: Task Cancellation
- [ ] **Question**: Can the user cancel a running analysis?
- [ ] **Options**:
  - A) Yes, with "Cancel" button (sends kill signal)
  - B) No, once started must wait for completion
  - C) Yes, but only before Stage 3 (Reviewers)

### P3: Session History Persistence
- [ ] **Question**: How are historical sessions stored?
- [ ] **Options**:
  - A) SQLite local database
  - B) JSON files in blackboard directory
  - C) In-memory only (lost on restart)
  - D) Browser localStorage

### P4: Configuration Management
- [ ] **Question**: Can users edit DeepFlow configuration via frontend?
- [ ] **Options**:
  - A) Full editing (search_config.yaml, credentials.yaml, output_config.yaml)
  - B) Read-only view (display current config)
  - C) Partial editing (only safe fields like session_prefix, output_channel)
  - D) No config view/editing at all

### P5: Task Queuing Behavior
- [ ] **Question**: If user submits a new task while one is running, what happens?
- [ ] **Options**:
  - A) Queue the new task (run after current completes)
  - B) Reject with "Task already running" message
  - C) Kill current task and start new one
  - D) Open new browser tab with separate session

### P6: Browser Compatibility
- [ ] **Question**: Which browsers must be supported?
- [ ] **Options**:
  - A) Chrome only (recommended for local dev)
  - B) Chrome + Safari (macOS primary)
  - C) Chrome + Safari + Firefox + Edge (full support)

### P7: Notification Mechanism
- [ ] **Question**: When analysis completes, how to notify user?
- [ ] **Options**:
  - A) Browser tab title flashing + sound
  - B) OS notification (macOS Notification Center / Windows Toast)
  - C) In-app toast message only
  - D) No notification (user must check manually)

### P8: Data Privacy & Retention
- [ ] **Question**: How long are analysis reports retained?
- [ ] **Options**:
  - A) Permanent (until user manually deletes)
  - B) 30 days auto-cleanup
  - C) Last 50 sessions only
  - D) No persistence (session lost on browser close)

### P9: Language & Localization
- [ ] **Question**: Frontend language?
- [ ] **Options**:
  - A) Chinese only (匹配当前用户)
  - B) English only (匹配 README/文档)
  - C) Auto-detect system language
  - D) Manual switch (Chinese/English)

### P10: Theme & Appearance
- [ ] **Question**: UI theme requirements?
- [ ] **Options**:
  - A) Dark mode only
  - B) Light mode only
  - C) Auto system theme
  - D) Manual toggle (Light/Dark)

### P11: Log Visibility
- [ ] **Question**: Can users view execution logs?
- [ ] **Options**:
  - A) Full logs (all Worker outputs, debug level)
  - B) Summary logs (stage transitions, errors only)
  - C) No logs (only progress bar)
  - D) Logs in separate "Advanced" tab

### P12: Report Sharing
- [ ] **Question**: Can users share reports outside the system?
- [ ] **Options**:
  - A) Export as .md file download
  - B) Copy to clipboard
  - C) Send to Feishu (existing backend capability)
  - D) Generate shareable link
  - E) No sharing (view only)

### P13: Input Validation Strategy
- [ ] **Question**: Form validation timing?
- [ ] **Options**:
  - A) Real-time validation (as user types)
  - B) On-blur validation (when field loses focus)
  - C) On-submit validation only
  - D) Combination (real-time for critical fields, on-submit for others)

### P14: First-Time User Experience
- [ ] **Question**: Onboarding for first-time users?
- [ ] **Options**:
  - A) Guided tour (step-by-step overlay)
  - B) Sample task pre-loaded ("Try analyzing SMIC")
  - C) Help documentation link
  - D) No onboarding (self-exploratory)

## 15. ALIGNED P1-P5 (Updated)

### P1: Error Handling (ALIGNED ✅)
**Decision**: Option D
- Frontend displays "Analysis Failed" message only
- No retry button, no log viewer, no auto-retry
- Retry decisions are made by Solution Pro engine (Harness / PipelineOrchestrator)
- Frontend responsibility: DISPLAY status only, not DECIDE recovery

### P2: Task Cancellation (ALIGNED ✅)
**Decision**: Option B — Cannot cancel
- Once analysis starts, user must wait for completion
- No "Cancel" button in progress UI
- Rationale: Solution Pro pipeline has complex state; cancellation at arbitrary point risks data inconsistency

### P3: Session History Persistence (ALIGNED ✅)
**Decision**: Option B — JSON files in blackboard directory
- Session metadata stored as JSON files alongside blackboard/{session_id}/
- Survives browser refresh and app restart
- Format: `blackboard/sessions_index.json` (array of session summaries)
- Each session: `blackboard/{session_id}/session_meta.json`
- Not using SQLite (additional dependency) or localStorage (size limit, not shared)

### P4: Configuration Management (ALIGNED ✅)
**Decision**: Tiered approach

**Phase 1 (Current Version) — Display Only**:
- Configurations visible but NOT editable
- Display: search_config.yaml, output_config.yaml (mask credentials)
- Read-only view with "Advanced Configuration" toggle (collapsed by default)

**Phase 2 (Future Version) — Limited Editing**:
- Key safe configurations editable via frontend
- Controlled by `editable_config: true` feature flag

**Key Safe Configurations (Editable in Phase 2)**:
| Config | Field | Safety | Frequency |
|:---|:---|:---:|:---:|
| output_config.yaml | output_channel (feishu/email/local) | High | High |
| output_config.yaml | session_prefix | High | High |
| search_config.yaml | search_depth (quick/standard/deep) | High | Medium |
| search_config.yaml | force_rebuild (true/false) | High | Low |

**Never Editable via Frontend**:
- credentials.yaml (all API keys, tokens)
- domains/*.yaml (Worker configurations, architecture-level)
- model_config (model selection, may break stability)

### P5: Task Queuing (ALIGNED ✅)
**Decision**: Single task only
- Only ONE task can run at a time
- If user tries to submit while task running: show "Task already running, please wait" message
- No queuing, no multi-tab support
- Rationale: Simplifies state management, avoids OpenClaw resource contention
- Future version may add queue support
