# DeepFlow 前端 API 契约

> **版本**: 1.0
> **日期**: 2026-05-16
> **原则**: 前端期望的字段,后端必须保证存在且类型一致

---

## 📋 契约列表

### API-001: 提交任务 (`POST /api/v2/tasks`)

| 字段 | 前端发送 | 后端返回 |
|:---|:---|:---|
| `session_id` | - | ✅ `string` |
| `status` | - | ✅ `string` (`queued`) |
| `domain` | ✅ `string` (`solution`/`investment`) | ✅ `string` |
| `created_at` | - | ✅ `string` (ISO) |
| `webhook_sent` | - | ✅ `boolean` |
| `webhook_retries` | - | ✅ `number` |

**Solution 参数**:
```json
{
  "domain": "solution",
  "topic": "string",
  "solution_type": "architecture|design|code",
  "constraints": ["string"],
  "stakeholders": ["string"],
  "session_prefix": "string"
}
```

**Investment 参数**:
```json
{
  "domain": "investment",
  "code": "string",
  "name": "string",
  "industry": "string",
  "analysis_depth": "value|growth|technical",
  "session_prefix": "string"
}
```

---

### API-002: 任务状态 (`GET /api/v2/status/{sessionId}`)

**前端期望字段**:

| 字段 | 类型 | 说明 | 来源 |
|:---|:---|:---|:---|
| `session_id` | `string` | 任务 ID | Blackboard |
| `status` | `string` | `pending/waiting/running/completed/failed` | Blackboard |
| `current_stage` | `string` | 当前阶段名 | 计算 |
| `progress` | `number` | 0.0-1.0 | 计算 |
| `stages` | `Stage[]` | 阶段列表 | Blackboard `phases` 映射 |
| `topic` | `string` | 任务主题 | Blackboard |
| `solution_type` | `string` | 方案类型 | Blackboard |

**Stage 对象**:
```typescript
interface Stage {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration: number
  workers?: { completed: number; total: number }
}
```

**Blackboard → 前端字段映射**:

| Blackboard 字段 | 前端字段 | 转换规则 |
|:---|:---|:---|
| `phases[]` | `stages[]` | `phase.stage → name`, `phase.status → status` |
| `current_phase` | - | 用于计算 `current_stage` |
| `status` | `status` | 直接映射 |
| - | `progress` | `completed_phases / total_phases` |

**Fallback 规则**:
- Blackboard 不存在 → 返回 SQLite 状态 + `current_stage: "waiting"`
- Blackboard 存在但无 phases → 返回空 stages 列表

---

### API-003: 任务报告 (`GET /api/v2/reports/{sessionId}`)

**前端期望字段**:

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `session_id` | `string` | 任务 ID |
| `content` | `string` | Markdown 内容 |
| `format` | `string` | `"markdown"` |
| `length` | `number` | 内容长度(字符数) |
| `source_file` | `string` | 来源文件名 |

**报告文件查找顺序**:
1. `report.md`
2. `final_solution.md`
3. `final_report.md`

**错误码**:
- `404`: `Report not yet generated`(任务存在但报告未生成)
- `404`: `Session not found`(任务不存在)

---

### API-004: 会话列表 (`GET /api/v2/sessions`)

**前端期望字段**：

| 字段 | 类型 | 说明 | 来源 |
|:---|:---|:---|:---|
| `session_id` | `string` | 任务 ID | SQLite |
| `domain` | `string` | 任务域 | SQLite |
| `status` | `string` | 状态 | SQLite |
| `created_at` | `number` | 创建时间（Unix 秒） | SQLite |
| `completed_at` | `number` | 完成时间 | SQLite |
| `progress` | `number` | 进度 0-1 | 计算 |
| `topic` | `string` | 任务主题 | SQLite `parameters.topic` |
| `code` | `string` | 股票代码 | SQLite `parameters.code` |
| `name` | `string` | 公司名称 | SQLite `parameters.name` |

**数据来源**：仅 SQLite（Blackboard 旧任务不显示在历史列表中）
**排序**: 按 `created_at` 降序

### API-005: 系统信息 (`GET /api/v2/system-info`)

**前端期望字段**：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `openclaw.status` | `string` | `connected` / `error` |
| `openclaw.version` | `string` | OpenClaw 版本号 |
| `backend.version` | `string` | API 版本 |
| `backend.host` | `string` | 后端地址 |
| `backend.port` | `number` | 后端端口 |
| `blackboard.path` | `string` | Blackboard 绝对路径 |
| `blackboard.session_count` | `number` | 任务总数 |
| `config.frontend_port` | `number` | 前端端口 |
| `config.backend_port` | `number` | 后端端口 |
| `config.webhook_url` | `string` | Webhook 地址 |

### API-006: 活跃任务 (`GET /api/v2/active-task`)

**前端期望字段**:

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `session_id` | `string` | 任务 ID |
| `domain` | `string` | 任务域 |
| `status` | `string` | 状态 |
| `topic` | `string` | 任务主题 |
| `code` | `string` | 股票代码 |
| `name` | `string` | 公司名称 |
| `created_at` | `number` | 创建时间 |
| `progress` | `number` | 进度 0-1(如有 Blackboard) |
| `current_stage` | `string` | 当前阶段(如有 Blackboard) |
| `stages` | `Stage[]` | 阶段列表(如有 Blackboard) |

**无活跃任务时**: 返回 `null`

**查询顺序**: `running` → `waiting_agent` → `pending`

---

### API-006: 健康检查 (`GET /api/health`)

**前端期望字段**:

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `status` | `string` | `"ok"` 或 `"error"` |
| `version` | `string` | API 版本 |
| `openclaw.status` | `string` | `"connected"` / `"unknown"` |
| `openclaw.details` | `string` | 详情(可选) |

---

## 🔴 红线(违反=BUG)

| # | 红线 | 说明 |
|:---|:---|:---|
| R1 | 返回类型必须匹配 | `number` 不能返回 `string`,`boolean` 不能返回 `null` |
| R2 | 必填字段不能缺失 | 前端 `interface` 中非可选字段必须存在 |
| R3 | 时间戳统一用 Unix 秒 | 不用 ISO 字符串,不用毫秒 |
| R4 | 错误必须用 HTTP 状态码 | 不用 200 + `error: true` |
| R5 | 字段名用 snake_case | 不用 camelCase(前端负责转换) |

---

## 📝 变更流程

1. 修改 API → 更新本文档
2. 前端修改 → 对照本文档验证
3. 新字段 → 必须标注来源(SQLite/Blackboard/计算)
4. 废弃字段 → 标注 `@deprecated` 并保留 1 个版本

---

*本文档是前后端开发的唯一真理源。所有映射问题先查本文档。*
