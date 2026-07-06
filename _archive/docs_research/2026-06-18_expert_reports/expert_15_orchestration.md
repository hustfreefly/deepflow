# 专家 15 报告：Agent 编排专家（OpenClaw 平台实现视角）

> **日期**: 2026-06-18
> **角色**: Agent 编排系统专家（专注 OpenClaw 平台落地实现）
> **研究范围**: OpenClaw sessions_spawn / 编排模式 / Blackboard 架构 / 错误处理
> **与 Expert 2 的分工**: Expert 2 做了业界 6 大框架的横向对比；本报告聚焦 **OpenClaw 平台上的具体实现方案**

---

## 一、OpenClaw 平台编排能力审计

### 1.1 核心原语

| 原语 | 能力 | 限制 |
|------|------|------|
| `sessions_spawn` | 非阻塞启动 sub-agent，立即返回 runId | 不接受 channel 参数；子 agent 无 message 工具 |
| `sessions_yield` | 结束当前 turn，等待子 agent 完成事件推送 | 只能等待，不能轮询 |
| `subagents` | 查看当前 session 的子 agent 状态 | 仅用于调试，不用于等待 |
| `sessions_history` | 获取子 agent 的历史（脱敏后） | 有截断，不是原始 transcript |
| 文件系统 | 所有 agent 共享同一 workspace | 无锁机制，需自行避免冲突 |

### 1.2 嵌套深度模型

```
Depth 0: agent:main2:main                    ← 主 Agent（永远可 spawn）
Depth 1: agent:main2:subagent:<uuid>         ← 编排层（maxSpawnDepth≥2 时可 spawn）
Depth 2: agent:main2:subagent:<uuid>:subagent:<uuid>  ← 叶子 Worker（永远不可 spawn）
```

**关键配置**：
```json5
{
  agents: {
    defaults: {
      subagents: {
        maxSpawnDepth: 2,           // 允许 orchestrator 模式
        maxChildrenPerAgent: 5,     // 每个 agent 最多 5 个活跃子 agent
        maxConcurrent: 8,           // 全局并发上限
        runTimeoutSeconds: 900,     // 15 分钟超时
      }
    }
  }
}
```

### 1.3 完成推送模型（Push-based）

```
Depth-2 Worker 完成 → 推送到 Depth-1 Orchestrator
Depth-1 Orchestrator 完成 → 推送到 Depth-0 Main
Main → 用户
```

**核心约束**：
- 完成是**推送式**的，不能轮询等待
- 每层只能看到**直接子 agent** 的推送
- 子 agent 输出是 `assistant` 文本，不是结构化的 JSON

---

## 二、推荐的编排模式：分层混合编排

### 2.1 编排图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Depth 0: Main Agent                          │
│  触发: 用户说"开始执行 XX 项目"                                       │
│  职责: 启动 Ship Pro Orchestrator，等待最终结果，交付给用户              │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ sessions_spawn (context: isolated)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Depth 1: Ship Pro Orchestrator                      │
│  职责:                                                               │
│    1. 读取 blackboard 文件（final_result + RTM + execution_plan）      │
│    2. LLM 解析 → 提取架构 → 拆分 WP                                   │
│    3. 为每个 WP spawn 一个 Worker                                     │
│    4. sessions_yield 等待所有 Worker 完成                              │
│    5. 收集结果 → 组装 ship_package.json                               │
│    6. 质量校验 → 输出最终包                                            │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ sessions_spawn × N (并行)
                            ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Depth 2: WP-001 │  │  Depth 2: WP-002 │  │  Depth 2: WP-003 │
│  Worker          │  │  Worker          │  │  Worker          │
│                  │  │                  │  │                  │
│  读: WP spec     │  │  读: WP spec     │  │  读: WP spec     │
│  做: 细化 AC     │  │  做: 细化 AC     │  │  做: 细化 AC     │
│  写: wp_result   │  │  写: wp_result   │  │  写: wp_result   │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 2.2 为什么选择这个模式

| 模式 | 优点 | 缺点 | 适合 Ship Pro？ |
|------|------|------|:-:|
| 纯串行 | 简单、可控 | 慢（5 个 WP = 5× 时间） | ❌ |
| 纯并行 | 快 | 无法处理 WP 间依赖 | ⚠️ 部分 |
| **分层混合** | 编排层串行决策 + Worker 层并行执行 | 实现稍复杂 | ✅ |
| 层级+消息 | 灵活 | OpenClaw 不支持直接消息传递 | ❌ |

**关键决策**：
- **WP 拆分**由 Orchestrator 串行完成（需要全局视角）
- **WP 细化**由 Workers 并行完成（相互独立）
- **依赖处理**：如果 WP-002 依赖 WP-001 的输出，Orchestrator 分两批 spawn（先 WP-001，完成后 spawn WP-002）

### 2.3 与 Expert 2 建议的差异

Expert 2 建议"Ship Pro 是 LLM 引导编译器，单 Agent 完成"。本专家认为：

- **小项目（≤3 WP）**：单 Agent 足够，不需要 spawn Workers
- **中型项目（4-8 WP）**：Orchestrator + 并行 Workers 明显更快
- **大型项目（>8 WP）**：需要分批 + 依赖图管理

**推荐**：Ship Pro 内部根据 WP 数量动态选择模式。

---

## 三、Agent 间数据传递设计

### 3.1 文件系统布局

```
blackboard/
├── .ship_pro/                          ← Ship Pro 专属工作目录
│   ├── orchestrator_state.json         ← 编排状态（进度、依赖图）
│   ├── wp_specs/                       ← 每个 WP 的规格说明
│   │   ├── wp_001_spec.json
│   │   ├── wp_002_spec.json
│   │   └── ...
│   ├── wp_results/                     ← 每个 Worker 的输出
│   │   ├── wp_001_result.json
│   │   ├── wp_002_result.json
│   │   └── ...
│   └── quality_reports/               ← 质量校验报告
│       └── wp_001_qa.json
│
├── final_result.json                   ← Solution Pro 输出（只读）
├── requirements_traceability_matrix.json  ← Solution Pro 输出（只读）
├── execution_plan.json                 ← Solution Pro 输出（只读）
│
└── ship_package.json                   ← 最终输出（Ship Pro 完成后生成）
```

### 3.2 文件命名规范

| 文件 | 写入者 | 读取者 | 格式 | 生命周期 |
|------|--------|--------|------|----------|
| `wp_{id}_spec.json` | Orchestrator | Worker | JSON | Worker 完成后标记为 consumed |
| `wp_{id}_result.json` | Worker | Orchestrator | JSON | 组装完成后归档 |
| `orchestrator_state.json` | Orchestrator | Orchestrator（恢复用） | JSON | 每次状态变更时更新 |
| `ship_package.json` | Orchestrator | Super Loop | JSON | 最终产物，长期保留 |

### 3.3 文件格式定义

#### WP Spec（Orchestrator → Worker）

```json
{
  "wp_id": "WP-001",
  "title": "API网关层",
  "context": {
    "project_name": "跨境AI算力中转站",
    "tech_stack": {"language": "TypeScript", "runtime": "Node.js"},
    "architecture_overview": "...（从 final_result 提取的相关部分）"
  },
  "requirements": [
    {"id": "REQ-001", "text": "支持3+ AI供应商", "priority": "P0"}
  ],
  "initial_ac": [
    {"criterion": "支持至少3家AI供应商的API接入", "source": "LLM提取"}
  ],
  "estimated_hours": 40,
  "dependencies": [],
  "output_path": "blackboard/.ship_pro/wp_results/wp_001_result.json"
}
```

#### WP Result（Worker → Orchestrator）

```json
{
  "wp_id": "WP-001",
  "status": "completed",  // completed | partial | failed
  "refined_ac": [
    {
      "id": "AC-001",
      "criterion": "支持至少3家AI供应商的API接入",
      "verification": "集成测试：对 OpenAI/Anthropic/Google 发送相同请求，验证响应格式一致",
      "priority": "P0",
      "confidence": 0.9
    }
  ],
  "technical_constraints": [
    "使用 New API（MIT License），Docker 部署"
  ],
  "deliverables": [
    "src/gateway/router.ts",
    "tests/integration/gateway.test.ts"
  ],
  "integration_checkpoints": [
    {"after": "WP-003", "check": "API网关 + 支付系统集成验证"}
  ],
  "risk_flags": [
    {"risk": "供应商 API 限流策略不同", "mitigation": "统一限流中间件"}
  ],
  "worker_notes": "建议增加供应商健康检查端点..."
}
```

#### Orchestrator State（断点恢复用）

```json
{
  "project": "跨境AI算力中转站",
  "started_at": "2026-06-18T21:00:00+08:00",
  "status": "workers_running",
  "wp_graph": {
    "WP-001": {"status": "completed", "worker_session": "agent:main2:subagent:abc123"},
    "WP-002": {"status": "running", "worker_session": "agent:main2:subagent:def456"},
    "WP-003": {"status": "pending", "blocked_by": ["WP-001"]}
  },
  "retry_counts": {"WP-002": 1},
  "last_checkpoint": "2026-06-18T21:15:00+08:00"
}
```

### 3.4 避免文件冲突的策略

| 风险 | 策略 |
|------|------|
| 多个 Worker 同时写同一文件 | 每个 Worker 只写自己的 `wp_{id}_result.json` |
| Worker 读 Orchestrator 正在写的文件 | Orchestrator 先写完所有 spec 再 spawn Workers |
| 文件名冲突 | 使用 WP ID 作为文件名前缀（保证唯一） |
| 大文件读写竞态 | 使用原子写入（先写 `.tmp` 再 `mv`） |

---

## 四、错误处理和降级策略

### 4.1 失败分类

| 类型 | 示例 | 处理策略 |
|------|------|----------|
| **瞬态失败** | API 超时、rate limit | 自动重试（指数退避） |
| **质量失败** | Worker 输出缺少必填字段 | 质量校验 → 重新 spawn |
| **逻辑失败** | WP 依赖关系矛盾 | Orchestrator 检测 → 报告用户 |
| **超时失败** | Worker 超过 15 分钟 | OpenClaw 自动终止 → 降级处理 |

### 4.2 重试策略

```
Worker 失败
  ├─ 瞬态失败（API error）→ 重试最多 3 次，间隔 2s/4s/8s
  ├─ 质量失败（输出不完整）→ 重新 spawn，附带错误反馈
  │    └─ 最多重试 2 次，第 3 次降级
  └─ 超时失败 → 不重试，直接降级
```

### 4.3 降级策略

| 场景 | 降级方案 |
|------|----------|
| 单个 Worker 失败（重试耗尽） | Orchestrator 用已有信息自己生成该 WP 的 result |
| 多个 Worker 失败（>50%） | 放弃并行模式，Orchestrator 串行处理所有 WP |
| Orchestrator 自身失败 | Main Agent 检测到超时 → 通知用户手动干预 |
| 文件系统不可用 | 回退到单 Agent 模式（所有工作在 Orchestrator 内完成） |

### 4.4 质量校验（Orchestrator 对 Worker 输出的检查）

```python
# 伪代码：质量校验逻辑
def validate_wp_result(result: dict) -> list[str]:
    errors = []
    
    # 必填字段检查
    required = ["wp_id", "status", "refined_ac", "deliverables"]
    for field in required:
        if field not in result:
            errors.append(f"缺少必填字段: {field}")
    
    # AC 质量检查
    if "refined_ac" in result:
        for ac in result["refined_ac"]:
            if not ac.get("verification"):
                errors.append(f"AC {ac.get('id')} 缺少验证方法")
            if not ac.get("criterion"):
                errors.append(f"AC {ac.get('id')} 缺少验收标准")
    
    # 工时合理性检查
    if result.get("estimated_hours", 0) > 200:
        errors.append("工时估算超过 200h，可能需要拆分")
    
    return errors
```

### 4.5 断路器模式

```
连续失败计数 = 0

每次 Worker 失败:
  连续失败计数 += 1
  if 连续失败计数 >= 3:
    触发断路器
    → 停止 spawn 新 Workers
    → 等待 30 秒（冷却期）
    → 降级为单 Agent 模式
    → 通知用户："检测到系统不稳定，已切换到降级模式"
```

---

## 五、具体实现方案

### 5.1 Ship Pro Orchestrator 主流程

```python
# 伪代码：Ship Pro Orchestrator 主流程

async def ship_pro_orchestrator(project_dir: str):
    # Phase 1: 读取 Solution Pro 输出
    final_result = read_json(f"{project_dir}/final_result.json")
    rtm = read_json(f"{project_dir}/requirements_traceability_matrix.json")
    exec_plan = read_json(f"{project_dir}/execution_plan.json")
    
    # Phase 2: LLM 解析 → 提取架构 → 拆分 WP
    wp_specs = llm_extract_and_split(final_result, rtm, exec_plan)
    
    # Phase 3: 写入 WP specs 到文件系统
    for spec in wp_specs:
        write_json(f"{project_dir}/.ship_pro/wp_specs/{spec['wp_id']}_spec.json", spec)
    
    # Phase 4: 构建依赖图，确定执行批次
    batches = topological_sort_batches(wp_specs)
    
    # Phase 5: 按批次并行执行
    all_results = {}
    for batch in batches:
        # Spawn 本批次所有 Workers
        for spec in batch:
            sessions_spawn(
                task=f"读取 {spec['wp_id']} 的 spec，细化 AC 和交付物，写入 result 文件",
                taskName=f"wp_worker_{spec['wp_id'].lower()}",
                mode="run"
            )
        
        # 等待本批次完成
        sessions_yield()
        
        # 收集结果 + 质量校验
        for spec in batch:
            result = read_json(f"{project_dir}/.ship_pro/wp_results/{spec['wp_id']}_result.json")
            errors = validate_wp_result(result)
            
            if errors:
                # 重试或降级
                result = handle_failure(spec, errors, retry_count=1)
            
            all_results[spec['wp_id']] = result
    
    # Phase 6: 组装 ship_package.json
    ship_package = assemble_ship_package(all_results, final_result)
    write_json(f"{project_dir}/ship_package.json", ship_package)
    
    return ship_package
```

### 5.2 OpenClaw 配置建议

```json5
// openclaw.json 中 Ship Pro 相关配置
{
  agents: {
    defaults: {
      subagents: {
        maxSpawnDepth: 2,
        maxChildrenPerAgent: 5,
        maxConcurrent: 8,
        runTimeoutSeconds: 900,  // 15 min per worker
        model: "a-cheaper-model",  // Workers 用便宜模型
        // Orchestrator 用主模型，Worker 用子模型
      }
    },
    list: [
      {
        id: "ship-pro-orchestrator",
        name: "Ship Pro Orchestrator",
        subagents: {
          model: "a-cheaper-model",  // Worker 模型
          runTimeoutSeconds: 600,     // Worker 10 分钟超时
        }
      }
    ]
  }
}
```

### 5.3 与 Hermes Agent 的对比

| 维度 | OpenClaw 内编排 | Hermes Agent 编排 |
|------|----------------|------------------|
| **启动开销** | 低（已有基础设施） | 高（需要额外部署） |
| **文件系统访问** | 直接共享 workspace | 需要配置挂载 |
| **完成通知** | 内置 push-based | 需要自己实现 |
| **嵌套深度** | 最多 5 层（推荐 2 层） | 无限制 |
| **错误恢复** | 依赖 OpenClaw 重试 | 可自定义任意策略 |
| **可观测性** | `subagents` + `sessions_history` | 需要自建 |

**建议**：**在 OpenClaw 内编排**。理由：
1. Ship Pro 的编排复杂度不需要 Hermes 级别的灵活性
2. OpenClaw 的 push-based 完成模型已经足够
3. 减少一个外部依赖，降低运维成本
4. 文件系统共享在 OpenClaw 内是天然的

---

## 六、对上下文文件 Q1-Q5 的回答

### Q1: Ship Pro 用 LLM 还是确定性编译器？

**建议：LLM 引导 + 确定性校验**

- LLM 负责：解析不统一的 final_result 格式、提取架构信息、拆分 WP
- 确定性代码负责：文件 I/O、格式校验、依赖图计算、组装 ship_package

**OpenClaw 实现**：Orchestrator 本身就是 LLM（有 LLM 能力），Worker 可以是 LLM 或确定性脚本。

### Q2: Ship Pro 应该读几个文件？

**建议：读 3 个文件（final_result + RTM + execution_plan）**

- living_blueprint 的 design_decisions 价值有限（Ship Pro 关心"做什么"，不关心"为什么"）
- 3 个文件 ≈ 33KB，在 LLM 上下文窗口内完全可控

### Q3: `_ship_pro_hints` 约定是否可行？

**建议：可行，但简化为 `ship_pro_navigation` 字段**

```json
{
  "_ship_pro_hints": {
    "architecture_location": "architecture.core_components",
    "implementation_plan_location": "implementation_plan.phases",
    "requirements_location": "requirements.items"
  }
}
```

**风险缓解**：即使 hints 字段缺失或错误，Ship Pro 的 LLM 应该能自己定位（final_result 格式虽然不统一，但字段名是有语义的）。

### Q4: 砍掉 blueprint freezing 后，下游格式稳定性？

**建议：ship_package.json 的 JSON Schema 就是稳定性保证**

- 定义严格的 JSON Schema（必填字段、类型约束）
- Ship Pro 输出前做 Schema 校验
- Super Loop 只信任通过校验的 ship_package

### Q5: 确定性编译器 → LLM 引导编译器的代码量变化？

**估计**：
- 当前确定性编译器：1048 行 Python
- LLM 引导编译器：~400 行 Python（文件 I/O + 校验 + 组装）+ ~200 行 prompt 工程
- **净减少约 400 行代码**，但增加了 prompt 维护成本

---

## 七、实施信心评分

| 维度 | 信心 | 理由 |
|------|:----:|------|
| OpenClaw 编排能力满足需求 | **9/10** | 文档明确支持 maxSpawnDepth=2，push-based 完成 |
| 文件系统数据传递可行 | **8/10** | 简单可靠，但需注意并发写入冲突 |
| 错误处理策略完备 | **7/10** | 覆盖了主要场景，但 LLM 输出质量难以 100% 保证 |
| 与 Hermes 对比后的选择 | **8/10** | OpenClaw 内编排足够，Hermes 是 overkill |
| 整体方案可实施性 | **8/10** | 技术风险可控，主要风险在 LLM 输出质量 |

**总体信心：8/10**

---

## 八、关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Worker LLM 输出质量不稳定 | ship_package 质量下降 | 质量校验 + 重试 + 降级 |
| 大项目 WP 数量 > maxChildrenPerAgent | 无法全部并行 | 分批执行（topological batches） |
| 文件系统竞态条件 | 数据损坏 | 原子写入 + 每 Worker 独立文件 |
| OpenClaw gateway 重启 | 进行中的 Workers 丢失 | orchestrator_state.json 断点恢复 |
| LLM 解析 final_result 错误 | 架构信息提取错误 | 让用户确认关键提取结果 |

---

## 九、总结

### 推荐的编排模式

**分层混合编排**：
- Depth 0: Main Agent（触发 + 交付）
- Depth 1: Ship Pro Orchestrator（解析 + 拆分 + 组装）
- Depth 2: WP Workers（并行细化 AC + 交付物）

### 核心设计决策

1. ✅ **在 OpenClaw 内编排**，不引入 Hermes
2. ✅ **文件系统传递数据**，每 Worker 独立文件避免冲突
3. ✅ **push-based 完成等待**，不轮询
4. ✅ **质量校验 + 重试 + 降级**三层错误处理
5. ✅ **动态模式选择**：小项目单 Agent，大项目多 Agent

### 下一步行动

1. 定义 ship_package.json 的 JSON Schema
2. 实现 Orchestrator 的 prompt（LLM 解析 + 拆分逻辑）
3. 实现 Worker 的 prompt（AC 细化逻辑）
4. 实现质量校验模块
5. 端到端测试（用 8 个历史案例回测）
