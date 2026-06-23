# Blackboard V2 迁移方案

> **版本**: v1.0.0
> **日期**: 2026-06-22
> **状态**: 待评审
> **作者**: DeepFlow Architecture Analysis

---

## 一、当前 Blackboard 结构分析

### 1.1 目录现状

```
.deepflow/blackboard/
├── research_pro_29df4dfd_1781188482/     ← Research Pro（hash+timestamp）
│   ├── review/
│   │   ├── industry_analyst_review.md
│   │   ├── info_design_review.md
│   │   └── industry_benchmarks.md
│
├── research_pro_2ca648a3_1781180542/     ← Research Pro（另一运行）
│   └── report/
│       ├── comparison_v41_vs_v4_vs_manus.md
│       └── ...
│
└── [历史 Solution Pro 目录已归档至 archive/]
```

**当前活跃数据**：仅 2 个 Research Pro 运行目录（总计 5 个文件）。

**历史数据**：Solution Pro 和 Ship Pro 的历史运行数据已归档或清理。

### 1.2 代码引用分析

#### 1.2.1 STAGE_PATH_REGISTRY 使用方式

**定义位置**：`domains/solution_pro/blackboard.py`

```python
STAGE_PATH_REGISTRY = {
    "data_collection": "data/collection.json",
    "structured_requirements": "data/structured_requirements.json",
    "frozen_spec": "data/frozen_spec.json",
    "requirements_traceability_matrix": "requirements_traceability_matrix.json",
    "planning": "stages/planning.json",
    "reviewer_technical": "stages/reviewer_technical.json",
    # ... 共 18 个 stage
}
```

**引用文件**（共 7 个）：

| 文件 | 使用方式 | 行号 |
|:---|:---|:---|
| `domains/solution_pro/control_contract.py` | `STAGE_PATH_REGISTRY.get(stage_name)` | 24, 56 |
| `domains/solution_pro/planner.py` | `STAGE_PATH_REGISTRY["planning"]` | 15, 121 |
| `domains/solution_pro/harness_check_expert.py` | `blackboard_path / session_id / STAGE_PATH_REGISTRY[...]` | 19, 34-35 |
| `domains/solution_pro/completion_handler.py` | 构建 `STAGE_REQUIREMENTS` 映射 | 27, 34-55 |
| `domains/solution_pro/task_builder.py` | 拼接完整路径 `{base}/blackboard/{session_id}/{STAGE_PATH_REGISTRY[...]}` | 34, 109-112, 225, 676, 1288, 1366, 1559, 1573, 1661, 1757, 1885 |
| `domains/solution_pro/orchestrator_agent.py` | 构建 `STAGE_TO_PATH` 映射 | 69, 75-92 |
| `core/orchestrator/pipeline_orchestrator.py` | 导入并补充别名映射 | 32-34, 44-93 |

#### 1.2.2 get_blackboard_path() 调用点

**定义位置**：`core/config/path_config.py:194`

```python
def get_blackboard_path(self, session_id: str) -> Path:
    # 安全验证 + 路径解析
    return resolved_path  # blackboard_dir / sanitized_session_id
```

**调用文件**（共 3 个）：

| 文件 | 调用方式 | 行号 |
|:---|:---|:---|
| `domains/solution_pro/blackboard.py` | `config.get_blackboard_path(session_id)` | 70 |
| `domains/solution_pro/config.py` | `config.get_blackboard_path(self.session_id)` | 46 |
| `domains/solution_pro/harness_check_expert.py` | 间接通过 `blackboard_path` 参数 | 34 |

#### 1.2.3 硬编码 blackboard 路径的文件

**高风险**（直接拼接路径字符串）：

| 文件 | 硬编码模式 | 行号 |
|:---|:---|:---|
| `domains/solution_pro/task_builder.py` | `f"{_DEEPFLOW_BASE}/blackboard/{session_id}"` | 109-112, 225, 676, 1288, 1366, 1559, 1573, 1661, 1757, 1885 |
| `domains/spec_pro/coordinator.py` | `os.path.join(str(_BASE_DIR), "blackboard", self.session_id)` | 118 |
| `domains/spec_pro/spec_pro_api.py` | `os.path.join(DEEPFLOW_BASE, "blackboard")` | 62 |
| `domains/research_pro/__init__.py` | `_path_config.base_dir / "blackboard" / session_id` | 235 |
| `domains/research_pro/orchestrator.py` | `_BASE_DIR / 'blackboard'` | 151 |
| `core/blackboard/blackboard_bridge.py` | `Path.home() / ".openclaw" / "workspace" / ".deepflow" / "blackboard"` | 10 |
| `scripts/pipeline_progress_notify.py` | `"blackboard/.stage_progress.json"` | 53 |
| `frontend/backend/routers/status_v2.py` | `BLACKBOARD_DIR = _DEEPFLOW_ROOT / "blackboard"` | 24 |

**中风险**（通过 BlackboardManager 间接访问）：

| 文件 | 使用方式 |
|:---|:---|
| `core/orchestrator/pipeline_orchestrator.py` | `BlackboardManager` + `STAGE_PATH_REGISTRY` |
| `core/quality/entry_harness.py` | `BlackboardManager` |
| `scripts/data_collect_smic.py` | `BlackboardManager` |

### 1.3 状态文件分布

**散落在根目录的状态文件**：

| 文件名 | 写入位置 | 用途 |
|:---|:---|:---|
| `.completed` | `completion_handler.py:402`, `research_pro/__init__.py:181` | 标记任务完成 |
| `.cron_run_count` | `pipeline_watcher.py:56`, `solution/__init__.py:105`, `research_pro/__init__.py:265` | 运行计数 |
| `.cron_job_id` | `pipeline_watcher.py` | Cron 任务 ID |
| `.notified_stages.json` | `solution/__init__.py:97`, `research_pro/__init__.py:256` | 已通知阶段 |
| `.stage_progress.json` | `pipeline_progress_notify.py:39,53` | 阶段进度 |
| `.watcher_should_remove` | `pipeline_watcher.py:184` | Watcher 清理标记 |
| `.watcher_no_output_count` | `pipeline_watcher.py:117` | 无输出计数 |
| `.run_start_at` | `pipeline_watcher.py` | 运行开始时间 |

**问题**：8+ 个状态文件与交付文件混在同一目录，违反"状态与产出分离"原则。

### 1.4 跨域数据流引用

```
Spec Pro → Solution Pro:
  spec_pro/coordinator.py:118 → blackboard/{session_id}/spec/living_spec.json
  solution/blackboard.py → 读取 data/frozen_spec.json（来自 Spec Pro）

Solution Pro → Ship Pro:
  solution/blackboard.py → 写入 final_result.json
  ship_pro/scripts/run_pipeline.py:181 → bb_dir = output_p / "blackboard"
  ship_pro/scripts/run_pipeline.py:260 → 读取 final_result.json

Ship Pro 嵌套问题:
  run_pipeline.py:181 创建 ship/blackboard/ 子目录（套娃）
```

---

## 二、V2 迁移影响分析

### 2.1 需要修改的文件清单

#### 高优先级（核心路径逻辑）

| # | 文件 | 修改内容 | 风险 | 工作量 |
|:---|:---|:---|:---:|:---:|
| 1 | `core/config/path_config.py` | 新增 V2 路径方法 `get_project_path()`, `get_run_path()` | 🟢 低 | S |
| 2 | `core/blackboard/path_resolver.py` | **新建**兼容层，统一新旧路径解析 | 🟢 低 | M |
| 3 | `domains/solution_pro/blackboard.py` | `STAGE_PATH_REGISTRY` 路径前缀适配 V2 | 🟡 中 | M |
| 4 | `domains/solution_pro/task_builder.py` | 替换 10+ 处硬编码路径拼接 | 🔴 高 | L |
| 5 | `domains/ship_pro/scripts/run_pipeline.py` | 删除 `bb_dir = output_p / "blackboard"` 套娃逻辑 | 🟡 中 | M |

#### 中优先级（状态文件路径）

| # | 文件 | 修改内容 | 风险 | 工作量 |
|:---|:---|:---|:---:|:---:|
| 6 | `domains/solution_pro/completion_handler.py` | `.completed` 路径改为 `state/.completed` | 🟡 中 | S |
| 7 | `scripts/pipeline_watcher.py` | 状态文件路径改为 `state/` 子目录 | 🟡 中 | M |
| 8 | `scripts/pipeline_progress_notify.py` | `.stage_progress.json` 路径改为 `state/` | 🟡 中 | S |
| 9 | `domains/solution_pro/__init__.py` | 清理旧状态文件逻辑 | 🟢 低 | S |
| 10 | `domains/research_pro/__init__.py` | 状态文件路径改为 `state/` | 🟡 中 | S |

#### 低优先级（跨域引用）

| # | 文件 | 修改内容 | 风险 | 工作量 |
|:---|:---|:---|:---:|:---:|
| 11 | `domains/spec_pro/coordinator.py` | 使用 `path_resolver.py` 替代硬编码 | 🟢 低 | S |
| 12 | `domains/spec_pro/spec_pro_api.py` | 使用 `path_resolver.py` 替代硬编码 | 🟢 低 | S |
| 13 | `domains/research_pro/orchestrator.py` | 使用 `path_resolver.py` 替代硬编码 | 🟢 低 | S |
| 14 | `core/blackboard/blackboard_bridge.py` | 使用 `path_resolver.py` 替代硬编码 | 🟢 低 | S |
| 15 | `frontend/backend/routers/status_v2.py` | 支持 V2 路径结构（降级查旧路径） | 🟡 中 | M |

#### 无需修改（通过兼容层自动适配）

| 文件 | 原因 |
|:---|:---|
| `domains/solution_pro/control_contract.py` | 通过 `STAGE_PATH_REGISTRY` 间接引用，改注册表即可 |
| `domains/solution_pro/planner.py` | 同上 |
| `domains/solution_pro/harness_check_expert.py` | 通过 `STAGE_PATH_REGISTRY` 间接引用 |
| `domains/solution_pro/orchestrator_agent.py` | 同上 |
| `core/orchestrator/pipeline_orchestrator.py` | 同上 |
| `core/quality/entry_harness.py` | 使用 `BlackboardManager` API，不直接拼路径 |

### 2.2 修改顺序（依赖关系排序）

```
Phase 1: 基础设施（零风险）
  └─ 1.1 core/config/path_config.py（新增 V2 方法）
  └─ 1.2 core/blackboard/path_resolver.py（新建兼容层）

Phase 2: 核心迁移（按依赖顺序）
  ├─ 2.1 domains/solution_pro/blackboard.py（STAGE_PATH_REGISTRY 适配）
  │     ↓
  ├─ 2.2 domains/solution_pro/task_builder.py（替换硬编码路径）
  │     ↓
  ├─ 2.3 domains/ship_pro/scripts/run_pipeline.py（删除套娃逻辑）
  │     ↓
  └─ 2.4 domains/solution_pro/completion_handler.py（状态文件路径）

Phase 3: 状态文件集中化
  ├─ 3.1 scripts/pipeline_watcher.py
  ├─ 3.2 scripts/pipeline_progress_notify.py
  ├─ 3.3 domains/solution_pro/__init__.py
  └─ 3.4 domains/research_pro/__init__.py

Phase 4: 跨域引用统一
  ├─ 4.1 domains/spec_pro/coordinator.py
  ├─ 4.2 domains/spec_pro/spec_pro_api.py
  ├─ 4.3 domains/research_pro/orchestrator.py
  └─ 4.4 core/blackboard/blackboard_bridge.py

Phase 5: 前端适配
  └─ 5.1 frontend/backend/routers/status_v2.py
```

### 2.3 风险评估矩阵

| 风险项 | 概率 | 影响 | 缓解措施 |
|:---|:---:|:---:|:---|
| `task_builder.py` 硬编码路径遗漏 | 高 | 高 | 全文搜索 `blackboard/` + 正则匹配，逐一替换 |
| 旧运行数据无法被前端读取 | 中 | 中 | `status_v2.py` 兼容层：先查 V2 路径，降级查 V1 |
| 状态文件路径变更导致 cron watcher 失效 | 中 | 高 | `pipeline_watcher.py` 兼容层：双路径检查 |
| Ship Pro 嵌套逻辑删除后旧数据不兼容 | 低 | 低 | 旧数据已归档，不影响新运行 |
| `STAGE_PATH_REGISTRY` 修改影响所有 stage 写入 | 中 | 高 | 兼容层：新路径不存在时降级到旧路径 |
| 跨域数据流路径变更导致读取失败 | 中 | 高 | `path_resolver.py` 提供统一的跨域路径解析 |

---

## 三、迁移脚本设计

### 3.1 功能概述

**脚本位置**：`scripts/migrate_blackboard_v2.py`

**核心功能**：
1. 扫描 V1 blackboard 目录
2. 按项目 topic 分组，生成 slug
3. 为每个运行创建 V2 目录结构
4. 移动文件到对应子目录（`input/`, `stages/`, `output/`, `state/`）
5. 生成 `project.json`, `run.json`, `runs.json`
6. 保留原始目录结构备份

### 3.2 接口设计

```python
class BlackboardMigrator:
    """V1 → V2 Blackboard 迁移器"""
    
    def __init__(
        self,
        v1_root: Path,           # .deepflow/blackboard/
        v2_root: Path,           # .deepflow/blackboard/projects/
        backup_root: Path,       # .deepflow/blackboard/_legacy/
        dry_run: bool = True,    # 默认干跑，不实际移动
        log_file: Optional[Path] = None
    ):
        """初始化迁移器"""
        pass
    
    def scan_v1_directories(self) -> List[V1SessionInfo]:
        """
        扫描 V1 目录，提取元数据
        
        Returns:
            List[V1SessionInfo]: 包含 session_id, domain, topic, files 等信息
        """
        pass
    
    def generate_slug(self, topic: str) -> str:
        """
        从 topic 生成项目 slug
        
        规则：
        - 中文 → pinyin 或保留（如果文件系统支持）
        - 空格 → '-'
        - 特殊字符 → 删除
        - 长度限制 30 字符
        - 冲突时加 hash 后缀
        
        Args:
            topic: 项目主题
        
        Returns:
            str: 项目 slug
        """
        pass
    
    def plan_migration(self, sessions: List[V1SessionInfo]) -> MigrationPlan:
        """
        生成迁移计划（不执行）
        
        Args:
            sessions: V1 session 列表
        
        Returns:
            MigrationPlan: 包含所有移动操作的计划
        """
        pass
    
    def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        """
        执行迁移
        
        Args:
            plan: 迁移计划
        
        Returns:
            MigrationResult: 包含成功/失败/跳过的文件列表
        """
        pass
    
    def verify_migration(self, result: MigrationResult) -> VerificationReport:
        """
        验证迁移结果
        
        检查：
        - 所有文件已移动到新位置
        - project.json, run.json, runs.json 格式正确
        - 原始目录备份完整
        
        Args:
            result: 迁移结果
        
        Returns:
            VerificationReport: 验证报告
        """
        pass
    
    def rollback(self, result: MigrationResult) -> bool:
        """
        回滚迁移
        
        从备份恢复所有文件到原始位置
        
        Args:
            result: 迁移结果（包含备份路径）
        
        Returns:
            bool: 回滚是否成功
        """
        pass
```

### 3.3 数据结构

```python
@dataclass
class V1SessionInfo:
    """V1 session 元数据"""
    session_id: str              # 原始目录名
    domain: str                  # spec_pro / solution_pro / ship_pro / research_pro
    topic: Optional[str]         # 从目录名或文件内容提取
    files: List[Path]            # 所有文件列表
    has_completed: bool          # 是否有 .completed 标记
    created_at: Optional[datetime]  # 从目录名或文件时间提取
    input_hash: Optional[str]    # 从目录名提取（Solution Pro）

@dataclass
class MigrationPlan:
    """迁移计划"""
    operations: List[FileOperation]
    projects: Dict[str, List[V1SessionInfo]]  # slug → sessions
    
@dataclass
class FileOperation:
    """单个文件移动操作"""
    source: Path
    destination: Path
    operation: str  # "move" | "copy" | "skip"
    reason: Optional[str]

@dataclass
class MigrationResult:
    """迁移结果"""
    successful: List[FileOperation]
    failed: List[Tuple[FileOperation, str]]  # (op, error)
    skipped: List[Tuple[FileOperation, str]]  # (op, reason)
    backup_path: Path  # 备份目录路径

@dataclass
class VerificationReport:
    """验证报告"""
    total_files: int
    migrated_files: int
    missing_files: List[Path]
    corrupted_files: List[Path]
    metadata_valid: bool
    backup_intact: bool
```

### 3.4 迁移流程

```
1. 扫描阶段
   ├─ 遍历 blackboard/ 下所有目录
   ├─ 识别 domain（从目录名模式）
   ├─ 提取 topic（从目录名或文件内容）
   └─ 生成 V1SessionInfo 列表

2. 规划阶段
   ├─ 按 topic 分组，生成 slug
   ├─ 为每个 session 分配 run_id（时间戳或 hash）
   ├─ 生成 FileOperation 列表
   └─ 输出迁移计划（JSON）供人工审核

3. 备份阶段
   ├─ 创建 _legacy/ 备份目录
   ├─ 复制整个 blackboard/ 到 _legacy/
   └─ 生成备份清单（checksum）

4. 执行阶段
   ├─ 创建 V2 目录结构（projects/{slug}/runs/{ts}/）
   ├─ 移动文件到对应子目录：
   │   ├─ data/ → input/
   │   ├─ stages/ → stages/
   │   ├─ final_result.json → output/
   │   ├─ .completed, .cron_* → state/
   │   └─ ship/ → ship/
   ├─ 生成 project.json, run.json, runs.json
   └─ 记录操作日志

5. 验证阶段
   ├─ 检查所有文件已移动到新位置
   ├─ 验证 JSON 文件格式正确
   ├─ 检查备份完整性
   └─ 生成验证报告

6. 清理阶段（可选）
   ├─ 删除空的 V1 目录
   └─ 保留 _legacy/ 备份（手动确认后再删除）
```

### 3.5 回滚机制

```python
def rollback(self, result: MigrationResult) -> bool:
    """
    回滚步骤：
    1. 停止所有 DeepFlow 进程（避免文件占用）
    2. 删除 V2 目录（projects/）
    3. 从 _legacy/ 恢复原始目录
    4. 验证恢复后的目录结构
    5. 删除 _legacy/ 备份（可选）
    """
    pass
```

**回滚触发条件**：
- 验证阶段发现 > 5% 文件迁移失败
- 手动触发（`--rollback` 参数）
- 迁移后 24 小时内发现严重问题

### 3.6 验证步骤

```python
def verify_migration(self, result: MigrationResult) -> VerificationReport:
    """
    验证检查项：
    1. 文件完整性
       - V1 文件数量 == V2 文件数量
       - 每个文件的 checksum 匹配
    
    2. 目录结构
       - projects/{slug}/runs/{ts}/ 结构正确
       - input/, stages/, output/, state/ 子目录存在
    
    3. 元数据
       - project.json 格式正确，slug 唯一
       - run.json 包含必要字段（run_id, domain, status）
       - runs.json 包含所有 run 的摘要
    
    4. 备份完整性
       - _legacy/ 目录与原始 blackboard/ 一致
       - checksum 验证通过
    """
    pass
```

---

## 四、分阶段实施计划

### Phase 1: 基础设施（零风险）

**目标**：建立 V2 路径基础设施，不影响现有功能。

**任务**：

| # | 任务 | 文件 | 工作量 |
|:---|:---|:---|:---:|
| 1.1 | 新增 V2 路径方法 | `core/config/path_config.py` | S |
| 1.2 | 新建 `path_resolver.py` 兼容层 | `core/blackboard/path_resolver.py` | M |
| 1.3 | 创建 V2 目录结构 | `blackboard/projects/` | XS |

**新增方法**（path_config.py）：

```python
def get_project_path(self, slug: str) -> Path:
    """获取项目目录路径：blackboard/projects/{slug}/"""
    return self.blackboard_dir / "projects" / slug

def get_run_path(self, slug: str, run_id: str) -> Path:
    """获取运行目录路径：blackboard/projects/{slug}/runs/{run_id}/"""
    return self.blackboard_dir / "projects" / slug / "runs" / run_id

def get_domain_path(self, slug: str, run_id: str, domain: str) -> Path:
    """获取域目录路径：blackboard/projects/{slug}/runs/{run_id}/{domain}/"""
    return self.get_run_path(slug, run_id) / domain
```

**path_resolver.py 核心逻辑**：

```python
class PathResolver:
    """统一路径解析器（V1/V2 兼容）"""
    
    def __init__(self, path_config: PathConfig):
        self.config = path_config
    
    def resolve_session_path(self, session_id: str) -> Path:
        """
        解析 session 路径（V1/V2 自动识别）
        
        规则：
        - 如果 session_id 包含 '/'（V2 格式：slug/runs/ts）→ V2 路径
        - 否则 → V1 路径（blackboard/{session_id}）
        """
        if '/' in session_id:
            # V2 格式
            parts = session_id.split('/')
            return self.config.get_run_path(parts[0], parts[2])
        else:
            # V1 格式
            return self.config.get_blackboard_path(session_id)
    
    def resolve_stage_path(self, session_id: str, stage_name: str) -> Path:
        """解析 stage 路径（V2 优先，降级 V1）"""
        base = self.resolve_session_path(session_id)
        
        # V2 路径：stages/ 在域子目录下
        v2_path = base / "stages" / STAGE_PATH_REGISTRY_V2[stage_name]
        if v2_path.exists():
            return v2_path
        
        # V1 路径：降级
        v1_path = base / STAGE_PATH_REGISTRY[stage_name]
        return v1_path
    
    def resolve_state_path(self, session_id: str, filename: str) -> Path:
        """解析状态文件路径（V2: state/, V1: 根目录）"""
        base = self.resolve_session_path(session_id)
        
        # V2 路径
        v2_path = base / "state" / filename
        if v2_path.exists():
            return v2_path
        
        # V1 路径：降级
        v1_path = base / filename
        return v1_path
```

**测试计划**：
- [ ] 单元测试：`test_path_resolver.py`
  - V1 session_id 解析
  - V2 session_id 解析
  - 路径降级逻辑
  - 状态文件路径解析
- [ ] 集成测试：使用现有 V1 数据验证路径解析正确性

**验收标准**：
- [ ] 所有测试通过
- [ ] 现有 V1 运行不受影响
- [ ] V2 路径方法可正常创建目录

---

### Phase 2: 新代码使用 V2 路径

**目标**：新运行的任务使用 V2 路径结构。

**任务**：

| # | 任务 | 文件 | 工作量 |
|:---|:---|:---|:---:|
| 2.1 | Solution Pro session_id 改为 V2 格式 | `scripts/start_solution_pro.py` | M |
| 2.2 | Ship Pro 删除套娃逻辑 | `domains/ship_pro/scripts/run_pipeline.py` | M |
| 2.3 | STAGE_PATH_REGISTRY 适配 V2 | `domains/solution_pro/blackboard.py` | M |
| 2.4 | task_builder.py 使用 path_resolver | `domains/solution_pro/task_builder.py` | L |

**关键修改**：

**2.1 start_solution_pro.py**：

```python
# V1: session_id = f"{topic}_{domain}_{hash6}"
# V2: session_id = f"{slug}/runs/{timestamp}"

def generate_v2_session_id(topic: str) -> str:
    slug = generate_slug(topic)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{slug}/runs/{timestamp}"
```

**2.2 run_pipeline.py**：

```python
# V1: bb_dir = output_p / "blackboard"
# V2: bb_dir = output_p（直接使用 output_dir）

# 删除这行：
# bb_dir = output_p / "blackboard"

# 改为：
bb_dir = output_p
```

**2.3 blackboard.py**：

```python
# V2: STAGE_PATH_REGISTRY 路径前缀改为相对于域子目录
STAGE_PATH_REGISTRY_V2 = {
    "data_collection": "input/collection.json",      # data/ → input/
    "structured_requirements": "input/structured_requirements.json",
    "frozen_spec": "input/frozen_spec.json",
    "requirements_traceability_matrix": "output/requirements_traceability_matrix.json",
    "planning": "stages/planning.json",              # stages/ 保持不变
    # ... 其他 stage 路径不变
    "final_result": "output/final_result.json",      # 新增
}
```

**2.4 task_builder.py**：

```python
# V1: f"{_DEEPFLOW_BASE}/blackboard/{session_id}"
# V2: 使用 path_resolver

from core.blackboard.path_resolver import PathResolver

resolver = PathResolver(PathConfig.resolve())
blackboard_path = resolver.resolve_session_path(session_id)
```

**测试计划**：
- [ ] 单元测试：`test_blackboard_v2.py`
  - V2 session_id 生成
  - V2 目录结构创建
  - stage 写入/读取
  - Ship Pro 路径解析
- [ ] 集成测试：启动一个完整的 Solution Pro 运行
  - 验证 V2 目录结构正确创建
  - 验证所有 stage 文件写入正确位置
  - 验证 Ship Pro 读取 Solution Pro 输出
- [ ] 回归测试：使用现有测试用例
  - `tests/golden/run_golden_e2e.py`
  - `tests/contract/test_blackboard_manager.py`

**验收标准**：
- [ ] 新运行的 Solution Pro 使用 V2 目录结构
- [ ] 新运行的 Ship Pro 不再创建 `ship/blackboard/` 套娃
- [ ] 所有 stage 文件写入正确位置
- [ ] 前端 status_v2 能正常显示新运行状态

---

### Phase 3: 状态文件集中化

**目标**：所有状态文件迁移到 `state/` 子目录。

**任务**：

| # | 任务 | 文件 | 工作量 |
|:---|:---|:---|:---:|
| 3.1 | completion_handler.py 状态路径 | `domains/solution_pro/completion_handler.py` | S |
| 3.2 | pipeline_watcher.py 状态路径 | `scripts/pipeline_watcher.py` | M |
| 3.3 | pipeline_progress_notify.py 状态路径 | `scripts/pipeline_progress_notify.py` | S |
| 3.4 | solution/__init__.py 状态清理 | `domains/solution_pro/__init__.py` | S |
| 3.5 | research_pro/__init__.py 状态路径 | `domains/research_pro/__init__.py` | S |

**关键修改**：

**3.1 completion_handler.py**：

```python
# V1: marker_path = base_path / '.completed'
# V2: marker_path = base_path / 'state' / '.completed'

# 兼容层：
state_dir = base_path / "state"
if not state_dir.exists():
    # V1 降级
    marker_path = base_path / '.completed'
else:
    marker_path = state_dir / '.completed'
```

**3.2 pipeline_watcher.py**：

```python
# V1: state_dir / ".cron_run_count"
# V2: state_dir / "state" / ".cron_run_count"

# 兼容层：
def _resolve_state_path(state_dir: Path, filename: str) -> Path:
    v2_path = state_dir / "state" / filename
    if v2_path.exists():
        return v2_path
    return state_dir / filename  # V1 降级
```

**测试计划**：
- [ ] 单元测试：`test_state_paths.py`
  - 状态文件路径解析
  - V1/V2 降级逻辑
- [ ] 集成测试：启动一个完整运行
  - 验证状态文件写入 `state/` 目录
  - 验证 pipeline_watcher 能正确读取状态
  - 验证 completion_handler 能正确标记完成

**验收标准**：
- [ ] 所有状态文件写入 `state/` 目录
- [ ] pipeline_watcher 能正常监控新运行
- [ ] completion_handler 能正确标记完成状态

---

### Phase 4: 跨域引用统一

**目标**：所有域使用 `path_resolver.py` 统一路径解析。

**任务**：

| # | 任务 | 文件 | 工作量 |
|:---|:---|:---|:---:|
| 4.1 | spec_pro/coordinator.py | `domains/spec_pro/coordinator.py` | S |
| 4.2 | spec_pro/spec_pro_api.py | `domains/spec_pro/spec_pro_api.py` | S |
| 4.3 | research_pro/orchestrator.py | `domains/research_pro/orchestrator.py` | S |
| 4.4 | blackboard_bridge.py | `core/blackboard/blackboard_bridge.py` | S |

**关键修改**：

```python
# V1: self.base_path = os.path.join(str(_BASE_DIR), "blackboard", self.session_id)
# V2: 
from core.blackboard.path_resolver import PathResolver
resolver = PathResolver(PathConfig.resolve())
self.base_path = resolver.resolve_session_path(self.session_id)
```

**测试计划**：
- [ ] 单元测试：每个域的 path_resolver 调用
- [ ] 集成测试：跨域数据流验证
  - Spec Pro → Solution Pro 数据传递
  - Solution Pro → Ship Pro 数据传递

**验收标准**：
- [ ] 所有域使用 `path_resolver.py` 解析路径
- [ ] 跨域数据流正常
- [ ] 无硬编码 blackboard 路径

---

### Phase 5: 前端适配

**目标**：前端 status_v2 支持 V2 路径结构。

**任务**：

| # | 任务 | 文件 | 工作量 |
|:---|:---|:---|:---:|
| 5.1 | status_v2.py 支持 V2 路径 | `frontend/backend/routers/status_v2.py` | M |
| 5.2 | 新增项目列表 API | `frontend/backend/routers/status_v2.py` | M |
| 5.3 | 新增运行对比 API | `frontend/backend/routers/status_v2.py` | L |

**关键修改**：

```python
# V1: status_path = BLACKBOARD_DIR / session_id / "status.json"
# V2: 支持 projects/{slug}/runs/{ts}/status.json

def _get_status_path(session_id: str) -> Path:
    # V2 路径优先
    if '/' in session_id:
        # V2 格式：slug/runs/ts
        parts = session_id.split('/')
        v2_path = BLACKBOARD_DIR / "projects" / parts[0] / "runs" / parts[2] / "status.json"
        if v2_path.exists():
            return v2_path
    
    # V1 降级
    v1_path = BLACKBOARD_DIR / session_id / "status.json"
    return v1_path

# 新增 API：
@router.get("/projects")
def list_projects():
    """列出所有项目"""
    projects_dir = BLACKBOARD_DIR / "projects"
    # ...

@router.get("/projects/{slug}/runs")
def list_runs(slug: str):
    """列出项目的所有运行"""
    runs_dir = projects_dir / slug / "runs"
    # ...

@router.get("/compare")
def compare_runs(run_ids: List[str]):
    """对比多个运行"""
    # ...
```

**测试计划**：
- [ ] API 测试：`test_status_v2_api.py`
  - V1 session 状态查询
  - V2 session 状态查询
  - 项目列表 API
  - 运行对比 API
- [ ] 前端集成测试：手动验证

**验收标准**：
- [ ] 前端能正常显示 V1 和 V2 运行状态
- [ ] 项目列表 API 正常工作
- [ ] 运行对比 API 正常工作

---

## 五、迁移脚本实施计划

### 5.1 脚本开发

**时间安排**：Phase 1 完成后开始开发

**开发任务**：

| # | 任务 | 工作量 |
|:---|:---|:---:|
| 5.1.1 | 实现 `BlackboardMigrator` 核心类 | L |
| 5.1.2 | 实现 slug 生成逻辑 | S |
| 5.1.3 | 实现文件移动逻辑 | M |
| 5.1.4 | 实现元数据生成（project.json, run.json） | M |
| 5.1.5 | 实现回滚机制 | M |
| 5.1.6 | 实现验证逻辑 | M |

### 5.2 迁移执行

**前提条件**：
- [ ] Phase 1-4 完成
- [ ] 所有测试通过
- [ ] 备份存储空间充足（≥ 2x 当前 blackboard 大小）

**执行步骤**：

```bash
# 1. 干跑（生成迁移计划，不实际移动）
python3 scripts/migrate_blackboard_v2.py --dry-run

# 2. 审核迁移计划
cat migration_plan.json | jq

# 3. 执行迁移（自动备份）
python3 scripts/migrate_blackboard_v2.py --execute

# 4. 验证迁移结果
python3 scripts/migrate_blackboard_v2.py --verify

# 5. 如果验证失败，回滚
python3 scripts/migrate_blackboard_v2.py --rollback
```

### 5.3 迁移后验证

**验证清单**：

- [ ] 所有 V1 文件已迁移到 V2 结构
- [ ] `project.json`, `run.json`, `runs.json` 格式正确
- [ ] 前端能正常显示历史运行
- [ ] 新运行使用 V2 结构
- [ ] 跨域数据流正常
- [ ] pipeline_watcher 正常监控

---

## 六、风险评估与缓解

### 6.1 技术风险

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| `task_builder.py` 硬编码路径遗漏 | 高 | 高 | 全文搜索 + 正则匹配，逐一替换；添加 lint 规则禁止硬编码 |
| 状态文件路径变更导致 cron watcher 失效 | 中 | 高 | 兼容层：双路径检查；迁移前备份 |
| 前端无法读取 V1 历史数据 | 中 | 中 | `status_v2.py` 兼容层：V2 优先，V1 降级 |
| 迁移脚本 bug 导致数据丢失 | 低 | 极高 | 默认 dry-run；自动备份；回滚机制 |

### 6.2 业务风险

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| 迁移期间无法启动新运行 | 中 | 中 | 选择无运行时段迁移；快速回滚 |
| 用户不熟悉新目录结构 | 低 | 低 | 文档更新；迁移脚本自动处理 |
| 跨域数据流中断 | 中 | 高 | 充分测试；兼容层降级 |

### 6.3 时间风险

| 阶段 | 预估工作量 | 风险缓冲 | 总计 |
|:---|:---:|:---:|:---:|
| Phase 1: 基础设施 | 1 天 | 0.5 天 | 1.5 天 |
| Phase 2: 核心迁移 | 3 天 | 1.5 天 | 4.5 天 |
| Phase 3: 状态文件 | 1 天 | 0.5 天 | 1.5 天 |
| Phase 4: 跨域引用 | 1 天 | 0.5 天 | 1.5 天 |
| Phase 5: 前端适配 | 2 天 | 1 天 | 3 天 |
| 迁移脚本开发 | 2 天 | 1 天 | 3 天 |
| 迁移执行 + 验证 | 1 天 | 1 天 | 2 天 |
| **总计** | **11 天** | **6 天** | **17 天** |

---

## 七、开放问题

### 7.1 待决策

1. **slug 生成策略**：
   - 方案 A：自动从 topic 生成（`deepflow-observability`）
   - 方案 B：用户首次运行时指定
   - 方案 C：hash（`1a43ee1f`）
   - **推荐**：方案 A + 冲突时加 hash 后缀

2. **旧数据迁移**：
   - 方案 A：全量迁移到 `projects/`
   - 方案 B：保留在 `_legacy/`，前端兼容读取
   - **推荐**：方案 B（风险低，工作量小）

3. **runs.json 维护者**：
   - 方案 A：orchestrator 写入
   - 方案 B：completion_handler 写入
   - 方案 C：独立的 registry 服务
   - **推荐**：方案 B（completion_handler 已有完成状态写入逻辑）

### 7.2 待验证

1. **V2 目录结构是否满足 Loop Engine 需求**：
   - 需要验证跨迭代的 A/B 对比场景
   - 需要验证反馈数据存储位置

2. **前端 Dashboard 是否需要大改**：
   - 需要评估前端工作量
   - 是否需要新增 API

---

## 八、附录

### 8.1 关键文件清单

| 文件 | 行数 | 优先级 | 修改类型 |
|:---|:---:|:---:|:---|
| `core/config/path_config.py` | 292 | P1 | 新增方法 |
| `core/blackboard/path_resolver.py` | 新建 | P1 | 新建 |
| `domains/solution_pro/blackboard.py` | 180 | P1 | 修改注册表 |
| `domains/solution_pro/task_builder.py` | 1900 | P1 | 替换硬编码 |
| `domains/ship_pro/scripts/run_pipeline.py` | 550 | P1 | 删除套娃 |
| `domains/solution_pro/completion_handler.py` | 500 | P2 | 状态路径 |
| `scripts/pipeline_watcher.py` | 245 | P2 | 状态路径 |
| `frontend/backend/routers/status_v2.py` | 650 | P3 | 兼容层 |

### 8.2 术语表

| 术语 | 定义 |
|:---|:---|
| V1 | 当前 blackboard 目录结构 |
| V2 | 重构后的 `projects/{slug}/runs/{ts}/` 结构 |
| slug | 项目的人类可读标识（如 `deepflow-observability`） |
| run_id | 运行标识（时间戳格式 `YYYYMMDD_HHMMSS`） |
| path_resolver | 统一路径解析器，支持 V1/V2 兼容 |

---

*本文档待专家评审后进入实施阶段。*
