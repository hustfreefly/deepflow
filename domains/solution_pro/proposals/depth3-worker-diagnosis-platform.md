# OpenClaw 多层 Subagent Spawn 平台限制诊断报告

> **诊断日期**: 2026-07-13
> **诊断目标**: 确认 5 层架构 (depth 0-4) 的平台可行性
> **结论**: ✅ **平台完全支持，当前配置正确，无需修改**

---

## 1. OpenClaw 文档中的 Depth 限制说明

### 来源: `/opt/homebrew/lib/node_modules/openclaw/docs/tools/subagents.md`

**关键文档摘录**:

| 配置项 | 默认值 | 范围 | 说明 |
|--------|--------|------|------|
| `maxSpawnDepth` | 1 | **1–5** | 最大嵌套深度 |
| `maxChildrenPerAgent` | 5 | 1–20 | 每个 agent session 的最大活跃子代数 |
| `maxConcurrent` | 8 | - | 全局并发 lane 上限 |

**文档中的深度表**（描述的是 maxSpawnDepth=2 的推荐场景）:

| Depth | Session Key 格式 | 角色 | 能否 spawn? |
|-------|-----------------|------|------------|
| 0 | `agent:<id>:main` | Main agent | Always |
| 1 | `agent:<id>:subagent:<uuid>` | Sub-agent (orchestrator) | Only if `maxSpawnDepth >= 2` |
| 2 | `agent:<id>:subagent:<uuid>:subagent:<uuid>` | Sub-sub-agent (leaf worker) | **Never** (当 maxSpawnDepth=2) |

> ⚠️ **文档误导点**: 文档中 "Depth 2: Never" 的描述是针对 **默认/推荐配置 maxSpawnDepth=2** 的场景，并非硬编码限制。文档明确说 "Maximum nesting depth is 5 (maxSpawnDepth range: 1–5). Depth 2 is recommended for most use cases."

---

## 2. 源码中的实际限制逻辑

### 2.1 深度计算: `getSubagentDepth(sessionKey)`

**文件**: `session-key-utils-C7uT9A4s.js`

```javascript
function getSubagentDepth(sessionKey) {
    const raw = normalizeOptionalLowercaseString(sessionKey);
    if (!raw) return 0;
    return raw.split(":subagent:").length - 1;
}
```

**原理**: 通过计算 session key 中 `:subagent:` 出现的次数来确定深度。

示例:
- `agent:main:main` → depth 0
- `agent:main:subagent:uuid1` → depth 1
- `agent:main:subagent:uuid1:subagent:uuid2` → depth 2
- `agent:main:subagent:uuid1:subagent:uuid2:subagent:uuid3` → depth 3
- `agent:main:subagent:uuid1:subagent:uuid2:subagent:uuid3:subagent:uuid4` → depth 4

### 2.2 角色解析: `resolveSubagentRoleForDepth(params)`

**文件**: `subagent-capabilities-BMHg2GYg.js`

```javascript
function resolveSubagentRoleForDepth(params) {
    const depth = resolveNonNegativeIntegerOption(params.depth, 0);
    const maxSpawnDepth = resolveIntegerOption(params.maxSpawnDepth, 1, { min: 1 });
    if (depth <= 0) return "main";
    return depth < maxSpawnDepth ? "orchestrator" : "leaf";
}
```

**关键逻辑**: `depth < maxSpawnDepth` → "orchestrator"，`depth >= maxSpawnDepth` → "leaf"

### 2.3 能力解析: `resolveSubagentCapabilities(params)`

```javascript
function resolveSubagentCapabilities(params) {
    const depth = resolveNonNegativeIntegerOption(params.depth, 0);
    const role = resolveSubagentRoleForDepth(params);
    const controlScope = resolveSubagentControlScopeForRole(role);
    return {
        depth,
        role,
        controlScope,
        canSpawn: role === "main" || role === "orchestrator",
        canControlChildren: controlScope === "children"
    };
}
```

### 2.4 Spawn 准入检查

**文件**: `openclaw-tools-B0V1p3La.js` (line 11745-11748)

```javascript
const maxSpawnDepth = cfg.agents?.defaults?.subagents?.maxSpawnDepth ?? 1;
if (callerDepth >= maxSpawnDepth) return {
    status: "forbidden",
    error: `sessions_spawn is not allowed at this depth (current depth: ${callerDepth}, max: ${maxSpawnDepth})`
};
```

**准入规则**: `callerDepth >= maxSpawnDepth` → 拒绝。即只有 `callerDepth < maxSpawnDepth` 才能 spawn。

### 2.5 子代深度分配

```javascript
const childDepth = callerDepth + 1;
const childCapabilities = resolveSubagentCapabilities({
    depth: childDepth,
    maxSpawnDepth
});
```

---

## 3. 当前配置检查结果

### 来源: `~/.openclaw/openclaw.json`

```json
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 20,
        "maxSpawnDepth": 4
      }
    }
  }
}
```

| 配置项 | 当前值 | 评估 |
|--------|--------|------|
| `maxSpawnDepth` | **4** | ✅ 正确，支持 5 层架构 (depth 0-4) |
| `maxConcurrent` | **20** | ✅ 充足 |
| `maxChildrenPerAgent` | 未设置 (默认 5) | ✅ 每层最多 5 个活跃子代 |

---

## 4. Depth-2 Agent 是否有 Spawn 能力的结论

### ✅ 结论: Depth-2 Agent **可以** Spawn（在 maxSpawnDepth=4 配置下）

**完整深度能力矩阵 (maxSpawnDepth=4)**:

| Depth | Session Key 示例 | 角色 | canSpawn | 能否被 spawn |
|-------|-----------------|------|----------|-------------|
| 0 | `agent:main2:main` | main | ✅ true | N/A (主 Agent) |
| 1 | `agent:main2:subagent:<uuid>` | orchestrator | ✅ true (1<4) | ✅ depth 0 spawn |
| 2 | `...subagent:<uuid>:subagent:<uuid>` | orchestrator | ✅ true (2<4) | ✅ depth 1 spawn |
| 3 | `...subagent:<uuid>:subagent:<uuid>:subagent:<uuid>` | orchestrator | ✅ true (3<4) | ✅ depth 2 spawn |
| 4 | `...:subagent:<uuid>:subagent:<uuid>:subagent:<uuid>:subagent:<uuid>` | **leaf** | ❌ false (4≥4) | ✅ depth 3 spawn |

### 5 层架构映射

```
depth-0: Main Agent (main2) ─── 角色: main, canSpawn=true
  └─ depth-1: 2.0.0 Orchestrator ─── 角色: orchestrator, canSpawn=true (1<4)
       └─ depth-2: Module Agent ─── 角色: orchestrator, canSpawn=true (2<4)
            └─ depth-3: Workers ─── 角色: orchestrator, canSpawn=true (3<4)
                 └─ depth-4: 迭代推理 ─── 角色: leaf, canSpawn=false (4≥4)
```

**每一层的工具权限**:

| 工具 | depth 0 | depth 1 | depth 2 | depth 3 | depth 4 |
|------|---------|---------|---------|---------|---------|
| sessions_spawn | ✅ | ✅ | ✅ | ✅ | ❌ |
| sessions_yield | ✅ | ✅ | ✅ | ✅ | ❌ |
| subagents | ✅ | ✅ | ✅ | ✅ | ❌ |
| sessions_list | ✅ | ✅ | ✅ | ✅ | ❌ |
| sessions_history | ✅ | ✅ | ✅ | ✅ | ❌ |
| read/write/exec | ✅ | ✅ | ✅ | ✅ | ✅ |

> depth 1-3 获得 orchestrator 工具集（sessions_spawn, subagents, sessions_list, sessions_history），因为它们的角色是 "orchestrator"。
> depth 4 是 "leaf"，没有 session 工具，只能执行任务并返回结果。

---

## 5. 平台层面是否需要修改配置

### ✅ 不需要修改。当前配置已完全满足 5 层架构需求。

**验证清单**:

- [x] `maxSpawnDepth=4` → 支持 depth 0-3 的 agent spawn 子代
- [x] depth-4 是 leaf，不需要 spawn（它是最终执行层）
- [x] `maxConcurrent=20` → 足够的并发量
- [x] `maxChildrenPerAgent=5` (默认) → 每层最多 5 个活跃子代
- [x] Announce chain: depth 4 → depth 3 → depth 2 → depth 1 → main（自动逐级上报）
- [x] Cascade stop: `/stop` 会级联停止所有子代

### 潜在风险与建议

| 风险项 | 级别 | 建议 |
|--------|------|------|
| Token 消耗随深度递增 | ⚠️ 中 | 每层 subagent 有独立 context，5 层 = 5 倍 token 开销。建议 depth-3/4 使用更便宜的模型 |
| Announce 链延迟 | ⚠️ 中 | 结果需逐层上报 (4→3→2→1→0)，每层有 announce timeout (默认 120s) |
| maxChildrenPerAgent=5 | ℹ️ 低 | 如果某层需要 >5 个并行子代，需调整此参数 |
| 深度 >5 的扩展 | ℹ️ 低 | maxSpawnDepth 最大可设为 5，支持 6 层。当前 4 已足够 |
| 子代 context 隔离 | ℹ️ 信息 | Sub-agent 只注入 AGENTS.md + TOOLS.md，不含 MEMORY.md/SOUL.md 等 |

### Announce Chain 流程

```
depth-4 (迭代推理) 完成
  → announce 到 depth-3 (Worker)
    → depth-3 综合所有 depth-4 结果后完成
      → announce 到 depth-2 (Module Agent)
        → depth-2 综合所有 depth-3 结果后完成
          → announce 到 depth-1 (2.0.0 Orchestrator)
            → depth-1 综合所有 depth-2 结果后完成
              → announce 到 depth-0 (Main Agent)
                → 交付给用户
```

**每一层只能看到直接子代的 announce**，不能跨层。这是设计如此。

---

## 总结

| 问题 | 答案 |
|------|------|
| maxSpawnDepth=4 是否支持 5 层架构？ | ✅ 是，完全支持 |
| depth-2 Agent 能否 spawn depth-3？ | ✅ 能，角色为 orchestrator |
| depth-3 Agent 能否 spawn depth-4？ | ✅ 能，角色为 orchestrator |
| depth-4 Agent 能否 spawn？ | ❌ 不能，角色为 leaf（这是预期行为） |
| 需要修改配置吗？ | ❌ 不需要，当前配置正确 |
| 文档说 "depth 2 never spawns" 是真的吗？ | ⚠️ 文档描述的是 maxSpawnDepth=2 的场景，不适用于 maxSpawnDepth=4 |
