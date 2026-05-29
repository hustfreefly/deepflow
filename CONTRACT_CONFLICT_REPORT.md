# 契约冲突报告

> **检查时间**: 2026-05-29  
> **检查范围**: `DIRECTORY_STRUCTURE_CONTRACT.md` vs 18 个 cage/*.yaml 契约

---

## 冲突汇总

| # | 冲突类型 | 涉及契约 | 严重程度 | 状态 |
|---|---------|---------|---------|------|
| 1 | 技能目录命名不一致 | deepclaw_v1.0.yaml | 🟡 中 | 待解决 |
| 2 | core/spec_pro/ 归属冲突 | spec_pro_v2.0.yaml | 🔴 高 | 待解决 |
| 3 | frontend/ 目录未覆盖 | 6 个 frontend 契约 | 🔴 高 | 待解决 |
| 4 | OpenClaw skills 路径混淆 | deepclaw_v1.0.yaml | 🟡 中 | 待解决 |
| 5 | ui_polish 路径前缀缺失 | ui_polish_contract.yaml | 🟢 低 | 待解决 |

---

## 冲突 1：技能目录命名不一致

**涉及契约**: `deepclaw_v1.0.yaml`

**冲突描述**:
- **目录契约** (第 5.2 章): 技能目录应为 `skills/research-pro/`（kebab-case）
- **deepclaw_v1.0**: 引用 `skills/deep-research/`（旧名称）

**示例**:
```yaml
# deepclaw_v1.0.yaml 第 39 行
check: "grep -r 'source_registry' skills/deep-research/lib/citation_verifier.py"

# 目录契约
skills/research-pro/lib/citation_verifier.py
```

**影响范围**: deepclaw_v1.0.yaml 中有 30+ 处引用 `skills/deep-research/`

**建议处理**:
- 选项 A: 修改目录契约，接受 `deep-research` 作为历史命名
- 选项 B: 修改 deepclaw_v1.0.yaml，将所有 `deep-research` 改为 `research-pro`
- **推荐**: 选项 B（已完成重命名，契约应同步更新）

---

## 冲突 2：core/spec_pro/ 归属冲突

**涉及契约**: `spec_pro_v2.0.yaml`

**冲突描述**:
- **目录契约** (第 8.1 章迁移规则 P1): `core/spec_pro/` 应移至 `domains/spec_pro/`
- **spec_pro_v2.0**: 所有路径仍引用 `core/spec_pro/`

**示例**:
```yaml
# spec_pro_v2.0.yaml 第 88 行
path: "core/spec_pro/coordinator.py"

# 目录契约迁移规则
P1 | core/spec_pro/ 移至 domains/spec_pro/
```

**影响范围**: spec_pro_v2.0.yaml 中有 10+ 处引用 `core/spec_pro/`

**建议处理**:
- 选项 A: 执行目录契约的 P1 迁移，然后更新 spec_pro_v2.0.yaml
- 选项 B: 取消迁移计划，修改目录契约允许 `core/spec_pro/` 存在
- **推荐**: 选项 A（符合分层架构原则，spec_pro 是业务域不是基础设施）

---

## 冲突 3：frontend/ 目录未覆盖

**涉及契约**: 6 个 frontend 相关契约

**冲突描述**:
- **目录契约** (第 2.1 章): 根目录列表中**没有** `frontend/`
- **6 个契约**: 大量引用 `frontend/backend/` 和 `frontend/web/`

**涉及的契约**:
1. `frontend_completion_v1.0.yaml` - 引用 `frontend/backend/routers/`, `frontend/README.md`
2. `frontend_phase1_contract.yaml` - 引用 `frontend/backend/`, `frontend/web/`
3. `frontend_phase5_client_v1.0.yaml` - 引用 `frontend/web/src/`
4. `frontend_webhook_fix_v1.0.yaml` - 引用 `frontend/backend/routers/`
5. `frontend_webhook_integration_contract.yaml` - 引用 `web/vite.config.ts`
6. `frontend_webhook_integration_v1.0.yaml` - 引用 `frontend/backend/`

**示例**:
```yaml
# frontend_phase1_contract.yaml 第 31 行
Vite + React 18 + TypeScript project under frontend/web/

# 目录契约第 2.1 章
.deepflow/ 根目录中没有 frontend/
```

**影响范围**: 6 个契约，30+ 处引用

**建议处理**:
- 选项 A: 在目录契约中添加 `frontend/` 为合法根目录
- 选项 B: 将 `frontend/` 标记为"独立项目"，不受目录契约约束
- **推荐**: 选项 A（frontend 是 DeepFlow 的组成部分，应该纳入目录契约）

**修改建议**:
```markdown
.deepflow/
├── frontend/                # 前端界面
│   ├── backend/             # FastAPI 后端
│   └── web/                 # React 前端
```

---

## 冲突 4：OpenClaw skills 路径混淆

**涉及契约**: `deepclaw_v1.0.yaml`

**冲突描述**:
- **目录契约** (第 1.2 章): 适用范围包括 `skills/` 目录下的 DeepFlow 技能
- **deepclaw_v1.0**: 引用 `skills/stock-analysis/`、`skills/market-analysis-cn/` 等

**问题**: 这些是 **OpenClaw workspace skills**（位于 `workspace/skills/`），不是 **DeepFlow skills**（位于 `.deepflow/skills/`）

**示例**:
```yaml
# deepclaw_v1.0.yaml 第 511 行
skill_path: "skills/stock-analysis/"

# 实际位置
/Users/allen/.openclaw/workspace/skills/stock-analysis/  # OpenClaw skill
/Users/allen/.openclaw/workspace/.deepflow/skills/research-pro/  # DeepFlow skill
```

**影响范围**: deepclaw_v1.0.yaml 中有 5+ 处引用 OpenClaw skills

**建议处理**:
- 选项 A: 在目录契约中明确区分两类 skills
- 选项 B: 修改 deepclaw_v1.0.yaml，使用绝对路径或明确标记
- **推荐**: 选项 A（在契约中说明 DeepFlow 技能 vs OpenClaw 技能的区别）

**修改建议**:
```markdown
### 5.1 技能类型区分

DeepFlow 项目涉及两类技能：

| 类型 | 位置 | 说明 |
|------|------|------|
| DeepFlow Skills | `.deepflow/skills/` | DeepFlow 内部技能 |
| OpenClaw Skills | `workspace/skills/` | OpenClaw 生态技能 |

本契约主要规范 DeepFlow Skills。OpenClaw Skills 遵循 OpenClaw 规范。
```

---

## 冲突 5：ui_polish 路径前缀缺失

**涉及契约**: `ui_polish_contract.yaml`

**冲突描述**:
- **目录契约**: 应该使用完整路径 `frontend/web/src/`
- **ui_polish_contract**: 使用相对路径 `src/App.tsx`

**示例**:
```yaml
# ui_polish_contract.yaml 第 18 行
files: ["src/App.tsx", "src/components/Header.tsx"]

# 应该是
files: ["frontend/web/src/App.tsx", "frontend/web/src/components/Header.tsx"]
```

**影响范围**: ui_polish_contract.yaml 中有 10+ 处使用相对路径

**建议处理**:
- 选项 A: 修改 ui_polish_contract.yaml，添加完整路径前缀
- 选项 B: 接受相对路径，在契约开头说明基准目录
- **推荐**: 选项 B（相对路径更简洁，只需在契约开头声明基准目录）

**修改建议**:
```yaml
# ui_polish_contract.yaml 开头添加
base_dir: "frontend/web/"
```

---

## 非冲突：路径一致的契约

以下契约与目录契约**无冲突**：

| 契约 | 状态 |
|------|------|
| deepflow_navigator_v1.0.yaml | ✅ 一致 |
| english_refactor_contract.yaml | ✅ 一致 |
| github_release_contract.yaml | ✅ 一致 |
| release_cleanup_contract.yaml | ✅ 一致 |
| update_docs_contract.yaml | ✅ 一致 |

---

## 解决优先级

| 优先级 | 冲突 | 工作量 | 建议时间 |
|--------|------|--------|----------|
| P0 | 冲突 3: frontend/ 未覆盖 | 小 | 立即 |
| P1 | 冲突 2: core/spec_pro/ 归属 | 中 | 1 周内 |
| P1 | 冲突 1: deep-research 命名 | 小 | 1 周内 |
| P2 | 冲突 4: OpenClaw skills 混淆 | 小 | 2 周内 |
| P3 | 冲突 5: ui_polish 路径前缀 | 小 | 排期 |

---

## 建议的行动计划

### 立即行动（P0）
修改 `DIRECTORY_STRUCTURE_CONTRACT.md`，添加 `frontend/` 到根目录列表。

### 1 周内（P1）
1. 执行 `core/spec_pro/` → `domains/spec_pro/` 迁移
2. 更新 `spec_pro_v2.0.yaml` 中的所有路径
3. 更新 `deepclaw_v1.0.yaml` 中的 `deep-research` → `research-pro`

### 2 周内（P2）
在目录契约中添加"技能类型区分"章节，说明 DeepFlow skills vs OpenClaw skills。

### 排期（P3）
修改 `ui_polish_contract.yaml`，在开头声明 `base_dir`。

---

**报告生成时间**: 2026-05-29 23:48  
**下一步**: 等待用户确认后执行修复
