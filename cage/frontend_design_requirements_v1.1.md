# DeepFlow Frontend UI - Aligned Requirements & Constraints
# Version: 1.1 (Aligned with user input)
# Date: 2026-05-06

## 1. Project Definition

**Name**: DeepFlow Frontend UI
**Type**: architecture
**Goal**: A user-friendly browser-based interface for DeepFlow that simplifies task submission, visualizes analysis progress, and presents final Markdown reports.

## 2. User Profile (Aligned)

**Target Users**: Mixed
- Technical developers (can handle CLI but prefer UI)
- Product managers (non-technical, need GUI)
- Investors (non-technical, need simple interface)

**Implication**: UI must be intuitive for non-technical users while providing advanced options for technical users.

## 3. Deployment Model (Aligned)

**Environment**: Personal computer, local-only
**Access Method**: Browser access (http://localhost:PORT)
**Not**: Desktop app, SaaS, or public web deployment

**Architecture**:
```
Browser (User) → HTTP → FastAPI (localhost) → DeepFlow Python → OpenClaw CLI
```

## 4. Real-Time Requirements (Aligned)

**Requirement**: "Can see progress is enough"
**Latency Target**: Stage-level updates (not worker-level granularity)
**Polling Interval**: 3-5 seconds acceptable
**Not Required**: Sub-second updates, worker-level progress tracking

## 5. Quality Gate Interaction (Aligned)

**Frontend Role**: Display-only
**Decision Authority**: Solution Pro engine (Harness V2)
**User Actions Available**:
- View Harness scores (Completeness / Necessity / Target Alignment)
- View quality gate warnings
- Acknowledge gate results (but not override engine decisions)

**Not in Scope**: Manual quality score adjustment, force-skip gates

## 6. Report Format (Aligned)

**Primary Format**: Markdown rendering
**Features**: 
- Markdown-to-HTML rendering with syntax highlighting
- Basic tables and lists
- Code block formatting
**Not in Scope**: PDF export, charts/visualizations, PPT-style reports, interactive widgets

## 7. Extensibility (Aligned)

**Plugin System**: NO
**Domain Extension**: Driven by DeepFlow backend module development only
**Frontend Behavior**: Automatically discovers available domains from backend
**New Domain Addition**: Requires DeepFlow backend code changes, not frontend configuration

## 8. Multi-User & Concurrency (Aligned)

**Scope**: Single user, single task at a time
**Session Model**: One active analysis session per user
**Not in Scope**: 
- Multiple simultaneous tasks
- User authentication
- Session sharing
- Collaborative features

## 9. User Flow & Experience Design (To Be Determined)

### 9.1 Primary User Journey

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

### 9.2 Key UX Decisions Needed

| Screen | Purpose | Open Questions |
|:---|:---|:---|
| Landing | Welcome + quick actions | Show recent sessions? Quick-start templates? |
| Domain Select | Choose analysis type | How to present domain options? Icons + description? |
| Parameter Form | Input task parameters | Auto-complete? Validation real-time or on-submit? |
| Progress | Monitor running analysis | Show stage list or pipeline visualization? |
| Quality Alert | Display Harness warnings | Modal or inline notification? |
| Report | Read final output | Side navigation for report sections? |
| History | List past analyses | Search/filter? Group by domain? |

## 10. OpenClaw Integration Feasibility

### 10.1 Integration Chain

```
┌─────────────┐     HTTP      ┌─────────────┐     Python    ┌─────────────┐
│   Browser   │◄─────────────►│  FastAPI    │◄────────────►│   DeepFlow   │
│  (Frontend) │   localhost   │   Server    │   function   │   Backend    │
└─────────────┘               └─────────────┘              └──────┬──────┘
                                                                     │
                                                                     │ subprocess
                                                                     │ (CLI call)
                                                                     ▼
                                                              ┌─────────────┐
                                                              │   OpenClaw   │
                                                              │   (CLI)      │
                                                              └─────────────┘
```

### 10.2 Feasibility Assessment

| Integration Point | Feasibility | Risk | Mitigation |
|:---|:---:|:---:|:---|
| Browser → FastAPI | ✅ High | CORS | Allow localhost origins |
| FastAPI → DeepFlow | ✅ High | None | Direct Python import |
| DeepFlow → OpenClaw | ⚠️ Medium | exec environment limits | Use subprocess call with proper env |
| Progress feedback | ✅ High | File polling latency | 3-5s interval acceptable per requirements |
| Report retrieval | ✅ High | File read permissions | Serve from allowed directory |

### 10.3 Critical Technical Constraint

**OpenClaw sessions_spawn cannot be imported in exec environment.**
**Solution**: FastAPI server runs in the main Python process (not exec), where OpenClaw SDK is available if properly configured.

Alternative if SDK unavailable:
```python
# FastAPI route
@app.post("/api/tasks")
def create_task(params):
    # Option A: Direct Python call (if SDK available)
    result = deepflow_entry_harness.run(params)
    
    # Option B: CLI subprocess call (fallback)
    result = subprocess.run([
        "openclaw", "agent", "run", 
        "--task", json.dumps(params)
    ], capture_output=True)
```

## 11. Success Criteria (Aligned)

| # | Criterion | Measurement |
|:---:|:---|:---|
| 1 | Non-technical user submits task in < 2 minutes | User testing |
| 2 | Progress visible at stage level | Automated test |
| 3 | Quality gate scores displayed | Visual verification |
| 4 | Markdown report readable | User testing |
| 5 | Single-task workflow complete without errors | End-to-end test |
| 6 | Browser-based access works on macOS/Windows/Linux | Cross-platform test |

## 12. Out of Scope (Explicitly Excluded)

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

## 13. Next Steps

1. ✅ Requirements aligned (this document)
2. ⬜ User flow wireframes confirmation
3. ⬜ Technical feasibility validation (POC)
4. ⬜ Solution Pro design phase启动

---

*Aligned with user input on 2026-05-06*
