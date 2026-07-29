# ADR-009 Solution Pro MD-First 完全改造计划

> 日期: 2026-07-29
> 目标: Solution Pro 完完全全改成 MD-first（MD 是唯一真相源，JSON 退化为 ≤1KB 衍生品）
> 依据: 3 专家审计报告（综合评级 C+）+ ADR-009 原文

---

## 目标架构

```
当前（JSON-first with MD sidecar）:
  Worker → dict → bb.write_stage → .json（真相源）
                              → render → .md（衍生品/侧车）

目标（MD-first）:
  Worker → dict → render → .md（真相源）
                       → 提取索引 → .json（≤1KB 衍生品）
```

---

## 改造分 6 个 Phase，依赖链：P1 → P2 → P3 → P4 → P5 → P6

---

## Phase 1: 契约层修复 🔴 P0（前置条件：MD 必须可信）

> 不修契约，MD-first 就是空话。Round-trip 保留率必须 ≥ 95%。

### 1.1 frozen_living_md.py — 修复 5 个 HIGH 级问题

| # | 问题 | 修复方案 |
|---|------|---------|
| F1 | `schema_version` 丢失 | parse 增加 YAML frontmatter 解析 |
| F2 | `key_decisions` 类型退化 dict→str | render 改用表格保留结构化字段（decision/rationale/alternatives） |
| F3 | `risk_summary` 类型退化 dict→str | render 改用表格保留 severity/probability/mitigation |
| F4 | `implementation_phases` 类型退化 dict→str | render 改用表格保留 tasks/timeline/effort |
| F5 | `session_id` 丢失 | parse 增加 frontmatter session 解析 |

### 1.2 solution_living_md.py — 修复 2 个 HIGH 级问题

| # | 问题 | 修复方案 |
|---|------|---------|
| S1 | `full_solution` 类型不匹配（render dict, parse str） | parse 增加结构化解析（检测 dict 格式 vs 纯文本） |
| S2 | `gate_decisions` 完全丢失 | parse 增加 gate_decisions 表格解析 |

### 1.3 去除硬截断

| 位置 | 当前 | 修复 |
|------|------|------|
| solution_living_md.py | risk[:40], mitigation[:60], metadata[:80] | 去除截断或提高到 500 字符 |
| frozen_living_md.py | constraint desc[:100] | 去除截断 |

### 1.4 补充 frozen_living_md.py 测试

当前 **零测试**。需补充：
- `test_render_frozen_spec_md` — 基础渲染
- `test_parse_frozen_spec_md` — 基础解析
- `test_round_trip` — dict → MD → dict 保留率 ≥ 95%
- `test_validate_frozen_spec_md` — 校验函数
- `test_empty_fields` — 空 semantic_anchors、空 constraints
- `test_frontmatter` — schema_version + session_id 保留

**交付物**: 修复后的 frozen_living_md.py + solution_living_md.py + test_frozen_living_md.py
**验证标准**: 全部测试通过，round-trip 保留率 ≥ 95%

---

## Phase 2: 基础设施改造 🔴 P0

> write_stage / read_stage 必须原生支持 MD。

### 2.1 blackboard_manager.py — write_stage 支持 MD

```python
# 当前（硬编码 .json）:
def _stage_path(self, stage_name):
    return self._stages_dir / f"{stage_name}.json"

def write_stage(self, stage_name, data):
    # json.dump(data)

# 目标（类型感知）:
def _stage_path(self, stage_name, content_type="auto"):
    """auto: str → .md, dict → .json"""
    suffix = ".md" if content_type == "md" else ".json"
    return self._stages_dir / f"{stage_name}{suffix}"

def write_stage(self, stage_name, data, content_type="auto"):
    """
    content_type:
      - "auto": str → .md, dict/list → .json
      - "md": 强制 .md
      - "json": 强制 .json
    """
```

### 2.2 blackboard_manager.py — read_stage 支持 MD 优先

```python
# 目标: 优先读 .md，fallback 读 .json（过渡期兼容）
def read_stage(self, stage_name):
    md_path = self._stages_dir / f"{stage_name}.md"
    json_path = self._stages_dir / f"{stage_name}.json"
    if md_path.exists():
        return md_path.read_text()
    elif json_path.exists():
        return json.load(json_path)
    return None
```

### 2.3 STAGE_PATH_REGISTRY 更新

将交付物 stage 的注册路径从 `.json` → `.md`：
- `final_solution` → `final_solution.md`
- `frozen_spec` → `frozen_spec.md`
- `solution_document` → `solution_document.md`

**交付物**: 修改后的 blackboard_manager.py
**验证标准**: 现有 470+ tests 全部通过（向后兼容）

---

## Phase 3: 执行层迁移 🔴 P0

> MD 从"可选侧车"变为"主写入路径"。

### 3.1 __init__.py — 写入顺序翻转

```python
# 当前（JSON 主写 + MD 侧车）:
bm.write_stage('final_solution', solution_dict)        # ← JSON 真相源
md = render_final_solution_md(solution_dict)
bm.write('final_solution.md', md)                       # ← MD 侧车（失败不阻断）

# 目标（MD 主写 + JSON 衍生品）:
md = render_final_solution_md(solution_dict)
bm.write_stage('final_solution', md, content_type="md") # ← MD 真相源
index = extract_index(solution_dict)                      # ≤1KB
bm.write_stage('final_solution_index', index)            # ← JSON 衍生品
```

### 3.2 __init__.py — frozen_spec 同理

```python
# 当前:
bm.write("data/frozen_spec.json", frozen_spec)
bm.write("data/frozen_spec.md", render_frozen_spec_md(frozen_spec))

# 目标:
bm.write("data/frozen_spec.md", render_frozen_spec_md(frozen_spec))  # ← 真相源
# JSON 衍生品可选生成（Gate 仪表盘用）
```

### 3.3 render 失败从"log ERROR"变为"raise"

```python
# 当前:
except Exception as e:
    logging.error(f"MD render failed: {e}")  # 不阻断

# 目标:
# MD render 失败 → raise ValueError（ADR-009 契约违反）
```

**交付物**: 修改后的 __init__.py
**验证标准**: E2E 运行 Solution Pro，验证 MD 文件存在且可被 parse 还原

---

## Phase 4: Prompt 迁移 🟡 P1

> 12+ prompt 文件引用 JSON，必须全部改为 MD。

### 4.1 需要修改的 Prompt 文件

| 文件 | 当前引用 | 改为 |
|------|---------|------|
| `orchestrator.md` | `stages/final_solution.json` × 2 | `stages/final_solution.md` |
| `orchestrator.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `summary_module.md` | `stages/final_solution.json` | `stages/final_solution.md` |
| `summary_json_extractor.md` | `data/frozen_spec.json` × 4 | `data/frozen_spec.md` |
| `summary_refiner.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `summary_summarizer.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `summary_review_layer_b.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `summary_harness_check.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `reviewer_convergence.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `reviewer_meta.md` | `data/frozen_spec.json` | `data/frozen_spec.md` |
| `meta_planner.md` | `data/frozen_spec.json` × 2 | `data/frozen_spec.md` |
| `planning_module.md` | `data/frozen_spec.json` × 2 | `data/frozen_spec.md` |
| `solution_pulse.md` | `stages/final_solution.json` | `stages/final_solution.md` |

### 4.2 summary_json_extractor.md 特殊处理

这个 prompt 的核心原则需要翻转：
```
当前: "JSON 只包含轻量级结构化元数据（~1KB 衍生品）。完整方案的 source of truth 是 data/frozen_spec.json"
目标: "MD 是完整方案的 source of truth。JSON 是 ≤1KB 衍生品，仅放索引/摘要"
```

### 4.3 read_json → read_stage / parse_md

```python
# 当前:
spec = bb.read_json('data/frozen_spec.json', default={})

# 目标:
spec_md = bb.read_stage('frozen_spec')  # 返回 MD 字符串
spec = parse_frozen_spec_md(spec_md)     # MD → dict
```

**交付物**: 12+ 修改后的 prompt 文件
**验证标准**: grep 确认无 `.json` 残留引用（交付物相关）

---

## Phase 5: 跨域消费迁移 🟡 P1

> Ship Pro 必须从 frozen_spec.md 读取，不再读 frozen_spec.json。

### 5.1 ship_orchestrator.py

```python
# 当前（ship_orchestrator.py:1502-1508）:
frozen_spec = bb.read_json('data/frozen_spec.json')
requirements = frozen_spec.get('requirements', [])

# 目标:
frozen_spec_md = bb.read_stage('frozen_spec')  # 读 MD
frozen_spec = parse_frozen_spec_md(frozen_spec_md)  # MD → dict
requirements = frozen_spec.get('requirements', [])
```

### 5.2 spawn_params_contract.py

```python
# 当前（spawn_params_contract.py:136-137）:
frozen_spec = bb.read_json('data/frozen_spec.json')

# 目标:
frozen_spec_md = bb.read_stage('frozen_spec')
frozen_spec = parse_frozen_spec_md(frozen_spec_md)
```

### 5.3 其他跨域消费点

搜索全域 `frozen_spec.json` 引用，逐一迁移。

**交付物**: ship_pro 修改后的消费代码
**验证标准**: Ship Pro 能正常从 MD 读取并解析 frozen_spec

---

## Phase 6: 清理 + 防回归 🟡 P1

### 6.1 删除 JSON 主写入逻辑

- 删除 `bm.write("data/frozen_spec.json", ...)` 双写代码
- 删除 `render_solution_md()` 的 try/except 吞错误逻辑
- 保留 `read_stage()` 的 JSON fallback（过渡期，后续删除）

### 6.2 测试迁移

- `test_verification_constraints.py:150`: `load_stage("final_solution.json")` → `.md`
- `test_v6_improvements.py`: 从 `final_result.json` → `final_result.md`
- 新增 MD-first E2E 测试：验证 MD 写入 → parse → 下游消费 全链路

### 6.3 防回归 CI 检查

```python
# 新增 CI 检查:
# 1. 交付物 stage 不允许 .json 写入（只允许 .md）
# 2. Prompt 不允许引用交付物 .json 路径
# 3. round-trip 保留率 ≥ 95%
```

---

## 依赖关系 & 执行顺序

```
Phase 1 (契约修复)
    ↓
Phase 2 (基础设施) ← 依赖 Phase 1（MD 可信才能改基础设施）
    ↓
Phase 3 (执行层) ← 依赖 Phase 2（基础设施支持才能切主路径）
    ↓
Phase 4 (Prompt) ← 可与 Phase 3 并行
Phase 5 (跨域) ← 依赖 Phase 3（MD 写入后才能改消费端）
    ↓
Phase 6 (清理) ← 全部完成后
```

## 工作量估算

| Phase | 改动文件数 | 复杂度 | 预估时间 |
|-------|----------|--------|---------|
| P1 契约修复 | 3 | 中 | 30min |
| P2 基础设施 | 1 | 中 | 20min |
| P3 执行层 | 1 | 中 | 20min |
| P4 Prompt | 12+ | 低（批量替换） | 15min |
| P5 跨域 | 2-3 | 低 | 10min |
| P6 清理 | 3-5 | 低 | 15min |
| **合计** | **~25** | — | **~2h** |

## 风险

| 风险 | 缓解 |
|------|------|
| Phase 2 改 blackboard_manager 影响全域 | 向后兼容：dict 仍写 .json，str 写 .md |
| Phase 4 Prompt 改漏 | grep 扫描 + CI 检查 |
| Phase 5 Ship Pro 解析失败 | 保留 JSON fallback 过渡 |
| Round-trip 信息丢失 | Phase 1 先修到 ≥ 95% |

## 验证标准（全部满足 = 改造完成）

- [ ] frozen_living_md round-trip 保留率 ≥ 95%
- [ ] solution_living_md round-trip 保留率 ≥ 95%
- [ ] write_stage 支持 MD 写入
- [ ] MD 是主写入路径（JSON 是衍生品）
- [ ] 所有 Prompt 引用 .md 而非 .json（交付物相关）
- [ ] Ship Pro 从 MD 读取 frozen_spec
- [ ] 470+ tests 全部通过
- [ ] E2E 运行 Solution Pro → 验证 MD 产物
