# DeepFlow 版本管理体系专家评审

> **评审日期**: 2026-06-01
> **评审人**: 软件工程专家 + DevOps 架构师
> **范围**: 全项目（组件、Prompt、Cage、Contracts、运行时）
> **状态**: 建议稿，待团队 review

---

## 1. 现状诊断报告

### 1.1 问题严重性评估

| 维度 | 严重等级 | 影响 |
|------|---------|------|
| **组件级版本缺失** | 🔴 高 | 四大领域组件无独立版本标识，无法回答"当前 Solution Pro 是哪个版本" |
| **Prompt 无版本标识** | 🔴 高 | 91/93 的 .md 文件头部无版本元数据，改了之后无法追溯 |
| **运行时版本硬编码** | 🟠 中高 | `master_agent.py` L113、`orchestrator_agent.py` L73 硬编码 `"version": "4.0"`，与根 CHANGELOG 的 `0.1.2` 完全脱节 |
| **Cage 命名不一致** | 🟠 中 | `investment_v2.0.yaml` 但 `spec_pro_v2.0.yaml`（大小写/分隔符不统一）；`integrate_codegraph.yaml` 无版本号 |
| **Contract 无版本** | 🟡 中低 | `contracts/` 下仅 2/5 文件有 `> **版本**: X.X.X` 注释行 |
| **Git tag 稀少** | 🟡 中低 | 仅 `v0.1.1` 一个 tag，且对应大量未版本化的内部变更 |

**结论**：项目处于"快速迭代但缺乏可追溯性"的阶段。当前文件量（91 prompts + 6 cage active + 19 cage archive + 5 contracts + 4 domain YAML）还在可控范围，但若继续增长，版本混乱将指数级放大。

### 1.2 根因分析

1. **历史包袱**：项目从 2.0.0 起步，期间经历了大规模重构（`core/` 重组、`domains/` 模块化迁移、35 个脚本迁移等），版本标识在每次重构中被遗漏
2. **"版本号"语义不统一**：
   - 根 CHANGELOG 用 SemVer（`0.1.2`）
   - `master_agent.py` 硬编码 `"4.0"`（可能是管线阶段数，误标为 version）
   - Cage 文件用 `v2.0`、`v1.0`（不遵循 SemVer 三段式）
   - `registry.yaml` 中的 prompt 版本用 `2.1.0`、`2.0.0`、`1.0.0`（格式正确但仅存在于 YAML，不随文件）
3. **Registry 与文件脱节**：`prompts/registry.yaml` 维护了版本元数据，但这是"旁路注册"——文件本身不携带版本信息，修改文件后需手动同步 registry，容易遗漏
4. **Cage loader 容错掩盖问题**：`cage_loader.py` 的 `data.get("cage_version", "2.0")` 给了默认值，缺失版本时静默 fallback，问题被隐藏

### 1.3 已有基础设施盘点

好消息：项目已经有一些版本管理基础设施可以利用：

| 组件 | 现状 | 可利用性 |
|------|------|---------|
| `CHANGELOG.md` | 存在，Keep a Changelog 格式，当前 0.1.2 | ✅ 保留并扩展 |
| `prompts/registry.yaml` | 完整，包含 version/changelog 字段 | ✅ 扩展为版本事实源 |
| `PromptInfo.version` | 已有 `version` 字段 | ✅ 已有模型 |
| `PromptRegistry.check_version()` | 已有，基于 `packaging.version` | ✅ 已有验证逻辑 |
| `DomainContract.cage_version` | 已有 YAML 字段 | ✅ 已有模型 |
| `cage_loader.py` 版本解析 | 从 YAML 读取 `cage_version` | ⚠️ 需要 fallback 改为 raise |

---

## 2. 版本管理架构设计

### 2.1 三层版本架构

DeepFlow 需要三层独立的版本管理体系，每层有不同的语义和更新节奏：

```
┌─────────────────────────────────────────────────┐
│  Layer 1: 全局版本 (Global SemVer)               │
│  CHANGELOG.md → 0.1.3, 0.2.0, 1.0.0            │
│  Git tag: v0.1.3, v0.2.0                        │
│  范围: 整个 DeepFlow 项目                         │
│  触发: 重大特性发布 / 破坏性变更                    │
├─────────────────────────────────────────────────┤
│  Layer 2: 组件版本 (Component SemVer)             │
│  4 个领域各自独立:                                │
│    spec_pro:     2.3.0                          │
│    solution:     3.2.0                          │
│    investment:   2.0.0                          │
│    research_pro: 1.0.0                          │
│  定义在各域 domain.yaml 中                        │
│  触发: 该领域 prompt/cage/逻辑变更                │
├─────────────────────────────────────────────────┤
│  Layer 3: 文件版本 (File-level Minor Version)     │
│  每个 .md / .yaml 文件头部标识                    │
│  格式: @version: 2.1.0                          │
│  触发: 文件内容修改时递增                          │
└─────────────────────────────────────────────────┘
```

**关键设计原则**：
- 三层版本**独立递增**，不搞"一个版本号管全部"
- 全局版本 ≥ max(组件版本)（语义约束，非硬性限制）
- 文件版本只跟随所属组件版本递增

### 2.2 组件级版本管理

#### 设计：Domain YAML 作为组件版本的事实源

每个 `domains/<domain>.yaml` 增加 `component_version` 字段（三段式 SemVer）：

```yaml
# domains/solution.yaml
component_version: "3.2.0"
component_name: "Solution Pro"
domain: solution
last_updated: "2026-06-01"
# ... 其余配置不变
```

**更新规则**：
- 该领域任意 prompt/cage/logic 变更时，按 SemVer 规则递增
- 变更后更新 `CHANGELOG.md` 中对应组件版本
- 运行时从 `domain.yaml` 读取版本，替代硬编码

**组件版本矩阵**（建议从现状迁移到统一格式）：

| 组件 | 当前散见版本 | 建议统一版本 | 依据 |
|------|-------------|-------------|------|
| Spec Pro | CHANGELOG: v2.3, registry: 2.1.0, cage: 2.1 | **2.3.0** | CHANGELOG 最新 |
| Solution Pro | CHANGELOG: v3.2, registry: 2.1.0/1.0.0, cage: 1.1 | **3.2.0** | CHANGELOG 最新 |
| Investment | registry: 2.0.0, cage: 2.0 | **2.0.0** | 一致 |
| Research Pro | CHANGELOG 未提及, cage: 1.0 | **1.0.0** | 初始版本 |

### 2.3 文件级版本标识

#### 方案选择：YAML Front Matter（推荐）

对比两种方案：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A. 顶部注释 `@version`** | 不破坏 Markdown 渲染，LLM 不解析 YAML | 无结构化解析，需正则匹配 |
| **B. YAML Front Matter `---`** | 标准化，可被 `yaml.safe_load` 解析，已有生态 | `prompt_registry.py` validate() 已将其视为 warning |

**推荐：方案 B（YAML Front Matter）**，理由：
1. 已有 `registry.yaml` 就是 YAML 元数据方案，Front Matter 是其"内联化"
2. Python 可直接用 `yaml` 解析前 10 行
3. 现有 validate() 中的 "should be pure" warning 需改为白名单（只识别版本 front matter）
4. LLM 已经习惯处理 `---` 分隔符（Jekyll/Hugo/Obsidian 标准格式）

**Prompt .md 文件模板**：

```markdown
---
id: solution/planner
version: 3.2.0
component: solution
role: planner
updated: 2026-06-01
---

# Solution Planner Prompt

You are a solution planner. Create comprehensive implementation plans...
```

**Cage .yaml 文件模板**（已有结构，统一字段名）：

```yaml
# --- Cage Contract Header ---
cage_version: "2.0.0"
component: investment
status: active
---
# Investment v2.0 契约
# 投资研究引擎 — 股票/基金投资分析管线

module: investment
# ...
```

**Contract .md 文件模板**：

```markdown
---
id: contracts/cage_framework
version: 2.0.0
updated: 2026-06-01
---

# 契约笼子（Contract Cage）

> DeepFlow 质量保障系统
```

**Domain .yaml 文件模板**：

```yaml
---
component_version: "2.0.0"
component_name: "Investment"
updated: 2026-06-01
---

domain: investment
name: "投资研究"
# ... 其余不变
```

### 2.4 运行时版本感知架构

#### 利用并扩展现有 `prompt_registry.py`

当前 `PromptRegistry` 已有 `version` 字段、`check_version()` 方法、`validate()` 方法。需要扩展：

```python
class PromptRegistry:
    # ... 现有代码不变 ...
    
    def load_with_version(self, prompt_id: str) -> tuple[str, str]:
        """
        读取 prompt 内容并提取版本信息。
        支持 YAML Front Matter 和纯文本两种格式。
        
        Returns:
            (content, version)  — version 为 "unknown" 时记录 warning
        """
        info = self.get(prompt_id)
        file_path = PathConfig.resolve().base_dir / "prompts" / info.domain / info.filename
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 尝试从 Front Matter 提取版本
        version = self._extract_version_from_content(content)
        if version:
            # 校验 registry 与文件内版本一致性
            if version != info.version:
                logger.warning(
                    f"Version mismatch: registry={info.version}, "
                    f"file={version} for {prompt_id}"
                )
        
        return content, version or info.version
    
    @staticmethod
    def _extract_version_from_content(content: str) -> str | None:
        """从 YAML Front Matter 提取 version"""
        lines = content.split('\n')
        if lines[0].strip() != '---':
            return None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                break
            if line.startswith('version:'):
                return line.split(':', 1)[1].strip().strip('"\'')
        return None
```

#### 扩展 CageLoader：强制版本字段

```python
# cage_loader.py 修改建议
def _load_yaml_contract(self, path: Path) -> dict:
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    
    cage_version = data.get("cage_version") or data.get("version")
    if not cage_version:
        raise ValueError(
            f"Missing version in cage contract: {path.name}. "
            f"Add 'cage_version' field (SemVer format)."
        )
    
    return data
```

#### 修复 master_agent.py 硬编码版本

```python
# master_agent.py — 替换硬编码 "version": "4.0"

def _get_deepflow_version() -> str:
    """从 CHANGELOG.md 或 __init__.py 读取当前全局版本"""
    changelog = PathConfig.resolve().base_dir / "CHANGELOG.md"
    if changelog.exists():
        with open(changelog, 'r') as f:
            for line in f:
                # 匹配 ## [0.1.3] 格式的最近版本号
                m = re.match(r'^## \[(\d+\.\d+\.\d+)\]', line)
                if m:
                    return m.group(1)
    return "unknown"

# 使用处
plan = {
    "session_id": session_id,
    "version": _get_deepflow_version(),  # 替代硬编码 "4.0"
    # ...
}
```

#### 运行时版本日志

每次 Pipeline 执行时，在 Blackboard 输出 `version_snapshot.json`：

```json
{
  "global_version": "0.1.3",
  "components": {
    "investment": "2.0.0",
    "spec_pro": "2.3.0",
    "solution": "3.2.0",
    "research_pro": "1.0.0"
  },
  "prompts_loaded": {
    "investment/planner": "2.0.0",
    "investment/researcher_finance": "2.0.0",
    "system/data_manager_agent": "1.0.0"
  },
  "cage_loaded": {
    "investment": "2.0.0"
  },
  "session_id": "xxx",
  "timestamp": "2026-06-01T08:15:00+08:00"
}
```

---

## 3. 具体实施方案

### 3.1 版本标识格式规范

**统一使用 YAML Front Matter**，所有 `.md` 和 `.yaml` 文件遵循：

```
---
<key>: <value>
---
<原有内容>
```

**必填字段**：
| 字段 | 说明 | 格式 |
|------|------|------|
| `version` / `cage_version` / `component_version` | 版本号（择一） | SemVer `X.Y.Z` |
| `updated` | 最后更新日期 | `YYYY-MM-DD` |

**可选字段**：
| 字段 | 说明 |
|------|------|
| `id` | 唯一标识（如 `solution/planner`） |
| `component` | 所属组件（如 `solution`） |
| `role` | 角色（Prompt 专用） |

### 3.2 目录/文件命名规范

**Cage 文件命名规范**：

```
cage/active/
  {component}_{component_version}.yaml    ← 领域契约
  {domain}_v{major}.{minor}.yaml          ← 历史保留（归档时重命名）

cage/archive/
  {component}_v{major}.{minor}.yaml       ← 已废弃版本
```

**规则**：
- 文件名中的版本号**仅供参考**，事实源是文件内的 `cage_version` 字段
- 文件名版本与文件内版本不一致时，以文件内为准，并记录 warning
- 新增 active cage 文件时，不强制在文件名中嵌入版本号（减少重命名负担）

**Prompt 文件**：
- 保持现有命名（不加 `_vX.Y` 后缀），版本信息在 Front Matter 中
- 仅当**语义破坏性变更**需要并存新旧版本时，才用 `_v2` 后缀（如 `planner_v2_harness.md`）

### 3.3 CHANGELOG 层级结构

保持单 `CHANGELOG.md`，但增加**组件版本锚点**：

```markdown
## [0.2.0] - 2026-06-15

### Component Versions
- Spec Pro: 2.3.0 → 2.4.0
- Solution Pro: 3.2.0 → 3.3.0
- Investment: 2.0.0 (no change)
- Research Pro: 1.0.0 (no change)

### Added
- **Spec Pro v2.4**: ...

### Changed
- **Solution Pro**: ...
```

不引入组件级独立 CHANGELOG（增加维护成本），而是用 `CHANGELOG.md` 中的 `### Component Versions` 块作为快速索引。

### 3.4 运行时版本注册表设计

**扩展 `PromptRegistry`**，增加三个新方法：

```python
class PromptRegistry:
    # ... existing ...
    
    def get_version_snapshot(self) -> dict:
        """
        生成当前所有已注册 prompt 的版本快照。
        输出可直接写入 version_snapshot.json。
        """
        snapshot = {
            "prompts": {},
            "warnings": []
        }
        for prompt_id, info in self._prompts_by_id.items():
            snapshot["prompts"][prompt_id] = info.version
        return snapshot
    
    def report_version_drift(self) -> list[dict]:
        """
        检测 registry.yaml 中声明的版本与文件 Front Matter 中的版本是否一致。
        """
        drifts = []
        base_path = PathConfig.resolve().base_dir
        for prompt_id, info in self._prompts_by_id.items():
            file_path = base_path / "prompts" / info.domain / info.filename
            if not file_path.exists():
                continue
            with open(file_path, 'r') as f:
                content = f.read()
            file_version = self._extract_version_from_content(content)
            if file_version and file_version != info.version:
                drifts.append({
                    "prompt_id": prompt_id,
                    "registry_version": info.version,
                    "file_version": file_version
                })
        return drifts
    
    def upgrade_registry_from_files(self) -> int:
        """
        扫描所有 prompt 文件的 Front Matter，更新 registry.yaml 中的版本号。
        用于迁移脚本或定期同步。
        
        Returns: 更新的条目数
        """
        # 实现略：读取 registry.yaml → 对比文件版本 → 写回
        pass
```

### 3.5 Git Tag / Release 策略

| 事件 | 全局版本 | Git Tag | 组件版本 |
|------|---------|---------|---------|
| 修复 bug / 文档 | Patch: 0.1.2 → 0.1.3 | `v0.1.3` | 不变 |
| 某组件新增功能 | Minor: 0.1.3 → 0.2.0 | `v0.2.0` | 该组件 Minor++ |
| 破坏性变更 / 架构升级 | Major: 0.x → 1.0.0 | `v1.0.0` | 相关组件 Major++ |
| 仅内部重构 | 不变 | 无 tag | 不变 |

**Release 流程**（手动执行，暂不引入 CI）：
1. 更新受影响组件的 `component_version`（在 `domains/*.yaml`）
2. 给变更的 prompt/cage 文件更新 Front Matter `version` + `updated`
3. 更新 `CHANGELOG.md`
4. `git tag -a v0.1.3 -m "Release 0.1.3"`
5. `git push origin v0.1.3`

---

## 4. 迁移计划

### 4.1 Phase 1：补版本标识（1 天）

**自动化脚本** `scripts/migrate_version_headers.py`：

```python
#!/usr/bin/env python3
"""
DeepFlow 版本标识迁移脚本
为所有 prompt/cage/contract 文件添加 YAML Front Matter
"""
import yaml
from pathlib import Path

DEEPFLOW_BASE = Path(__file__).parent.parent

def migrate_prompts():
    """为 prompts/ 目录下所有 .md 文件添加 Front Matter"""
    registry_path = DEEPFLOW_BASE / "prompts" / "registry.yaml"
    with open(registry_path) as f:
        registry = yaml.safe_load(f)
    
    migrated = 0
    for domain, domain_data in registry.get("domains", {}).items():
        for prompt_id, prompt_data in domain_data.get("prompts", {}).items():
            filename = prompt_data.get("filename")
            version = prompt_data.get("version", "1.0.0")
            role = prompt_data.get("role", "unknown")
            
            # 从 domains/ 和 prompts/ 两个位置查找
            candidates = [
                DEEPFLOW_BASE / "prompts" / domain / filename,
                DEEPFLOW_BASE / "domains" / domain / "prompts" / filename,
            ]
            
            for filepath in candidates:
                if filepath.exists():
                    content = filepath.read_text()
                    # 跳过已有 Front Matter 的文件
                    if content.startswith("---"):
                        continue
                    
                    front_matter = (
                        f"---\n"
                        f"id: {domain}/{prompt_id}\n"
                        f"version: \"{version}\"\n"
                        f"component: {domain}\n"
                        f"role: {role}\n"
                        f"updated: \"{prompt_data.get('updated', '')}\"\n"
                        f"---\n\n"
                    )
                    filepath.write_text(front_matter + content)
                    migrated += 1
                    print(f"  ✓ {filepath.relative_to(DEEPFLOW_BASE)} → v{version}")
                    break
    
    print(f"\nMigrated {migrated} prompt files")

def migrate_cage():
    """为 cage/active/ 下的 YAML 文件补全 cage_version 字段"""
    cage_dir = DEEPFLOW_BASE / "cage" / "active"
    migrated = 0
    for filepath in sorted(cage_dir.glob("*.yaml")):
        content = filepath.read_text()
        data = yaml.safe_load(content)
        
        if not data.get("cage_version") and not data.get("version"):
            # 从文件名推断版本
            import re
            m = re.search(r'_v(\d+\.\d+)', filepath.stem)
            version = f"{m.group(1)}.0" if m else "1.0.0"
            
            # 在文件头部插入
            lines = content.split("\n")
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith("#"):
                    insert_pos = i + 1
                elif line.strip():
                    break
            
            header = f"cage_version: \"{version}\"\n"
            new_content = "\n".join(lines[:insert_pos] + [header] + lines[insert_pos:])
            filepath.write_text(new_content)
            migrated += 1
            print(f"  ✓ {filepath.name} → cage_version: {version}")
    
    print(f"\nMigrated {migrated} cage files")

def migrate_contracts():
    """为 contracts/ 下的 .md 文件添加 Front Matter"""
    contracts_dir = DEEPFLOW_BASE / "contracts"
    migrated = 0
    for filepath in sorted(contracts_dir.glob("*.md")):
        content = filepath.read_text()
        if content.startswith("---"):
            continue
        
        # 尝试从内容中提取版本
        import re
        m = re.search(r'>\s*\*\*版本\*\*:\s*(\d+\.\d+\.\d+)', content)
        version = m.group(1) if m else "1.0.0"
        
        contract_id = filepath.stem
        front_matter = (
            f"---\n"
            f"id: contracts/{contract_id}\n"
            f"version: \"{version}\"\n"
            f"updated: \"2026-06-01\"\n"
            f"---\n\n"
        )
        filepath.write_text(front_matter + content)
        migrated += 1
        print(f"  ✓ {filepath.name} → v{version}")
    
    print(f"\nMigrated {migrated} contract files")

if __name__ == "__main__":
    print("=== Prompt Migration ===")
    migrate_prompts()
    print("\n=== Cage Migration ===")
    migrate_cage()
    print("\n=== Contract Migration ===")
    migrate_contracts()
```

**迁移预期结果**：

| 文件类型 | 数量 | 来源 | 版本取值 |
|---------|------|------|---------|
| Prompt .md | ~80 | `registry.yaml` + 未注册的 (architecture/code/general/system) | registry 已有 → 用 registry；无 registry → `1.0.0` |
| Cage .yaml | 6 | `cage/active/` | 文件名提取 / 默认 `1.0.0` |
| Contract .md | 5 | `contracts/` | 内容中提取 / 默认 `1.0.0` |
| Domain .yaml | 4 | `domains/*.yaml` | 从现有 Version 注释转换 |

### 4.2 Phase 2：运行时适配（0.5 天）

修改以下文件：

1. **`core/prompt_registry.py`**
   - `_extract_version_from_content()` — 新增
   - `load_with_version()` — 新增
   - `validate()` — 修改 Front Matter 从 warning 改为白名单识别

2. **`core/cage/cage_loader.py`**
   - 加载时检查 `cage_version` 字段，缺失时 raise 而非 fallback

3. **`core/orchestrator/master_agent.py`**
   - 删除硬编码 `"version": "4.0"`
   - 改用 `_get_deepflow_version()` 或从 `domains/investment.yaml` 读取 `component_version`

4. **`core/orchestrator/orchestrator_agent.py`**
   - 同上

### 4.3 Phase 3：版本快照输出（0.5 天）

在 Pipeline 启动时写入 `version_snapshot.json`：

```python
# 在 master_agent.py 或 orchestrator_agent.py 的初始化阶段
def write_version_snapshot(session_id: str):
    snapshot = {
        "global_version": _get_deepflow_version(),
        "components": _load_component_versions(),
        "prompts_loaded": PromptRegistry().get_version_snapshot(),
        "cage_loaded": CageLoader().get_version_snapshot(),
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }
    path = f"{DEEPFLOW_BASE}/blackboard/{session_id}/version_snapshot.json"
    with open(path, 'w') as f:
        json.dump(snapshot, f, indent=2)
```

### 4.4 迁移期间兼容策略

| 场景 | 策略 |
|------|------|
| 无 Front Matter 的文件 | 读取版本降级为 `registry.yaml` 中的值；两者都无则为 `"unknown"`，记录 warning |
| Front Matter 与 registry 不一致 | 以 Front Matter 为准，log warning |
| Cage 无 `cage_version` | Phase 2 前：fallback `"2.0"`（现有行为）；Phase 2 后：raise 阻止加载 |
| 文件名带 `_v2` 后缀 | 保留兼容，新版本不再强制后缀命名 |

---

## 5. 风险与注意事项

### 5.1 复杂度评估

**额外负担**（每次修改文件时）：

| 操作 | 耗时 | 说明 |
|------|------|------|
| 更新文件 Front Matter `version` + `updated` | ~10 秒 | 改一行数字 |
| 更新 `registry.yaml`（如果改了 prompt） | ~30 秒 | 改一行数字 |
| 更新 `CHANGELOG.md` | ~1 分钟 | 写一句话 |

**结论**：单次文件变更的额外负担约 **1.5 分钟**。考虑到 120+ 文件的年变更频率（假设每月 10 次变更），全年额外耗时约 3 小时。收益是可追溯性从 0 → 100%。

### 5.2 平衡可追溯性与轻量性

**Do（轻量做法）**：
- ✅ 版本标识只写 `version` + `updated` 两个必填字段
- ✅ 不要求每个文件独立 `changelog` 数组（已有 registry 和 CHANGELOG.md）
- ✅ 不引入版本号自动生成工具（人类手动改一行数字即可）
- ✅ 不要求文件名包含版本号（减少重命名负担）

**Don't（过度设计）**：
- ❌ 不要给每个文件生成独立的 changelog
- ❌ 不要引入版本号自动递增的 CI pipeline（当前阶段太早）
- ❌ 不要给每个 prompt 文件生成独立的 VERSION 文件
- ❌ 不要强制 `git commit --amend` 来对齐版本号和 commit

### 5.3 LLM Agent 兼容性

- YAML Front Matter 是标准格式，主流 LLM 都能正确理解和忽略
- `prompt_registry.py` 的 `validate()` 已有对 `---` 的检测逻辑，改为白名单即可
- 运行时版本信息输出为 `version_snapshot.json`，Agent 可读取用于调试

### 5.4 回滚策略

迁移脚本 `migrate_version_headers.py` 是**幂等的**：
- 已有 Front Matter 的文件会被跳过（`if content.startswith("---"): continue`）
- 如需回滚，用 git revert 即可（脚本在 git 管理下运行）

### 5.5 未来演进方向

| 阶段 | 时间 | 方向 |
|------|------|------|
| 当前（v0.1.x） | 现在 | 手动版本标识 + registry 同步 |
| v0.2.x | 未来 | `version_snapshot.json` 自动化 + drift 检测 CI |
| v1.0.0 | 成熟期 | Git hook 自动递增 + release notes 自动生成 |

---

## 附录 A：文件模板示例

### A.1 Prompt 文件（.md）

```markdown
---
id: investment/planner
version: "2.0.0"
component: investment
role: planner
updated: "2026-06-01"
---

# Investment Planner Prompt

You are an investment research planner. Create comprehensive research plans
for the given company across multiple dimensions.

## Input
- Company code: {{COMPANY_CODE}}
- Company name: {{COMPANY_NAME}}
- Industry: {{INDUSTRY}}

## Instructions
...
```

### A.2 Cage 文件（.yaml）

```yaml
cage_version: "2.0.0"
component: investment
status: active
module: investment
# 投资研究引擎 — 股票/基金投资分析管线

created: "2026-05-30"
updated: "2026-06-01"
complexity: complex

description: |
  Investment 是 DeepFlow 的投资研究引擎。
  ...

interface:
  input:
    required: [code, name]
  output:
    required: [report, score]

behavior:
  stages:
    required_order:
      - data_collection
      - planning
      - research
      - audit
      - fix
      - summarize
  ...
```

### A.3 Contract 文件（.md）

```markdown
---
id: contracts/cage_framework
version: "2.0.0"
updated: "2026-06-01"
---

# 契约笼子（Contract Cage）

> DeepFlow 2.0.0 单个模块开发质量保障系统

## 一、契约笼子的四层约束

...
```

### A.4 Domain 配置文件（.yaml）

```yaml
---
component_version: "2.0.0"
component_name: "Investment"
updated: "2026-06-01"
---

domain: investment
name: "投资研究"
description: "股票/基金投资分析，包括财务研究、技术分析、市场研究、风险评估"

context:
  schema:
    required: ["code", "name"]
    optional: ["price", "market", "industry"]

agents:
  - role: data_manager
    prompt: "prompts/data_manager_agent.md"
    timeout: 300
  ...
```

## 附录 B：迁移后验证清单

- [ ] 所有 `prompts/**/*.md` 文件头部有 `---` Front Matter
- [ ] 所有 `cage/active/*.yaml` 文件有 `cage_version` 字段
- [ ] 所有 `contracts/*.md` 文件头部有 `---` Front Matter
- [ ] 所有 `domains/*.yaml` 文件有 `component_version` 字段
- [ ] `prompt_registry.py` 的 `validate()` 不再对 Front Matter 报 warning
- [ ] `cage_loader.py` 加载缺失版本的文件时 raise（非 fallback）
- [ ] `master_agent.py` / `orchestrator_agent.py` 不再硬编码 `"4.0"`
- [ ] `git tag v0.1.3` 已创建
- [ ] 执行一次 Pipeline，验证 `version_snapshot.json` 正确生成

## 附录 C：现状 vs 目标对照表

| 维度 | 现状 | 目标 |
|------|------|------|
| 组件版本 | CHANGELOG 中散见，无统一事实源 | `domains/*.yaml` 中 `component_version` |
| Prompt 版本 | 仅 registry.yaml 中有，文件本身无标识 | 文件 Front Matter + registry 双写 |
| Cage 版本 | 文件名带版本号但不统一，部分无版本字段 | 文件内 `cage_version` 为事实源 |
| Contract 版本 | 2/5 有版本注释 | 全部有 Front Matter |
| 运行时感知 | 硬编码 `"4.0"` | 从 CHANGELOG + domain.yaml 动态读取 |
| 结果追溯 | 无法追溯 | `version_snapshot.json` 每次执行记录 |
| Git tag | 仅 v0.1.1 | 每次 release 打 tag |
| 迁移工具 | 无 | `scripts/migrate_version_headers.py` |
