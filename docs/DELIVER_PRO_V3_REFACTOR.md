# Deliver Pro V3 重构方案 — derive, don't sync + Agent 精简

> 日期：2026-07-22
> 背景：Deliver Pro E2E 从未零干预跑通；R7-R10 四轮补丁后仍暴露状态双源问题
> 定位：**系统修复**，不是第 6 个补丁
> 验收标准：**单 WP 项目 E2E 一键跑通、零人工干预**

---

## 一、问题诊断（为什么一直跑不通）

### 1.1 根因：状态双源

```
文件系统（真实进度） ←→ delivery_state.json（缓存进度）
                            ↕ 必须同步
        reconcile / phase alias / force=True / stuck 检测 / 原子写入...
```

- R10 修的 5 个问题中 4 个是双源同步 bug（B2/R2/B3/B4）
- 每次 E2E 都暴露新的同步失败模式，补丁摞补丁
- **兄弟域证明了解法**：Solution Pro 无状态机（`.stage_progress` append-only 日志）；Ship Pro 决策靠文件存在性前置检查（`state_manager.py` 只写不读，是审计日志）

### 1.2 次因：Agent 数量过多

单 WP 完整流程的 Agent 数（depth-2）：

| 角色 | 数量 | 说明 |
|:--|:--:|:--|
| Analyze Agent | 1 | WP → 任务分解 |
| Worker Agents | N（实测 7-8） | 任务执行 |
| Validate Agent | 1（+fix 轮次最多 4） | 质量门禁 |
| Package Agent | 1 | 打包交付 |
| **合计/WP** | **N+3 ~ N+7** | |

15 WP 项目（5+9+1 三层）× 平均 7 Workers = **~165 个子 Agent**。

对比：Solution Pro 全流程 ~10 个 Agent；Ship Pro ~8-12 个。

每个 Agent = 独立失败点 + bootstrap token 开销（~10-20K）+ spawn 延迟。165 个 Agent = 165 个失败点。这也放大了状态同步问题（越多 Agent 写文件，磁盘与 state 不一致的概率越高）。

### 1.3 已确认的设计缺陷

- Orchestrator 曾假设 `step3_workers()` 返回单个 spawn_params，实际返回列表 → 接口语义不清导致崩溃
- `DeliveryRunner` / `DeliverRunner` / `DeliverWPRunner` / `DeliverOrchestrator` 四个类职责重叠
- Validate FAIL 后的 fix-loop 从未在 E2E 中成功闭环过

---

## 二、三大重构原则

### 原则 1：derive, don't sync（推导，别同步）

**文件系统是唯一真相。phase 是扫出来的，不是存起来的。**

```python
def derive_phase(wp_dir: Path) -> str:
    stages = wp_dir / "stages"
    if (stages / "delivery_manifest.json").exists():      return "DELIVERED"
    if (stages / "final_deliverable/README.md").exists(): return "PACKAGING"
    if (stages / "validation_result.json").exists():      return "VALIDATING"
    if (stages / "integrated_draft/DELIVERABLE.md").exists(): return "INTEGRATING"
    if (stages / "execution_plan.json").exists():         return "GENERATING"
    return "INIT"

def derive_worker_progress(wp_dir: Path) -> tuple[set, set]:
    """completed, failed — 从 MANIFEST 推导"""
    completed, failed = set(), set()
    for m in (wp_dir / "stages/worker_outputs").glob("*/MANIFEST.json"):
        status = json.loads(m.read_text()).get("status", "")
        tid = m.parent.name
        if status in ("COMPLETE", "PASS", "PARTIAL"): completed.add(tid)
        elif status == "FAILED": failed.add(tid)
    return completed, failed
```

**效果**：resume 永远免费——根本不存在"state 与磁盘不一致"这个可能性。

### 原则 2：append-only 日志，不做决策

参照 Solution Pro `.stage_progress`：

```json
{"completed_phases": ["ANALYZING", "GENERATING"], "events": [...], "updated_at": "..."}
```

- 只增不改，无状态机、无转换校验
- 用途仅限：stuck 检测持久化、审计、监控
- **永远不作为"下一步干什么"的决策依据**

### 原则 3：能代码化的 Agent 一律代码化

Agent 只留给真正需要语义判断的角色。打包（复制文件、生成清单、模板化 README）是确定性工作 → 代码。

---

## 三、目标架构（V3）

```
L0: Main Agent
  → run_deliver_pro(project) → spawn Orchestrator Agent（1 个）

L1: Orchestrator Agent（薄层，~5 yield）
  loop:
    status = exec: orchestrator.scan()        # 纯推导，无状态机
    if status.all_done: break
    for action in status.spawn_actions: sessions_spawn(action)
    sessions_yield()

L2: Phase Agents（每 WP 只有 2 种）
  - Worker × N（执行任务）
  - Validate × 1（质量门禁）
  - （条件触发）Analyze × 1、Fix × 0~2
```

**每 WP 流水线**：

```
[Analyze*] → Workers×N → Assembly(代码) → Validate → Package(代码)
   ↑ 条件式     ↑ LLM      ↑ SmartAssembler  ↑ LLM     ↑ PackageBuilder
   仅无任务结构时           （不变，526行）            （新增，替代Agent）
```

---

## 四、改动清单

### 4.1 删除（状态双源机制，~700 行）

| 删什么 | 文件 | 理由 |
|:--|:--|:--|
| `PipelineState` / `VALID_TRANSITIONS` / `transition_to` | `contracts/pipeline_state.py` | 状态机整体废弃 |
| `_reconcile_manifests` | `orchestrator.py` | 磁盘即真相，无需同步 |
| `_check_wp_phase`（state 读取分支） | `orchestrator.py` | 改为纯文件推导 |
| `delivery_state.json` 读写（决策路径） | `wp_runner.py` | 降级为 progress log |
| R10 Fix 3（phase 兼容层） | `wp_runner.py` | 不再读存起来的 phase |
| R10 Fix 4（force=True） | `pipeline_state.py` | 无转换约束了 |
| `state_manager.py`（DEPRECATED 未清理） | 根目录 | 顺手删除 |
| `blackboard.py`（DEPRECATED 未清理） | 根目录 | 顺手删除 |

### 4.2 新增（~400 行）

| 加什么 | 文件 | 行数估 |
|:--|:--|:--:|
| `derive_phase()` + `derive_worker_progress()` + `derive_wp_status()` | `wp_runner.py` 或新 `phase_deriver.py` | ~80 |
| `ProgressLog`（append-only，含原子写入） | `progress_log.py` | ~60 |
| `PackageBuilder`（代码化打包） | `package_builder.py` | ~200 |
| `scan()`（Orchestrator 全项目推导入口） | `orchestrator.py` | ~60 |

**PackageBuilder 职责**（替代 Package Agent）：
```
1. 收集 worker_outputs + integrated_draft
2. 复制到 final_deliverable/（保留 T-XXX 结构）
3. 从 MANIFESTs + validation_result.json 生成 delivery_manifest.json
4. 从模板渲染 README.md（含 PASS/PARTIAL 状态、组件表）
5. 如有失败组件 → 从 verdict 数据模板化生成 FAILURE_REPORT.md
```

### 4.3 修改（接口统一）

| 改什么 | 说明 |
|:--|:--|
| `step3_workers()` → 明确返回 `list[spawn_params]`，文档+类型签名统一 | 修掉"以为返回单个"的接口歧义 |
| 合并 `DeliverRunner`（driver.py）进 `DeliverWPRunner` | 消除四层类重叠（4→2：Orchestrator + WPRunner） |
| Analyze 改为条件式：`execution_plan.json` 已存在 → 跳过（derive 天然支持 resume） | resume 免费 |
| Worker prompt 增加任务合并指引：相关小任务合并，目标 4-6 tasks/WP | 减少 Worker 数 |

### 4.4 保留（不动）

- ✅ `SmartAssembler`（526 行，零问题，Code-First 样板）
- ✅ 所有 `verify_*` Gate（契约笼子）
- ✅ `prepare_*_spawn` 系列（Agent 编排参数生成）
- ✅ Validate Agent + fix-loop（保留但 max_rounds 5→3）
- ✅ 原子写入（R10 Fix 2，给 progress log 用）
- ✅ ship_package graceful fallback（R10 Fix 1）

---

## 五、Agent 数量优化（回答"是不是太多了"）

### 结论：偏多，可减 ~45%

| 措施 | 每 WP 节省 | 15 WP 项目节省 |
|:--|:--:|:--:|
| Package Agent → PackageBuilder（代码） | -1 | -15 |
| Worker 任务合并（8→5 tasks/WP） | -3 | -45 |
| Analyze 条件式（resume 时跳过） | 0~-1 | 0~-15 |
| **合计** | **-4 ~ -5** | **-60 ~ -75** |

**Before**：15 WP × (1 Analyze + 8 Workers + 1 Validate + 1 Package) = **165 Agents**
**After**：15 WP × (5 Workers + 1 Validate) + 1 Orchestrator = **91 Agents**（-45%）

### 不减的部分（有证据支持保留）

- **Validate Agent**：本次 E2E 就是它抓出 T-002 幻影交付——语义质量门禁无法用代码替代
- **Workers 并行**：任务级并行是吞吐核心，只合并过碎的小任务，不搞串行

### 不追求的目标

不搞"一个 Agent 包打天下"。Solution Pro/Ship Pro 的对照显示 10 个 Agent 是健康量级；91 个对 15 WP 项目仍偏多，但这是任务分解粒度决定的，后续可通过 Ship Pro 产出带任务结构（WP 自带 tasks）进一步砍 Analyze。

---

## 六、迁移计划（分两步，随时可回退）

### Step 1：状态推导化（核心修复，不碰 Agent 流程）

1. 新增 `derive_phase()` / `derive_worker_progress()`
2. `orchestrator.py` 的 `_check_wp_phase` / `tick` 改为纯推导
3. `wp_runner.py` 各 step 改为：推导当前位置 → 决定下一步（不再读 state.phase）
4. `delivery_state.json` → `progress_log.json`（append-only）
5. 删除状态机 + reconcile
6. **验证门**：200 tests 全绿 + deliver_ai_001 残局自动续跑成功（这是现成的完美测试床）

### Step 2：Agent 精简（Package 代码化 + Worker 合并）

1. 新增 `PackageBuilder`
2. `step7_package` 从 spawn Agent 改为直接执行代码
3. Analyze prompt 增加任务合并指引（4-6 tasks）
4. **验证门**：200 tests 全绿 + 新跑一个单 WP 项目 E2E **零干预**通过

### 回退策略

每 Step 独立 commit。Step 1 失败 → revert 回 R10 状态（当前可用）。旧 `delivery_state.json` 文件保留不删，回退后仍可读。

---

## 七、验收标准（定义"跑通"）

| # | 标准 | 测量方式 |
|:--|:--|:--|
| 1 | **零干预 E2E**：`run_deliver_pro()` → DELIVERED，全程无人工修复状态 | 单 WP 项目实测 |
| 2 | **崩溃恢复**：kill 掉 Orchestrator Agent → 重启 → 自动从断点续跑 | 故意中断实测 |
| 3 | **200 tests 全绿** | pytest |
| 4 | **Agent 数 ≤ 预期**：单 WP（5 tasks）≤ 8 Agents | spawn 计数 |
| 5 | **无状态同步类 bug**：不再出现 phase/MANIFEST 不一致 | E2E 观察 |

标准 1 和 2 是硬标准——**这正是历史上从未达成过的**。

---

## 八、工作量估算

| 项 | 估算 |
|:--|:--|
| Step 1 代码改动 | ~500 行（删 700 + 加 200，净 -500） |
| Step 2 代码改动 | ~250 行（PackageBuilder 200 + 接口修改 50） |
| 测试更新 | 状态机相关测试重写（~30 个） |
| 预计净效果 | **5,465 → ~4,700 行**（-14%），状态同步代码清零 |

---

## 九、风险与开放问题

| 风险 | 缓解 |
|:--|:--|
| 推导逻辑的边界 case（如 Worker 写到一半崩溃，MANIFEST 不存在但 DELIVERABLE 存在） | 推导只看 MANIFEST（Worker 的自证文件），无 MANIFEST = 未完成，语义明确 |
| Validate fix-loop 依赖 verdict 文件多轮覆盖 | fix-loop 轮次写入 progress log（append-only 的合法用途） |
| 多 WP 并发时文件系统扫描性能 | 单 WP 目录 glob 是 O(tasks)，可忽略 |
| Ship Pro 未来产出带 tasks 的 WP | Analyze 已是条件式，天然兼容 |

**开放问题**（不阻塞，后续迭代）：
1. 是否把 Analyze 上移到 Ship Pro（WP 产出时自带任务分解）？→ 需要跨域改动，单独评估
2. Worker 失败诊断 Agent 是否保留？→ 当前从未在 E2E 验证过，建议 V3 先删除，出问题再加
