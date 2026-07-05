# DeepFlow Frontend UI — Architecture Design Document
# Version: 1.0
# Date: 2026-05-07
# Status: Based on Requirements v1.2

---

## 1. Executive Summary

**Project**: DeepFlow Frontend UI  
**Goal**: A browser-based user interface that simplifies task submission, visualizes analysis progress, and presents final Markdown reports for the DeepFlow multi-agent analysis system.  
**Target Users**: Technical developers, product managers, and investors — mixed technical proficiency.  
**Deployment**: Local-only, single-user, browser access via `http://localhost:8000`.  

The frontend serves as the UI layer ONLY. OpenClaw remains the core execution engine. All LLM operations, agent orchestration, and blackboard access flow through the FastAPI backend. The frontend never calls LLM APIs directly.

**Key Design Principles**:
- Simplicity for non-technical users; advanced options for power users
- Stage-level progress visibility (not worker-level)
- Display-only quality gates (no override)
- Single-task-at-a-time workflow
- Google Material Design visual language

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ LandingPage │  │ TaskForm    │  │ Progress    │  │ ReportViewer        │  │
│  │             │  │             │  │ Monitor     │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                │                    │            │
│         └────────────────┴────────────────┴────────────────────┘            │
│                                   │                                         │
│                              React 18 + TS                                  │
│                                   │                                         │
│                         HTTP REST (localhost)                               │
│                                   │                                         │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FASTAPI BACKEND (localhost:8000)                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Task Router     │  │ Status Router   │  │ Report Router               │  │
│  │ POST /api/tasks │  │ GET /api/status │  │ GET /api/reports            │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────────────────┘  │
│           │                    │                    │                       │
│           └────────────────────┴────────────────────┘                       │
│                              DeepFlow Python                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PipelineOrchestrator → Workers → Blackboard → JSON / Markdown      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                         OpenClaw CLI                                        │
│                    (sessions_spawn, NOT exec)                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Integration Chain

```
Browser ──HTTP──► FastAPI ──Python import──► DeepFlow ──CLI──► OpenClaw
   │                │                           │                    │
   │                │                           │                    │
   │◄──JSON─────────┘◄──File polling──────────┘◄──Blackboard───────┘
```

**Critical Constraint**: OpenClaw `sessions_spawn` CANNOT be imported in exec/subprocess environments. FastAPI runs in the main Python process, calling OpenClaw via direct Python import (not CLI exec). This is the ONLY valid integration path.

---

## 3. Technology Stack

### 3.1 Frontend

| Technology | Version | Purpose | Justification |
|:---|:---|:---|:---|
| React | 18.x | UI framework | Component model, hooks, mature ecosystem |
| TypeScript | 5.x | Type safety | Catch errors at compile time, IDE support |
| Tailwind CSS | 3.x | Styling | Utility-first, rapid development, consistent spacing |
| Vite | 5.x | Build tool | Fast HMR, optimized production builds |
| React Router | 6.x | Client routing | Landing → Form → Progress → Report navigation |
| Axios | 1.x | HTTP client | Request/response interceptors, error handling |

### 3.2 Backend

| Technology | Version | Purpose | Justification |
|:---|:---|:---|:---|
| FastAPI | 0.110+ | API framework | Async support, automatic OpenAPI docs, Python-native |
| Uvicorn | 0.27+ | ASGI server | Production-grade, supports HTTP/2 |
| Pydantic | 2.x | Data validation | Request/response models, type safety |
| Python | 3.10+ | Runtime | Required for DeepFlow integration |

### 3.3 Desktop & Communication

| Aspect | Decision | Justification |
|:---|:---|:---|
| Desktop Runtime | Browser-based (NOT Electron/Tauri) | Zero extra dependency, users already have Chrome/Safari |
| Access URL | `http://localhost:8000` | Local-only, no network exposure |
| Protocol | HTTP REST API | Simple, debuggable, no WebSocket complexity |
| Progress Updates | File-system polling (3-5s interval) | Backend writes JSON progress file; frontend polls `GET /api/status` |
| Data Storage | JSON files in `blackboard/` directory | No database dependency, survives restart |

### 3.4 UI Framework Style

- **Design System**: Google Material Design 3 (M3)
- **Color**: Light mode only; primary `#1A73E8`; white backgrounds; card-based elevation
- **Typography**: Roboto / Noto Sans; 14px base; Chinese-optimized line-height
- **Spacing**: 8px grid system; 4px micro-grid for fine adjustments
- **Icons**: Material Symbols (Google) — filled variant for actions, outlined for navigation

---

## 4. Component Design

### 4.1 Component Hierarchy

```
App
├── Layout (persistent shell)
│   ├── AppBar (logo, language switch, settings icon)
│   └── Snackbar (global notifications)
├── Routes
│   ├── /  → LandingPage
│   │   ├── HeroSection
│   │   ├── QuickStartCard (SMIC example)
│   │   └── RecentSessionsList
│   ├── /domain-select  → DomainSelector
│   │   └── DomainCard[] (Investment, Solution, ...)
│   ├── /task/:domain  → TaskForm
│   │   ├── DynamicForm (domain-specific fields)
│   │   ├── ValidationPanel
│   │   └── SubmitButton (disabled until valid)
│   ├── /progress/:session_id  → ProgressMonitor
│   │   ├── StageTimeline
│   │   ├── QualityScoreCard
│   │   └── EstimatedTimeBadge
│   ├── /report/:session_id  → ReportViewer
│   │   ├── MarkdownRenderer
│   │   └── ActionBar (copy, new task, history)
│   └── /history  → SessionHistory
│       ├── FilterBar (domain, date)
│       └── SessionCard[]
└── ErrorBoundary (fallback for React errors)
```

### 4.2 Key Components Detail

#### LandingPage
- **Props**: `recentSessions: SessionSummary[]`
- **State**: `selectedTemplate: string | null`
- **Behavior**: 
  - On mount: fetch `/api/sessions` for recent list
  - Quick-start: pre-fill TaskForm with SMIC example
  - Navigation: click domain card → `/domain-select`

#### DomainSelector
- **Props**: `availableDomains: DomainMeta[]`
- **State**: `hoveredDomain: string | null`
- **Behavior**:
  - Renders cards with icon + description per domain
  - Click → navigate to `/task/:domain_id`
  - Domains discovered dynamically from backend (`GET /api/domains`)

#### TaskForm
- **Props**: `domainId: string`, `initialData?: TaskPayload`
- **State**: `formData: Record<string, any>`, `validationErrors: string[]`, `isSubmitting: boolean`
- **Behavior**:
  - Dynamic form fields based on domain schema from backend
  - Real-time validation for critical fields (e.g., stock ticker format)
  - On-submit validation for all fields
  - Submit → `POST /api/tasks` → navigate to `/progress/{session_id}`

#### ProgressMonitor
- **Props**: `sessionId: string`
- **State**: `stageData: StageInfo[]`, `currentStage: string`, `qualityScores: QualityScore | null`, `isPolling: boolean`
- **Behavior**:
  - Mount: start polling `/api/status/{session_id}` every 4s
  - Update: merge new stage data, animate stage transitions
  - Completion: detect `status === "completed"` → navigate to `/report/{session_id}`
  - Error: detect `status === "failed"` → show ErrorDisplay, stop polling
  - Unmount: stop polling (cleanup interval)

#### ReportViewer
- **Props**: `sessionId: string`
- **State**: `reportContent: string`, `isLoading: boolean`
- **Behavior**:
  - Mount: fetch `GET /api/reports/{session_id}`
  - Render: Markdown-to-HTML with syntax highlighting
  - Actions: copy to clipboard, start new analysis, view in history

#### SessionHistory
- **Props**: `sessions: SessionSummary[]`
- **State**: `filterDomain: string | null`, `filterDateRange: [Date, Date] | null`
- **Behavior**:
  - Fetch all sessions from `GET /api/sessions`
  - Filter by domain, date range
  - Click session → navigate to `/report/{session_id}`

---

## 5. Data Flow

### 5.1 Task Submission Flow

```
[User fills form] ──► [Frontend validates] ──► [POST /api/tasks]
                                                        │
                                                        ▼
                                              [FastAPI validates payload]
                                                        │
                                                        ▼
                                              [DeepFlow creates session]
                                                        │
                                                        ▼
                                              [Return {session_id, status: "started"}]
                                                        │
                                                        ▼
[Navigate to /progress/{id}] ◄── [Frontend receives 200] ◄──┘
```

### 5.2 Progress Polling Flow

```
[ProgressMonitor mounts] ──► [setInterval 4000ms]
                                    │
                                    ▼ (every 4s)
                         [GET /api/status/{session_id}]
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                    [status: running]      [status: completed]
                         │                     │
                         ▼                     ▼
                   [update StageTimeline]  [stop polling]
                   [update QualityScore]     [navigate /report/{id}]
                         │
                         ▼
                    [status: failed]
                         │
                         ▼
                   [stop polling]
                   [show ErrorDisplay]
```

**Polling Rules**:
- Interval: 4 seconds (within 3-5s requirement)
- Stop conditions: `status === "completed"`, `status === "failed"`, component unmount
- No exponential backoff (local API, low latency)
- Polling continues across tab switches (setInterval in component)

### 5.3 Report Retrieval Flow

```
[ReportViewer mounts] ──► [GET /api/reports/{session_id}]
                                    │
                                    ▼
                         [FastAPI reads blackboard/{id}/report.md]
                                    │
                                    ▼
                         [Return Markdown string]
                                    │
                                    ▼
                         [Frontend: Markdown → HTML rendering]
                                    │
                                    ▼
                         [Display with syntax highlighting]
```

### 5.4 Error Handling Flow

```
[Any API call fails] ──► [Axios interceptor catches]
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              [Network]    [4xx]       [5xx]
                    │           │           │
                    ▼           ▼           ▼
              [Retry once]  [Show error  [Show error
               then fail]    message]     message]
                                │           │
                                └───────────┘
                                            │
                                            ▼
                                    [Log to console]
                                    [Show in Snackbar]
                                    [NO auto-retry]
                                    [NO recovery action]
```

**Frontend Error Philosophy**: Display only. The Solution Pro engine (Harness + PipelineOrchestrator) owns retry and recovery decisions. The frontend shows status; it does not decide it.

---

## 6. API Specification

### 6.1 Endpoint Summary

| Method | Endpoint | Description | Request | Response |
|:---|:---|:---|:---|:---|
| GET | `/api/domains` | List available domains | — | `DomainMeta[]` |
| POST | `/api/tasks` | Submit new analysis task | `TaskPayload` | `{session_id, status}` |
| GET | `/api/status/{session_id}` | Get current progress | — | `StatusResponse` |
| GET | `/api/reports/{session_id}` | Get final Markdown report | — | `string` (Markdown) |
| GET | `/api/sessions` | List all sessions | — | `SessionSummary[]` |
| POST | `/api/reports/{session_id}/export` | Export report (copy/send) | `{format, target?}` | `{success, message}` |

### 6.2 Detailed Schemas

#### GET /api/domains
```typescript
interface DomainMeta {
  id: string;              // "investment", "solution"
  name: string;            // "Investment Analysis"
  description: string;     // "Analyze stocks with multi-agent pipeline"
  icon: string;            // Material icon name
  input_schema: object;    // JSON Schema for form generation
}
```

#### POST /api/tasks
```typescript
interface TaskPayload {
  domain: string;          // Domain ID
  inputs: Record<string, any>;  // Domain-specific parameters
  // Example (Investment): { ticker: "SMIC", analysis_type: "value" }
  // Example (Solution):  { requirements_doc: "path/to/doc.md" }
}

interface TaskResponse {
  session_id: string;      // UUID for this analysis
  status: "started" | "queued" | "rejected";
  message?: string;        // Rejection reason if rejected
}
```

#### GET /api/status/{session_id}
```typescript
interface StageInfo {
  name: string;            // "Planning", "Analysis", "Review", "Synthesis"
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string;     // ISO timestamp
  completed_at?: string;   // ISO timestamp
  estimated_duration?: number;  // Seconds
}

interface QualityScore {
  completeness: number;    // 0.0 - 1.0
  necessity: number;       // 0.0 - 1.0
  target_alignment: number; // 0.0 - 1.0
  overall: number;         // 0.0 - 1.0
  warnings?: string[];     // Harness 2.0.0 warnings
}

interface StatusResponse {
  session_id: string;
  overall_status: "running" | "completed" | "failed" | "waiting";
  current_stage: string;
  stages: StageInfo[];
  quality?: QualityScore;
  started_at: string;
  estimated_completion?: string;
  error_message?: string;  // Only if status === "failed"
}
```

#### GET /api/reports/{session_id}
- **Response**: `text/markdown` content type
- **Body**: Raw Markdown string
- **Error 404**: Session not found or report not yet generated

#### GET /api/sessions
```typescript
interface SessionSummary {
  session_id: string;
  domain: string;
  status: "completed" | "failed" | "running";
  created_at: string;
  completed_at?: string;
  title?: string;          // Auto-generated from inputs
}

// Response: SessionSummary[]
```

#### POST /api/reports/{session_id}/export
```typescript
interface ExportRequest {
  format: "clipboard" | "feishu" | "file";
  target?: string;         // Feishu open_id if format="feishu"
}

interface ExportResponse {
  success: boolean;
  message: string;
}
```

### 6.3 Error Response Format

```typescript
interface ApiError {
  status_code: number;
  error_code: string;      // Machine-readable
  message: string;         // Human-readable
  details?: object;        // Additional context
}
```

---

## 7. UI/UX Specifications

### 7.1 Color Palette (Google Material Design)

| Token | Hex | Usage |
|:---|:---|:---|
| Primary | `#1A73E8` | Buttons, active states, links |
| On Primary | `#FFFFFF` | Text on primary buttons |
| Primary Container | `#D3E3FD` | Selected chips, light highlights |
| Surface | `#FFFFFF` | Cards, dialogs, form backgrounds |
| Background | `#F8F9FA` | Page background |
| On Surface | `#1F1F1F` | Primary text |
| On Surface Variant | `#5F6368` | Secondary text, descriptions |
| Outline | `#DADCE0` | Borders, dividers |
| Error | `#B3261E` | Error states, failed stages |
| Success | `#137333` | Completed stages, success messages |
| Warning | `#F9AB00` | Quality warnings, pending states |

### 7.2 Typography

| Scale | Font | Size | Weight | Line-Height | Usage |
|:---|:---|:---|:---|:---|:---|
| Display Large | Roboto/Noto Sans | 32px | 400 | 40px | Page titles |
| Headline Medium | Roboto/Noto Sans | 24px | 400 | 32px | Section headers |
| Title Large | Roboto/Noto Sans | 20px | 500 | 28px | Card titles |
| Body Large | Roboto/Noto Sans | 16px | 400 | 24px | Form labels, body |
| Body Medium | Roboto/Noto Sans | 14px | 400 | 20px | Default text |
| Label Medium | Roboto/Noto Sans | 12px | 500 | 16px | Buttons, chips |

### 7.3 Layout Grid & Spacing

- **Grid**: 12-column, 24px gutter, max-width 1200px (centered)
- **Spacing Scale**: 4px base unit
  - xs: 4px, sm: 8px, md: 16px, lg: 24px, xl: 32px, 2xl: 48px
- **Border Radius**: 8px (cards), 16px (dialogs), 4px (buttons), 50% (avatars)
- **Elevation**: 0dp (flat), 1dp (cards), 3dp (hovered cards), 6dp (dialogs)

### 7.4 Key Screens Description

#### Screen 1: Task Input (Landing + TaskForm)
- Welcome hero with DeepFlow logo
- Pre-filled SMIC example card ("Try analyzing SMIC with one click")
- Domain selection grid (Investment, Solution, future domains)
- Dynamic form with validation feedback
- Submit button: disabled until valid, loading state during submit

#### Screen 2: Progress Monitor
- Stage timeline (vertical or horizontal)
- Each stage: icon + name + status badge + duration
- Current stage: highlighted with pulse animation
- Quality score panel: 3 metrics + overall score (visible after Review stage)
- Estimated time remaining badge
- Warning panel: displays Harness warnings (non-blocking, informational)
- NO cancel button (per aligned decision)

#### Screen 3: Quality Dashboard (within Progress)
- Appears after Review stage completes
- Three score cards: Completeness, Necessity, Target Alignment
- Overall score: large display with color coding
- Warning list: expandable accordion with Harness messages
- Purely display — no user action required

#### Screen 4: Report Viewer
- Full-width Markdown rendering
- Syntax highlighting for code blocks
- Table styling with alternating row colors
- Action bar: Copy to clipboard, Start New Analysis, View History
- NO PDF export button (Markdown only per requirements)

---

## 8. State Management

### 8.1 Architecture

```
┌─────────────────────────────────────────┐
│           Global State (React Context)   │
│  ┌─────────────┐  ┌─────────────────────┐│
│  │ TaskState   │  │ SessionCache        ││
│  │ ─────────── │  │ ─────────────────── ││
│  │ currentId   │  │ sessions: Session[] ││
│  │ status      │  │ lastFetch: Date     ││
│  │ error       │  │ isLoading: boolean  ││
│  │ isSubmitting│  │                     ││
│  └─────────────┘  └─────────────────────┘│
│  ┌─────────────────────────────────────┐ │
│  │ UI State (React Context)            │ │
│  │ ─────────────────────────────────── │ │
│  │ language: "zh" | "en"              │ │
│  │ sidebarOpen: boolean               │ │
│  │ snackbar: { message, type, open }  │ │
│  └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      Local Component State (useState)   │
│  • Form input values                     │
│  • Validation errors                     │
│  • Polling interval ref                  │
│  • Markdown scroll position              │
│  • Filter selections                     │
└─────────────────────────────────────────┘
```

### 8.2 Current Task State

```typescript
interface TaskState {
  sessionId: string | null;
  domain: string | null;
  status: "idle" | "submitting" | "running" | "completed" | "failed";
  error: string | null;
  lastUpdated: Date;
}
```

- **Idle**: No active task, show LandingPage
- **Submitting**: POST /api/tasks in flight, show spinner
- **Running**: Polling active, show ProgressMonitor
- **Completed**: Report ready, show ReportViewer
- **Failed**: Error occurred, show ErrorDisplay

**State transitions are one-way**: idle → submitting → running → [completed | failed]. No return transitions. New task requires fresh state.

### 8.3 Polling Lifecycle

```typescript
// ProgressMonitor component
useEffect(() => {
  const poll = async () => {
    const data = await api.getStatus(sessionId);
    setStatus(data);
    
    if (data.overall_status === "completed") {
      stopPolling();
      navigate(`/report/${sessionId}`);
    } else if (data.overall_status === "failed") {
      stopPolling();
      // Remain on progress page, show error overlay
    }
  };
  
  const interval = setInterval(poll, 4000);
  poll(); // Immediate first call
  
  return () => clearInterval(interval); // Cleanup on unmount
}, [sessionId]);
```

### 8.4 Session History Cache

- **Storage**: In-memory React state + JSON file backend
- **Initial Load**: Fetch `GET /api/sessions` on app mount
- **Updates**: Invalidate and refetch after task completion
- **No offline cache**: Browser refresh fetches fresh list from backend
- **Session data lives in**: `blackboard/sessions_index.json`

---

## 9. Error Handling Strategy

### 9.1 Philosophy

**Frontend displays; engine decides.** The frontend shows error status but NEVER initiates retry, recovery, or cancellation. All recovery logic lives in Solution Pro's Harness and PipelineOrchestrator.

### 9.2 Error Types & Display

| Error Source | Frontend Action | User Sees |
|:---|:---|:---|
| Network failure (fetch) | Show Snackbar, allow retry | "Connection failed. Please check your network." |
| API 4xx (validation) | Highlight invalid fields | Field-level error messages |
| API 5xx (server) | Show Snackbar, log to console | "Server error. Please try again later." |
| Task failure (engine) | Stop polling, show error panel | "Analysis failed: {message}" |
| OpenClaw not running | Block task submission | "DeepFlow engine not available. Please start OpenClaw." |
| Task already running | Block submission | "Another analysis is in progress. Please wait." |

### 9.3 What the Frontend DOES NOT Do

| Action | Rationale |
|:---|:---|
| No retry button | Solution Pro engine handles retry logic |
| No log viewer | Logs are backend concern; frontend is UI layer |
| No auto-retry | Could interfere with engine's retry strategy |
| No cancellation | Pipeline state is complex; cancellation at arbitrary point risks inconsistency |
| No error recovery | Recovery decisions require engine context |

---

## 10. Security Considerations

### 10.1 Credentials Protection

| Asset | Location | Frontend Access |
|:---|:---|:---|
| API keys (OpenAI, etc.) | `credentials.yaml` | ❌ NEVER — backend only |
| Feishu tokens | `credentials.yaml` | ❌ NEVER — backend only |
| OpenClaw config | `openclaw.json` | ❌ NEVER — backend only |
| Session metadata | `blackboard/*.json` | ✅ Read-only via API |
| Reports | `blackboard/*.md` | ✅ Read-only via API |

### 10.2 CORS & Network

```python
# FastAPI CORS — local-only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 10.3 Local-Only Deployment

- No HTTPS in development (HTTP acceptable per aligned constraints)
- No authentication (single-user local use)
- No CSRF tokens needed (no cross-origin requests)
- Binding: `127.0.0.1:8000` only (reject external interfaces)

---

## 11. Implementation Roadmap

### Week 1: Foundation
- [ ] FastAPI project scaffold + health check endpoint
- [ ] React + Vite + Tailwind + TypeScript project scaffold
- [ ] Material Design theme tokens (colors, typography, spacing)
- [ ] API client layer (Axios + interceptors)
- [ ] React Router setup with route definitions

### Week 2: Core UI Shell
- [ ] Layout component (AppBar, main content area)
- [ ] LandingPage with hero + quick-start card
- [ ] DomainSelector with dynamic domain discovery
- [ ] SessionHistory list view
- [ ] Snackbar + error display components

### Week 3: Task Submission
- [ ] TaskForm with dynamic field rendering from JSON Schema
- [ ] Form validation (real-time + on-submit)
- [ ] Task submission API integration
- [ ] SMIC pre-filled example
- [ ] OpenClaw status detection (block if not running)

### Week 4: Progress & Quality
- [ ] ProgressMonitor with stage timeline
- [ ] Polling implementation (4s interval, lifecycle management)
- [ ] QualityScoreCard (3 metrics + overall)
- [ ] Warning panel for Harness alerts
- [ ] Stage transition animations

### Week 5: Reports & Polish
- [ ] Markdown renderer with syntax highlighting
- [ ] ReportViewer with action bar
- [ ] Export integration (clipboard, Feishu via backend)
- [ ] Chinese/English language switch
- [ ] Loading states + skeleton screens

### Week 6: Testing & Hardening
- [ ] End-to-end test: full workflow (SMIC example)
- [ ] Error scenario tests (network failure, API error, engine crash)
- [ ] Chrome + Safari compatibility verification
- [ ] Performance: polling efficiency, render optimization
- [ ] Documentation: user guide + developer setup

---

## 12. Risk Analysis

### 12.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|:---|:---:|:---:|:---|
| OpenClaw CLI interface changes | Medium | High | Abstract OpenClaw calls behind adapter layer; version detection |
| FastAPI + OpenClaw single-process conflicts | Medium | High | Run FastAPI in separate thread; use async subprocess for CLI |
| Markdown rendering inconsistencies | Low | Medium | Use battle-tested library (react-markdown + remark-gfm) |
| JSON schema forms become complex | Medium | Medium | Limit schema complexity; custom renderers for common types |
| Browser compatibility edge cases | Low | Low | Test on Chrome + Safari; graceful degradation |
| File polling performance at scale | Low | Low | Poll backend API (not files directly); backend handles file reads |

### 12.2 Integration Risks

| Risk | Likelihood | Impact | Mitigation |
|:---|:---:|:---:|:---|
| `sessions_spawn` import fails in FastAPI | High | Critical | Verify FastAPI runs in main process (not exec); test on startup |
| Blackboard directory structure changes | Medium | High | Backend abstracts blackboard access; frontend never reads directly |
| Session ID format changes | Low | Medium | Treat session_id as opaque string; no parsing |
| Quality score schema changes | Medium | Medium | Version API responses; handle missing fields gracefully |

### 12.3 Dependency Risks

| Dependency | Risk | Mitigation |
|:---|:---|:---|
| OpenClaw ≥ 2026.4.x | Mandatory; older versions fail | Detect version on startup; show upgrade message |
| Python 3.10+ | DeepFlow requirement | Document in setup guide; validate on startup |
| Node.js 18+ | Build requirement | Document in setup guide |

---

## Appendix A: File Structure

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── main.tsx                 # Entry point
│   ├── App.tsx                  # Root component + routing
│   ├── api/
│   │   ├── client.ts            # Axios instance + interceptors
│   │   ├── domains.ts           # Domain API
│   │   ├── tasks.ts             # Task API
│   │   ├── status.ts            # Status API
│   │   ├── reports.ts           # Report API
│   │   └── sessions.ts          # Session API
│   ├── components/
│   │   ├── Layout.tsx           # App shell
│   │   ├── AppBar.tsx           # Top navigation
│   │   ├── Snackbar.tsx         # Global notifications
│   │   ├── ErrorBoundary.tsx    # React error fallback
│   │   ├── StageTimeline.tsx    # Progress visualization
│   │   ├── QualityScoreCard.tsx # Quality metrics display
│   │   ├── MarkdownRenderer.tsx # Markdown → HTML
│   │   └── LoadingSkeleton.tsx  # Skeleton screens
│   ├── pages/
│   │   ├── LandingPage.tsx
│   │   ├── DomainSelector.tsx
│   │   ├── TaskForm.tsx
│   │   ├── ProgressMonitor.tsx
│   │   ├── ReportViewer.tsx
│   │   └── SessionHistory.tsx
│   ├── hooks/
│   │   ├── usePolling.ts        # Generic polling hook
│   │   ├── useTaskState.ts      # Task state management
│   │   └── useSessions.ts       # Session cache management
│   ├── context/
│   │   ├── TaskContext.tsx      # Global task state
│   │   └── UIContext.tsx        # UI state (language, theme)
│   ├── types/
│   │   └── api.ts               # TypeScript interfaces
│   ├── theme/
│   │   ├── colors.ts            # Material Design tokens
│   │   ├── typography.ts        # Font styles
│   │   └── spacing.ts           # 8px grid
│   └── utils/
│       └── validation.ts        # Form validators
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── tsconfig.json

backend/
├── main.py                      # FastAPI app + lifespan
├── routers/
│   ├── domains.py               # GET /api/domains
│   ├── tasks.py                 # POST /api/tasks
│   ├── status.py                # GET /api/status
│   ├── reports.py               # GET /api/reports
│   ├── sessions.py              # GET /api/sessions
│   └── export.py                # POST /api/reports/{id}/export
├── models/
│   └── schemas.py               # Pydantic models
├── services/
│   ├── task_service.py          # Task submission logic
│   ├── status_service.py        # Progress reading (blackboard polling)
│   ├── report_service.py        # Report retrieval
│   └── session_service.py       # Session index management
├── config.py                    # Backend configuration
└── requirements.txt
```

## Appendix B: Technology Versions

| Component | Version | Lock Date |
|:---|:---|:---|
| React | 18.2.0 | 2026-05 |
| TypeScript | 5.4.0 | 2026-05 |
| Tailwind CSS | 3.4.0 | 2026-05 |
| Vite | 5.2.0 | 2026-05 |
| FastAPI | 0.110.0 | 2026-05 |
| Uvicorn | 0.27.0 | 2026-05 |
| Pydantic | 2.6.0 | 2026-05 |
| Python | 3.10+ | 2026-05 |

---

*End of Document*
