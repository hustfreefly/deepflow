# Deliver Pro 防御性修复方案（多专家审查版）

> 审查时间: 2026-07-31 08:40
> 审查专家: 架构师 (DeepSeek V4 Pro) + 对抗审查 (Kimi K3) + 工程落地 (Qwen 3.7 Max)
> 方法论: FixFlow Phase 1 + 多视角交叉审查

---

## 专家共识（3/3 一致）

| # | 共识点 | 说明 |
|---|--------|------|
| 1 | **SafeJsonLoader 方向正确，但必须是纯函数** | Loader 只做 read+validate，不写合成文件。写合成是业务决策，由调用方显式选择 |
| 2 | **状态冗余** | batch_progress.json + delivery_state.json 双写 task_attempts，一个损坏时另一个是 recovery source |
| 3 | **重试上限** | H3 无限循环问题：加 retry counter，超过 N 次 → terminal_failed |
| 4 | **异常分类** | 区分瞬态错误（OSError/IOError → 重试）vs 逻辑错误（ValidationError → 判死） |
| 5 | **原子替换模式** | LLM 写 .tmp → 代码层校验（json.loads + Pydantic）→ PASS 则原子替换，FAIL 则保留 .tmp 为证据 |

---

## 专家关键洞察

### 架构师（DeepSeek V4 Pro）

**SafeJsonLoader 设计修正**：

```python
@dataclass
class LoadResult:
    data: dict | None          # 原始 JSON
    parsed: BaseModel | None   # Pydantic 对象
    state: Literal["ok", "not_found", "invalid_json", "schema_validation_failed"]
    error: str | None

class SafeJsonLoader:
    @staticmethod
    def load(path, schema_cls) -> LoadResult:
        # 纯函数：读 + 校验 + 返回结果
        # NEVER 写合成文件
        ...
    
    @staticmethod  
    def synthesize_fallback(path, template) -> None:
        # 独立的显式方法：调用方明确要求合成
```

**计数器文件化**：每个 task 独立计数器文件，不依赖 batch_progress.json

```
worker_outputs/T-001/.attempt_count   # 内容: "3"
worker_outputs/T-002/.attempt_count   # 内容: "1"
```

### 对抗审查（Kimi K3）

**发现 2 个循环依赖 + 1 个竞态 + 1 个机制缺失**：

| # | 问题 | 影响 | 修复 |
|---|------|------|------|
| V4 | H2↔H3 循环依赖：counter 存 batch_progress → H2 重建时 counter 归零 → H3 无限循环借尸还魂 | 修复方案自相矛盾 | counter 落盘到 WP 级独立文件，与 batch_progress 解耦 |
| V5 | 读写竞态：worker 正在写 MANIFEST 时 pulse 读到半截 JSON → 误判损坏 | 误杀健康任务 | SafeJsonLoader 加 mtime 宽限（<60s 视为写入中，跳过） |
| 缺失 | **无熔断机制**：LLM 持续输出损坏 JSON → 批量 fallback → 系统死亡 | 修复方案只防了单点，没防批量 | 加腐坏率熔断：单周期 ≥3 WP 损坏 → 停止 dispatch，告警人工介入 |

**合成 MANIFEST 的 failure_class 必须是新枚举值**：

```python
# 不能用 contract_violation 或 quality_failure（会触发豁免重派 → H3 换皮复发）
# 新枚举值：
failure_class = "output_corrupted"  # 不在豁免列表内
```

### 工程落地（Qwen 3.7 Max）

**优先级调整**：
- M6（pulse_state 损坏 → 告警失效）应提到 Wave 1
- M1（4 重定义）可并行做，零风险

**快速修复（1.5 小时）**：

| # | 修复 | 时间 | 收益 |
|---|------|------|------|
| M1 | 删除 verify_package_output 前 3 个重复定义 | 5min | 消除维护陷阱 |
| H3 | _validate_delivery_manifest 加 retry counter | 15min | 阻断无限循环 |
| M6 | _update_pulse_state 损坏保护 | 15min | 恢复告警能力 |
| H2 | _load_progress 损坏保护 | 30min | 防止状态全丢 |

**代码异味**：
- orchestrator.py 是 2450 行上帝类
- `except Exception: pass/continue` 出现 ≥6 次
- wp_runner.py 1746 行 + 4 个相同方法定义

---

## 最终修复方案

### 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM Agent 输出                            │
│                         ↓                                    │
│              写 .tmp 文件（原子写入）                         │
│                         ↓                                    │
│    ┌──────────────────────────────────────────────┐         │
│    │         SafeJsonLoader（纯函数）              │         │
│    │  1. mtime < 60s → 跳过（写入中）             │         │
│    │  2. json.loads(.tmp)                          │         │
│    │  3. Pydantic.model_validate(strict=True)      │         │
│    │  4. 返回 LoadResult（不写文件）                │         │
│    └──────────────────────────────────────────────┘         │
│                         ↓                                    │
│              ┌──────────────────┐                           │
│              │   LoadResult     │                           │
│              │  state: ok/...   │                           │
│              │  parsed: BaseModel│                          │
│              └──────────────────┘                           │
│                         ↓                                    │
│         ┌───────────────┴───────────────┐                   │
│         ↓                               ↓                   │
│    state == ok                      state != ok             │
│         ↓                               ↓                   │
│  atomic_write_json()          调用方决定 fallback:          │
│  （原子替换为正式文件）        - OSError → 重试（不递增）   │
│                                 - invalid_json → 合成 + 告警│
│                                 - 连续损坏 ≥3 → 熔断       │
└─────────────────────────────────────────────────────────────┘
```

### 分阶段交付

#### Phase A: 快速修复（1.5h）— 零风险/低风险

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| M1 | 删除重复方法定义 | wp_runner.py:1581,1601,1621 | 删 3 处，保留 1641 |
| H3 | 加 retry counter | phase_deriver.py:182 | progress_entry 加 manifest_retry_count，≥3 → terminal_failed |
| M6 | pulse_state 损坏保护 | orchestrator.py:1419 | `state = {}` → 备份 + 重建 last_signature |
| H2 | batch_progress 损坏保护 | orchestrator.py:215 | `return {}` → 备份 + 从文件证据重建 |

#### Phase B: SafeJsonLoader + H1（1.5h）

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| 基础设施 | 创建 SafeJsonLoader | utils/safe_json_loader.py | 纯函数 + mtime 宽限 + 异常分类 |
| H1 | MANIFEST 损坏不静默跳过 | orchestrator.py:955 | SafeJsonLoader + 合成 FAILED（failure_class=output_corrupted） |

#### Phase C: 统一替换（4-6h）

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| M2-M8 | 31 处 json.loads 替换 | orchestrator/driver/wp_runner/phase_deriver | SafeJsonLoader + Pydantic |

#### Phase D: 熔断 + 边缘加固（2-3h）

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| 新增 | 腐坏率熔断 | orchestrator.py pulse() | 单周期 ≥3 WP 损坏 → 停止 dispatch |
| L1-L6 | 边缘加固 | 多文件 | 路径显式化 + 异常分类 + I/O 优化 |

---

## 验收标准

| Phase | 验收条件 |
|-------|----------|
| **A** | ① 361 个现有测试全绿 ② MANIFEST 损坏最多回退 3 次后进 terminal_failed ③ pulse_state 损坏后 STALLED 告警仍触发 ④ batch_progress 损坏后 terminal_failed 不丢失 |
| **B** | ① SafeJsonLoader 单元测试覆盖 4 种 state ② MANIFEST 损坏时 Worker 不 stuck ③ 合成 MANIFEST 通过 WorkerOutputMeta 校验 |
| **C** | ① 31 处裸 json.loads 全部替换 ② 任意 JSON 损坏不导致静默错误决策 ③ 新增 15-20 个 schema 校验测试 |
| **D** | ① 单周期 ≥3 WP 损坏时停止 dispatch ② 熔断后仅人工可恢复 ③ 无回归 |

---

## 专家分歧点

| 议题 | 架构师 | 对抗审查 | 工程落地 | 最终决策 |
|------|--------|----------|----------|----------|
| 计数器存储 | 文件化（per-task .attempt_count） | batch_progress.json（但指出循环依赖） | batch_progress.json | **WP 级独立文件**（对抗审查说服了架构师） |
| Schema Registry | 不需要 | 不需要 | 不需要 | **不引入** |
| Validator Agent | 不需要（代码校验足够） | 不需要 | 不需要 | **不引入** |
| 合成 MANIFEST 放 loader | ❌ 职责越界 | ❌ 必须独立 | 可接受 | **不放 loader**（架构师说服了） |

---

## 实施建议

1. **先做 Phase A**（1.5h）：快速消除 3 个卡死路径 + 1 个告警盲区，验证不影响现有 361 个测试
2. **再做 Phase B**（1.5h）：引入 SafeJsonLoader 基础设施 + 修复 H1
3. **Phase C 逐文件替换**（4-6h）：每替换一个文件跑一次测试
4. **Phase D 最后做**（2-3h）：熔断机制 + 边缘加固

**对运行中 Pulse 的影响**：
- Phase A/B：✅ 无影响（只增加异常保护，不改变正常路径）
- Phase C：⚠️ 低风险（Pydantic 严格校验可能暴露之前静默通过的畸形数据）
- Phase D：✅ 无影响

---

## 总结

3 位专家的核心贡献：
- **架构师**：SafeJsonLoader 必须是纯函数，计数器文件化
- **对抗审查**：发现循环依赖 V4、竞态 V5、熔断缺失、合成 MANIFEST 必须用新枚举值
- **工程落地**：优先级调整（M6 提到 Wave 1）、快速修复路径（1.5h 完成 Phase A）、代码异味识别

最终方案：**4 个 Phase，总计 8-12 小时，31 处 json.loads 替换，新增熔断机制**。
