# Deliver Pro 脉冲式调度架构评审 — AI Native 纯度 + 泛化性

> 评审时间：2026-07-23  
> 评审维度：AI Native 纯度、泛化性、薄调度/硬契约切分  
> 评审结论：**P0 问题 2 个，P1 问题 4 个，P2 问题 3 个**

---

## 一、总体评价

提案的核心思路——用 cron 脉冲替代长寿 LLM orchestrator 循环——方向正确，是对平台不可靠原语的务实放弃。但方案在"薄调度"的边界划定上存在多处模糊地带，phase_deriver.py 中隐藏的规则引擎思维残留、orchestrator.py 中 LLM 与代码职责的错位、以及信息守恒的缝隙，是主要风险点。泛化性方面，当前方案仍深耦合于 Deliver Pro 的 5-Phase 流水线语义，距离"换一个域也成立"有显著距离。

---

## 二、逐条评审

### P0-1：phase_deriver.py 第 88-117 行 —— 规则引擎思维残留：硬编码 phase 映射链

**证据**：`derive_phase()` 函数中：
```python
if manifest_file.exists() and final_dir.exists():  # 第88行
    ...
if (stages_dir / "validation_result.json").exists():  # 第97行
    return PHASE_PACKAGING
if (stages_dir / "integrated_draft" / "DELIVERABLE.md").exists():  # 第100行
    return PHASE_VALIDATING
if plan_path.exists():  # 第103行
    ...
    return PHASE_ASSEMBLING / PHASE_GENERATING
```

**问题**：这是一个典型的"最高 artifact 胜出"规则链，本质上是 if-else 规则引擎。phase 之间的流转顺序（PENDING → GENERATING → ASSEMBLING → VALIDATING → PACKAGING → DONE）被硬编码在代码中。这不是"薄调度"，这是把调度逻辑藏在了 derive 函数里。

**AI Native 纯度**： 低。代码在做语义判断（"有 validation_result.json 就意味着可以打包"），而这个判断应该是 LLM 基于上下文做出的。

**泛化性影响**：换一个域（如投研报告流水线：数据收集 → 分析 → 撰写 → 审校 → 发布），这个 if-else 链完全不适用，需要重写。

**建议**：将 phase 流转规则外化为 LLM 可读的契约描述（如 YAML 或 JSON Schema），derive_phase 只做"文件存在性查询"，phase 判定交给 LLM。或者退一步：承认这是项目特定的规则引擎，但将其明确标记为"项目适配层"而非"通用调度层"。

---

### P0-2：orchestrator.py 第 340-420 行 —— LLM 被迫做确定性工作：_get_wp_next_action 中的 phase→action 映射

**证据**：`_get_wp_next_action()` 方法中：
```python
if phase == "PENDING":
    params = driver.step1_analyze()
    return {"wp_id": wp_id, "action": "analyze", ...}
if phase == "GENERATING":
    ok, info = driver.step2_check_analyze()
    ...
    params_list = driver.step3_workers()
    return {"wp_id": wp_id, "action": "spawn_workers", ...}
if phase == "ASSEMBLING":
    result = driver.step5_integrate()
    ...
    return {"wp_id": wp_id, "action": "validate", ...}
```

**问题**：这里代码在做"给定 phase，决定下一步 action"的确定性映射。这是典型的规则引擎逻辑——phase 到 action 的映射是 100% 确定性的，不需要 LLM 参与。但当前架构让 LLM（通过 orchestrator prompt）来"驱动"这个循环，实际上 LLM 只是在机械地调用 drive_all() 和 sessions_spawn()，没有发挥任何语义判断能力。

**AI Native 纯度**：❌ 极低。LLM 成了代码的" human-in-the-loop 外壳"，做着不需要智能的工作。

**建议**：将 phase→action 映射完全下沉到 Python 代码中（已经是了），但更重要的是——**删除 orchestrator prompt 中关于"循环调度"的所有指令**，让 pulse 的 cron 脚本直接调用 drive_all()，无需 LLM 介入。或者反过来：如果必须保留 LLM 介入点，让 LLM 做真正的语义判断（如"这个 WP 的产出质量是否足够进入下一阶段"），而不是做机械的 phase→action 映射。

---

### P1-1：phase_deriver.py 第 30 行 —— 硬编码超时阈值 WORKER_TIMEOUT_SECONDS = 1800

**证据**：
```python
WORKER_TIMEOUT_SECONDS = 1800  # 30 分钟
```

**问题**：超时阈值是业务语义（"Worker 跑多久算死"），但被硬编码为全局常量。不同 WP 的 Worker 复杂度差异巨大（有的 5 分钟，有的 2 小时），一刀切 30 分钟会导致：简单任务被过度等待，复杂任务被误杀。

**AI Native 纯度**：⚠️ 中等。代码在做业务判断，但这个判断本可以从 execution_plan.json 的 task metadata 中读取。

**建议**：将超时阈值下沉到 execution_plan.json 的 task 级别（如 `expected_duration_seconds`），derive 时按 task 取值，fallback 到全局默认值。

---

### P1-2：orchestrator.py 第 28-33 行 —— _STALE_DISPATCH_TIMEOUTS 硬编码映射

**证据**：
```python
_STALE_DISPATCH_TIMEOUTS = {
    "analyze": 1800,
    "spawn_workers": 5400,
    "validate": 1800,
    "package": 1800,
}
```

**问题**：action→timeout 的映射是硬编码的，新增 action 需要改代码。这是典型的"配置即代码"反模式。

**建议**：将超时配置外化到契约文件（如 `deliver_pro_contract.json`），orchestrator 读取契约而非内置映射。

---

### P1-3：orchestrator.py 第 350-360 行 —— 孤儿 validate 恢复逻辑中的隐式假设

**证据**：
```python
if verdict == "NOT_FOUND":
    progress_entry = self.progress.get(wp_id, {})
    last_spawned = progress_entry.get("last_spawned_action", "")
    validate_dispatched = last_spawned == "validate" or last_spawned.startswith("validate:")
    if not validate_dispatched or self._is_stale_dispatch(progress_entry, "validate"):
        # 重新分发 validate agent
```

**问题**：这里假设了"NOT_FOUND 意味着 validate agent 死了或从未被分发"。但 NOT_FOUND 也可能是 validation_result.json 路径写错了、格式损坏了、或者文件系统延迟。代码在做语义推断（"文件不存在 = agent 死了"），而这个推断应该是 LLM 基于更多上下文做出的。

**建议**：将"NOT_FOUND 原因分析"交给 LLM（提供文件系统状态、最近 pulse 记录、agent 日志等上下文），代码只做"文件存在性查询"和"按 LLM 决策执行"。

---

### P1-4：信息守恒缝隙 —— batch_progress.json 与文件系统状态可能不一致

**证据**：`orchestrator.py` 第 140-150 行 `_load_progress` / `_save_progress`：
```python
def _load_progress(self) -> dict:
    if self.progress_path.exists():
        try:
            return json.loads(self.progress_path.read_text())
        except Exception as e:
            logger.warning(f"Failed to load progress: {e}")
    return {}
```

**问题**：`batch_progress.json` 记录了"上次 spawn 了什么"，但文件系统（worker_outputs/ 下的目录/MANIFEST）才是 Worker 是否完成的真相。如果 pulse 在 write progress 和 spawn agent 之间崩溃，progress 会记录"已 spawn"但文件系统没有对应目录，导致孤儿任务无法被检测。

**信息守恒**：⚠️ 存在缝隙。progress 文件和文件系统状态可能不一致，且没有 reconcile 机制。

**建议**：每次 pulse 启动时，先做一次 reconcile：扫描文件系统中的 worker_outputs/ 目录，与 progress 记录交叉校验，标记不一致项。

---

### P2-1：泛化性 —— 方案深耦合于 Deliver Pro 的 5-Phase 语义

**证据**：整个 `phase_deriver.py` 和 `orchestrator.py` 都围绕 Deliver Pro 的特定 phase（PENDING → GENERATING → ASSEMBLING → VALIDATING → PACKAGING → DONE）设计。

**问题**：换一个域（如投研报告：数据收集 → 分析 → 撰写 → 审校 → 发布），这个模式不成立。phase 名称、artifact 路径、流转规则全部需要重写。

**建议**：将"phase 定义"和"流转规则"抽象为可配置契约（如 YAML），orchestrator 和 deriver 读取契约而非硬编码。Deliver Pro 只是契约的一个实例。

---

### P2-2："薄调度"边界模糊 —— pulse 脚本到底该有多薄？

**证据**：提案 3.1 节描述 pulse 脚本：
```
1. exec 跑 DeliverOrchestrator.pulse()
2. 读 _pulse_actions.json，逐条 sessions_spawn
3. 输出一行可见文字汇报，session 结束
```

**问题**：这里的"薄"是语义上的薄，但技术实现上 pulse 脚本仍需要理解 `_pulse_actions.json` 的格式、知道如何调用 `sessions_spawn`、处理并发上限等。这些不是"薄"，而是"薄但不简单"。

**建议**：明确 pulse 脚本的职责边界——它应该只做"调用 drive_all() → 拿到 spawn 列表 → spawn → 结束"，所有其他逻辑（并发控制、超时判断、孤儿恢复）下沉到 Python 代码中。或者更进一步：pulse 脚本就是一个 shell 命令，所有逻辑在 Python 中。

---

### P2-3：契约硬度不足 —— deliver_orchestrator.md 被废弃，但新契约在哪里？

**证据**：提案 3.2 节"新建 prompts/deliver_pulse.md"，但评审材料中未提供该文件。

**问题**：旧契约（deliver_orchestrator.md）有 800 行，定义了完整的 Wake Response Protocol、Step 0-3、铁律等。新契约（deliver_pulse.md）据说只有 40 行，但 40 行能否覆盖所有边界情况（如 pulse 重叠、并发竞态、孤儿恢复）？

**建议**：在 deliver_pulse.md 中明确定义：
1. Pulse 的输入/输出契约（文件系统路径、JSON 格式）
2. 错误处理契约（pulse 失败怎么办？重试策略？）
3. 并发契约（MAX_IN_FLIGHT 的实现方式）
4. 与旧契约的差异对照表

---

## 三、AI Native 纯度总结

| 维度 | 评分 | 说明 |
|------|------|------|
| 能力正交 | ⚠️ 中 | phase_deriver 中代码做语义判断，orchestrator 中 LLM 做机械映射，职责错位 |
| 薄调度 | ⚠️ 中 | 调度层确实薄了，但"薄"的定义模糊，边界不清 |
| 硬契约 | ✅ 高 | 文件系统作为唯一真相，契约相对清晰 |
| 规则引擎残留 | ❌ 低 | phase_deriver 的 if-else 链、orchestrator 的 phase→action 映射都是规则引擎思维 |

## 四、泛化性总结

| 维度 | 评分 | 说明 |
|------|------|------|
| 跨项目复用 | ❌ 低 | 深耦合于 Deliver Pro 的 5-Phase 语义 |
| 跨域复用 | ❌ 极低 | 换一个域（投研、设计、测试）需要重写 phase_deriver 和 orchestrator |
| 配置化程度 | ⚠️ 中 | 部分参数可配置，但核心流转规则硬编码 |

## 五、总体建议

1. **短期（本周）**：接受脉冲式调度方向，但将 P0-1 和 P0-2 标记为"已知技术债"，在 deliver_pulse.md 中明确说明"phase 判定和 action 映射当前是硬编码的，未来需外化为契约"。
2. **中期（本月）**：将 phase_deriver 的 if-else 链改造为"基于契约的推导引擎"，orchestrator 的 phase→action 映射改造为"基于契约的调度引擎"。
3. **长期（本季度）**：提取通用"脉冲式调度框架"，Deliver Pro 只是其一个插件/实例。
