# Solution Pro MD+Track 架构实施计划

> **版本**: V1.0 | **日期**: 2026-07-29  
> **目标**: 在 ADR-009 MD-first 基础上，设计轻量 Track 系统  
> **前置**: ADR-009 Phase 1-6 已完成（MD-first 改造完成）

---

## 1. 背景与目标

### 1.1 当前状态（ADR-009 完成后）

| 层级 | 状态 | 说明 |
|------|:----:|------|
| **MD 主写入** | ✅ 完成 | frozen_spec.md, final_solution.md, solution_document.md |
| **JSON fallback** | ⚠️ 部分残留 | post_validator.py 仍有 read_json 硬编码 |
| **Track 系统** | ❌ 未设计 | 当前只有基础 track.json（gate_summary, metrics） |

### 1.2 目标架构

```
┌─────────────────────────────────────────┐
│  Layer 1: MD（Source of Truth）          │
│  • frozen_spec.md                       │
│  • final_solution.md                    │
│  • solution_document.md                 │
└─────────────────────────────────────────┘
                    ↓ 自动提取
┌─────────────────────────────────────────┐
│  Layer 2: Track（Derived Metadata）      │
│  • solution_track.json (~1.5KB)         │
│  • gate_summary + metrics + summary     │
│  • semantic_anchors（跨域元数据）        │
│  • anchors（章节行号）                   │
└─────────────────────────────────────────┘
```

### 1.3 核心设计原则

| 原则 | 说明 |
|------|------|
| **MD 是唯一真相源** | Track 是从 MD 自动提取的"视图"，不是独立数据 |
| **Track 轻量** | ~1.5KB，只包含确定性指标 + 跨域元数据 |
| **Track 自动生成** | MD 写入后必须同步生成 Track |
| **Track 只读** | 任何系统不能直接写 Track，只能从 MD 提取 |

---

## 2. 实施 Phase 划分

### Phase 1: 清理 JSON 残留（P0）

**目标**: 删除所有 JSON fallback 路径，纯 MD 流转

| 任务 | 文件 | 动作 | 验证 |
|------|------|------|------|
| 删除 frozen_spec.json fallback | `post_validator.py` | 改用 `read_stage` | grep 无残留 |
| 删除 final_solution.json fallback | `ship_pro/__init__.py` | 只读 `.md` | grep 无残留 |
| 删除 master_state.json | `__init__.py` | 统一用 `.runs/*.run.json` | grep 无残留 |

**交付物**: 修改后的代码文件  
**验证标准**: `grep -rn "frozen_spec\.json\|final_solution\.json\|master_state" domains/solution_pro/` 返回 0

**预估时间**: 30min

---

### Phase 2: 扩展 Track Schema（P0）

**目标**: 添加 solution_specific 字段，支持轻量 Track

| 任务 | 文件 | 动作 | 验证 |
|------|------|------|------|
| 扩展 extract_track_json | `core/md_track_extractor.py` | 添加 solution_specific 提取 | 单元测试通过 |
| 添加 semantic_anchors 提取 | `core/md_track_extractor.py` | 从 MD 列表提取 | 单元测试通过 |
| 添加 summary 统计 | `core/md_track_extractor.py` | key_decisions_count, phases_count, risk_count | 单元测试通过 |
| 添加 constraint_coverage | `core/md_track_extractor.py` | 计算覆盖率 | 单元测试通过 |

**Track Schema 设计**:

```json
{
  "schema_version": "3.1.0",
  "domain": "solution_pro",
  "source_file": "final_solution.md",
  
  "gate_summary": {
    "L1_Schema": "PASS",
    "L2_Semantic": "PASS",
    "L3_Merge": "PASS"
  },
  
  "metrics": {
    "req_ids": ["REQ-001", "REQ-002"],
    "req_count": 2,
    "section_count": 8,
    "content_length": 12500
  },
  
  "summary": {
    "key_decisions_count": 5,
    "implementation_phases_count": 4,
    "risk_count": 8,
    "constraint_coverage": {
      "total": 20,
      "covered": 18,
      "ratio": 0.9
    }
  },
  
  "semantic_anchors": [
    {
      "name": "OpenTelemetry Collector",
      "category": "technology",
      "constraint": "REQ-001"
    }
  ],
  
  "anchors": {
    "meta_info": {"line": 5},
    "key_decisions": {"line": 45},
    "implementation_phases": {"line": 120}
  }
}
```

**交付物**: 修改后的 md_track_extractor.py + 单元测试  
**验证标准**: 
- 单元测试全部通过
- 生成的 solution_track.json 包含 solution_specific 字段
- Track 大小 ~1.5KB

**预估时间**: 60min

---

### Phase 3: Track 自动生成（P0）

**目标**: MD 写入后自动生成 Track

| 任务 | 文件 | 动作 | 验证 |
|------|------|------|------|
| pipeline 完成后调用 generate_solution_track | `pulse.py` | 已有，确认调用 | 集成测试 |
| Track 生成失败 = 架构违反 | `track_generator.py` | raise ValueError | 单元测试 |
| 添加 Track 完整性检查 | `track_generator.py` | 验证 solution_specific 存在 | 单元测试 |

**交付物**: 修改后的 track_generator.py + pulse.py  
**验证标准**: 
- pipeline 完成后 solution_track.json 自动生成
- Track 生成失败时 raise ValueError

**预估时间**: 30min

---

### Phase 4: Ship Pro 改用 Track（P1）

**目标**: Ship Pro 读取 solution_track.json 获取跨域元数据

| 任务 | 文件 | 动作 | 验证 |
|------|------|------|------|
| Ship Pro 读取 solution_track.json | `ship_pro/__init__.py` | 从 track 获取 semantic_anchors | 集成测试 |
| Ship Pro 读取 req_ids | `ship_pro/pipeline_designer.py` | 从 track 获取 REQ 覆盖 | 集成测试 |

**交付物**: 修改后的 ship_pro 代码  
**验证标准**: Ship Pro 能正确读取 Track 数据

**预估时间**: 30min

---

### Phase 5: 测试与验证（P0）

**目标**: 确保全链路正确

| 任务 | 验证内容 | 方法 |
|------|---------|------|
| 单元测试 | Track 提取逻辑 | pytest |
| 集成测试 | MD → Track 全链路 | E2E 运行 Solution Pro |
| 跨域测试 | Ship Pro 读取 Track | 集成测试 |
| 回归测试 | 现有测试不 break | pytest 全量 |

**交付物**: 测试报告  
**验证标准**: 
- 所有测试通过
- 无回归

**预估时间**: 30min

---

## 3. 依赖关系与执行顺序

```
Phase 1 (清理 JSON 残留)
    ↓
Phase 2 (扩展 Track Schema) ← 依赖 Phase 1（纯 MD 环境）
    ↓
Phase 3 (Track 自动生成) ← 依赖 Phase 2（Schema 定义）
    ↓
Phase 4 (Ship Pro 改用 Track) ← 依赖 Phase 3（Track 可用）
    ↓
Phase 5 (测试与验证) ← 全部完成后
```

---

## 4. 工作量估算

| Phase | 改动文件数 | 复杂度 | 预估时间 |
|-------|:----------:|:------:|:--------:|
| P1 清理 JSON 残留 | 3 | 低 | 30min |
| P2 扩展 Track Schema | 1 | 中 | 60min |
| P3 Track 自动生成 | 2 | 低 | 30min |
| P4 Ship Pro 改用 Track | 2 | 低 | 30min |
| P5 测试与验证 | - | 中 | 30min |
| **合计** | **~8** | — | **~3h** |

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Track 提取失败 | 下游无法获取元数据 | Track 生成失败 = 架构违反，raise ValueError |
| MD 结构变化 | Track 提取逻辑失效 | MD Schema 变更时同步更新 Track 提取逻辑 |
| Ship Pro 读取 Track 失败 | 跨域传递中断 | 保留 fallback：如果 Track 不存在，直接读 MD |
| semantic_anchors 提取不准确 | 下游契约验证失败 | 单元测试覆盖多种格式 |

---

## 6. 验证标准（全部满足 = 实施完成）

- [ ] JSON 残留全部清理（grep 返回 0）
- [ ] Track Schema 扩展完成（包含 solution_specific）
- [ ] Track 自动生成（pipeline 完成后调用）
- [ ] Ship Pro 能读取 Track 数据
- [ ] 所有测试通过（单元 + 集成 + 回归）
- [ ] Track 大小 ~1.5KB（轻量）
- [ ] E2E 运行 Solution Pro → 验证 Track 产物

---

## 7. 专家评审要点

请专家重点关注：

1. **Track Schema 设计是否合理？**
   - solution_specific 字段是否足够？
   - semantic_anchors 是否应该包含在 Track 中？

2. **Track 提取逻辑是否健壮？**
   - MD 格式变化时，提取逻辑是否会失效？
   - 是否需要更灵活的提取策略？

3. **跨域传递是否可靠？**
   - Ship Pro 读取 Track 的 fallback 策略是否合理？
   - 是否需要版本化 Track Schema？

4. **测试覆盖是否充分？**
   - 是否需要更多的边界测试？
   - 是否需要性能测试？

---

*文档生成时间: 2026-07-29*  
*作者: Solution Pro Architecture Team*
