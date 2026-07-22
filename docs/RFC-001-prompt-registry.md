# RFC-001: DeepFlow Prompt集中式注册表

**状态**: ✅ 已实现（Phase 1 完成）  
**作者**: DeepFlow Team  
**日期**: 2026-05-01  
**版本**: 1.0.0  

---

## 1. 设计原则

### 1.1 核心原则

| 原则 | 说明 |
|:---|:---|
| **单一职责** | Prompt文件只包含prompt内容，元数据由注册表管理 |
| **显式优于隐式** | 所有prompt必须在注册表中显式声明，不允许隐式加载 |
| **向后兼容** | 迁移期间支持旧格式，但新代码只使用新接口 |
| **可验证** | 提供工具自动校验注册表完整性和一致性 |

### 1.2 设计目标

- 消除YAML元数据污染LLM上下文的问题
- 建立统一的prompt版本管理机制
- 支持跨领域prompt查询和分析
- 为未来自动化工具（代码生成、文档生成）奠定基础

---

## 2. 文件结构

### 2.1 目录结构

```
prompts/
├── investment/              # 纯prompt文件（11个）
│   ├── planner.md
│   ├── researcher_finance.md
│   ├── researcher_tech.md
│   ├── researcher_market.md
│   ├── researcher_macro_chain.md
│   ├── researcher_management.md
│   ├── researcher_sentiment.md
│   ├── auditor.md
│   ├── fixer.md
│   ├── summarizer_enhanced.md
│   └── send_reporter.md
│
├── solution/                # 纯prompt文件（8个）
│   ├── planner.md
│   ├── researcher_template.md
│   ├── designer.md
│   ├── auditor.md
│   ├── fixer.md
│   ├── data_collection.md
│   ├── fixer_with_audit.md
│   └── deliver.md
│
└── registry.yaml            # 集中式注册表（唯一元数据源）
```

### 2.2 文件命名规范

```yaml
naming_convention:
  format: "{role}[_subtype].md"
  examples:
    - "planner.md"           # 单一角色
    - "researcher_finance.md" # 角色+子类型
    - "fixer_with_audit.md"  # 角色+场景
  
  reserved_words:
    - "registry"  # 保留给注册表文件
    - "index"     # 保留给索引文件
```

---

## 3. 注册表格式（registry.yaml）

### 3.1 顶层结构

```yaml
# registry.yaml
schema_version: "1.0.0"           # 注册表schema版本
last_updated: "2026-05-01T10:00:00+08:00"
generator: "manual"               # 或 "auto"（工具生成）

domains:                          # 按领域分组
  investment:
    version: "2.0.0"              # 领域整体版本
    prompts:                      # 该领域的所有prompt
      ...
  
  solution:
    version: "2.1.0"
    prompts:
      ...

# 可选：跨领域共享配置
shared:
  variables:
    common:
      - "DEEPFLOW_BASE"
      - "SESSION_ID"
      - "BLACKBOARD_PATH"
```

### 3.2 Prompt条目结构

```yaml
# registry.yaml 中的单个prompt条目
planner:                          # prompt标识符（文件名不含扩展名）
  name: "Investment Planner"      # 显示名称
  filename: "planner.md"          # 实际文件名
  version: "2.0.0"                # 语义化版本
  
  # 分类信息
  role: "planner"                 # 角色类型
  domain: "investment"            # 所属领域
  subtype: null                   # 子类型（可选）
  
  # 元信息
  author: "deepflow-team"
  created: "2026-04-01"
  updated: "2026-05-01"
  
  # 变更日志
  changelog:
    - version: "2.0.0"
      date: "2026-05-01"
      changes:
        - "优化输出格式"
        - "添加数据fallback策略"
    - version: "1.0.0"
      date: "2026-04-01"
      changes:
        - "初始版本"
  
  # 模板变量（用于代码生成和校验）
  variables:
    required:                     # 必需变量
      - name: "COMPANY_CODE"
        type: "string"
        description: "股票代码"
      - name: "COMPANY_NAME"
        type: "string"
        description: "公司名称"
    optional:                     # 可选变量
      - name: "INDUSTRY"
        type: "string"
        default: "半导体设备"
  
  # 依赖关系（可选，用于复杂场景）
  dependencies:
    data_files:
      - "key_metrics.json"
      - "financials/raw.json"
  
  # 兼容性矩阵（可选）
  compatibility:
    min_orchestrator_version: "4.0.0"
    tested_models:
      - "kimi-k2.5"
      - "qwen3.6-plus"
```

### 3.3 完整示例

```yaml
# prompts/registry.yaml
schema_version: "1.0.0"
last_updated: "2026-05-01T10:00:00+08:00"

domains:
  investment:
    version: "2.0.0"
    prompts:
      planner:
        name: "Investment Planner"
        filename: "planner.md"
        version: "2.0.0"
        role: "planner"
        author: "deepflow-team"
        created: "2026-04-01"
        updated: "2026-05-01"
        changelog:
          - version: "2.0.0"
            date: "2026-05-01"
            changes: ["添加YAML元数据", "优化数据读取逻辑"]
          - version: "1.0.0"
            date: "2026-04-01"
            changes: ["初始版本"]
        variables:
          required:
            - name: "COMPANY_CODE"
              type: "string"
            - name: "COMPANY_NAME"
              type: "string"
          optional:
            - name: "INDUSTRY"
              type: "string"
              default: "半导体设备"
      
      researcher_finance:
        name: "Finance Researcher"
        filename: "researcher_finance.md"
        version: "2.0.0"
        role: "researcher"
        subtype: "finance"
        author: "deepflow-team"
        created: "2026-04-01"
        updated: "2026-05-01"
        changelog:
          - version: "2.0.0"
            date: "2026-05-01"
            changes: ["添加YAML元数据"]
        variables:
          required:
            - name: "COMPANY_CODE"
            - name: "COMPANY_NAME"
            - name: "INDUSTRY"
      
      # ... 其他8个prompt
  
  solution:
    version: "2.1.0"
    prompts:
      planner:
        name: "Solution Planner"
        filename: "planner.md"
        version: "2.0.0"
        role: "planner"
        # ...
      
      # ... 其他7个prompt

shared:
  variables:
    common:
      - "DEEPFLOW_BASE"
      - "SESSION_ID"
      - "BLACKBOARD_PATH"
```

---

## 4. 代码实现

### 4.1 PromptRegistry类

```python
# core/prompt_registry.py

"""
DeepFlow Prompt注册表管理器

提供prompt的版本管理、元数据查询和加载功能。
所有prompt信息均来自 prompts/registry.yaml，不读取文件内容。
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from core.config.path_config import PathConfig


@dataclass
class PromptInfo:
    """Prompt元数据结构"""
    id: str                        # 唯一标识符（如 "investment/planner"）
    name: str                      # 显示名称
    filename: str                  # 文件名
    version: str                   # 版本号
    role: str                      # 角色类型
    domain: str                    # 所属领域
    subtype: Optional[str] = None  # 子类型
    author: str = "deepflow-team"
    created: str = ""
    updated: str = ""
    changelog: List[Dict] = None
    variables: Dict[str, List[Dict]] = None
    
    def __post_init__(self):
        if self.changelog is None:
            self.changelog = []
        if self.variables is None:
            self.variables = {"required": [], "optional": []}


class PromptRegistry:
    """
    Prompt注册表管理器
    
    单例模式，应用启动时加载 registry.yaml，运行时只读访问。
    """
    
    _instance = None
    _registry_data = None
    _prompts_by_id = {}      # { "investment/planner": PromptInfo }
    _prompts_by_domain = {}  # { "investment": [PromptInfo, ...] }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._load_registry()
        return cls._instance
    
    @classmethod
    def _load_registry(cls):
        """加载注册表文件"""
        base_path = PathConfig.resolve().base_dir
        registry_path = base_path / "prompts" / "registry.yaml"
        
        if not registry_path.exists():
            raise FileNotFoundError(f"Registry not found: {registry_path}")
        
        with open(registry_path, 'r', encoding='utf-8') as f:
            cls._registry_data = yaml.safe_load(f)
        
        # 构建索引
        cls._build_index()
    
    @classmethod
    def _build_index(cls):
        """构建索引以便快速查询"""
        cls._prompts_by_id = {}
        cls._prompts_by_domain = {}
        
        for domain_name, domain_data in cls._registry_data.get('domains', {}).items():
            cls._prompts_by_domain[domain_name] = []
            
            for prompt_id, prompt_data in domain_data.get('prompts', {}).items():
                full_id = f"{domain_name}/{prompt_id}"
                
                info = PromptInfo(
                    id=full_id,
                    name=prompt_data.get('name', prompt_id),
                    filename=prompt_data.get('filename', f"{prompt_id}.md"),
                    version=prompt_data.get('version', '1.0.0'),
                    role=prompt_data.get('role', 'unknown'),
                    domain=domain_name,
                    subtype=prompt_data.get('subtype'),
                    author=prompt_data.get('author', 'deepflow-team'),
                    created=prompt_data.get('created', ''),
                    updated=prompt_data.get('updated', ''),
                    changelog=prompt_data.get('changelog', []),
                    variables=prompt_data.get('variables', {'required': [], 'optional': []})
                )
                
                cls._prompts_by_id[full_id] = info
                cls._prompts_by_domain[domain_name].append(info)
    
    # ============ 查询接口 ============
    
    def get(self, prompt_id: str) -> PromptInfo:
        """
        获取指定prompt的元数据
        
        Args:
            prompt_id: 格式为 "domain/prompt_name"，如 "investment/planner"
        
        Returns:
            PromptInfo对象
        
        Raises:
            KeyError: 如果prompt不存在
        """
        if prompt_id not in self._prompts_by_id:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return self._prompts_by_id[prompt_id]
    
    def get_by_domain(self, domain: str) -> List[PromptInfo]:
        """获取某领域的所有prompt"""
        return self._prompts_by_domain.get(domain, [])
    
    def get_by_role(self, role: str, domain: Optional[str] = None) -> List[PromptInfo]:
        """获取指定角色的所有prompt"""
        results = []
        search_space = [self._prompts_by_domain[domain]] if domain else self._prompts_by_id.values()
        
        for prompt in search_space:
            if prompt.role == role:
                results.append(prompt)
        return results
    
    def list_all(self) -> List[PromptInfo]:
        """列出所有prompt"""
        return list(self._prompts_by_id.values())
    
    def exists(self, prompt_id: str) -> bool:
        """检查prompt是否存在"""
        return prompt_id in self._prompts_by_id
    
    # ============ 版本接口 ============
    
    def check_version(self, prompt_id: str, min_version: str) -> bool:
        """检查prompt版本是否满足最低要求"""
        from packaging import version
        info = self.get(prompt_id)
        return version.parse(info.version) >= version.parse(min_version)
    
    def get_changelog(self, prompt_id: str) -> List[Dict]:
        """获取prompt的变更历史"""
        return self.get(prompt_id).changelog
    
    # ============ 验证接口 ============
    
    def validate(self) -> Dict[str, List[str]]:
        """
        验证注册表完整性
        
        Returns:
            { "errors": [...], "warnings": [...] }
        """
        errors = []
        warnings = []
        
        base_path = PathConfig.resolve().base_dir
        
        for prompt_id, info in self._prompts_by_id.items():
            # 检查文件存在性
            file_path = base_path / "prompts" / info.domain / info.filename
            if not file_path.exists():
                errors.append(f"File not found: {file_path}")
            
            # 检查版本格式
            try:
                from packaging import version
                version.parse(info.version)
            except:
                errors.append(f"Invalid version format: {prompt_id} -> {info.version}")
            
            # 警告：如果文件内容包含YAML Front Matter
            if file_path.exists():
                with open(file_path, 'r') as f:
                    if f.read().startswith('---'):
                        warnings.append(f"Prompt contains YAML (should be pure): {prompt_id}")
        
        return {"errors": errors, "warnings": warnings}


# ============ 便捷函数 ============

def get_prompt_info(prompt_id: str) -> PromptInfo:
    """便捷函数：获取prompt元数据"""
    return PromptRegistry().get(prompt_id)


def read_prompt(prompt_id: str) -> str:
    """
    读取prompt内容（纯净版，无元数据）
    
    这是主要的prompt读取接口，所有代码应使用此函数。
    """
    registry = PromptRegistry()
    info = registry.get(prompt_id)
    
    base_path = PathConfig.resolve().base_dir
    file_path = base_path / "prompts" / info.domain / info.filename
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def read_prompt_with_vars(prompt_id: str, **variables) -> str:
    """
    读取prompt并填充变量
    
    示例:
        read_prompt_with_vars("investment/planner", 
                             COMPANY_CODE="300604", 
                             COMPANY_NAME="长川科技")
    """
    content = read_prompt(prompt_id)
    
    # 简单变量替换（可以扩展为Jinja2等模板引擎）
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    
    return content
```

### 4.2 使用示例

```python
# 使用示例
from core.prompt_registry import PromptRegistry, read_prompt, get_prompt_info

# 方式1：获取元数据
info = get_prompt_info("investment/planner")
print(f"Prompt: {info.name}, Version: {info.version}")
# 输出: Prompt: Investment Planner, Version: 2.0.0

# 方式2：读取prompt内容（纯净）
content = read_prompt("investment/planner")
# 返回: "# Investment Planner..." （无YAML）

# 方式3：填充变量后读取
filled = read_prompt_with_vars(
    "investment/planner",
    COMPANY_CODE="300604",
    COMPANY_NAME="长川科技"
)

# 方式4：使用Registry对象进行高级查询
registry = PromptRegistry()

# 获取所有researcher
researchers = registry.get_by_role("researcher", domain="investment")
for r in researchers:
    print(f"  - {r.name} ({r.subtype})")

# 版本检查
if registry.check_version("investment/planner", "2.0.0"):
    print("版本满足要求")

# 验证注册表完整性
result = registry.validate()
if result['errors']:
    print(f"发现 {len(result['errors'])} 个错误")
```

---

## 5. 迁移计划

### 5.1 迁移前准备

1. **备份当前prompt**
   ```bash
   cp -r prompts prompts.backup.$(date +%Y%m%d)
   ```

2. **冻结开发**
   - 迁移期间暂停prompt修改
   - 所有修改在迁移后统一进行

### 5.2 迁移步骤

```yaml
migration_steps:
  phase_1_extract:
    name: "提取元数据"
    actions:
      - "扫描所有prompt文件的YAML Front Matter"
      - "生成 prompts/registry.yaml 初稿"
      - "人工审核和补全信息"
    output: "registry.yaml (draft)"
    
  phase_2_clean:
    name: "清理prompt文件"
    actions:
      - "从所有prompt文件中删除YAML Front Matter"
      - "保留纯净的prompt内容"
      - "验证文件可读性"
    output: "纯净的prompt文件（19个）"
    
  phase_3_implement:
    name: "实现Registry类"
    actions:
      - "创建 core/prompt_registry.py"
      - "实现查询接口"
      - "添加验证工具"
    output: "PromptRegistry类"
    
  phase_4_migrate_code:
    name: "迁移代码"
    actions:
      - "core/task_builder.py: 使用read_prompt('investment/planner')"
      - "domains/solution_pro/task_builder.py: 使用read_prompt('solution/planner')"
      - "删除旧的read_original_prompt函数"
    output: "更新后的代码"
    
  phase_5_verify:
    name: "验证"
    actions:
      - "运行 PromptRegistry().validate()"
      - "执行全量测试"
      - "检查契约笼子合规性"
    criteria:
      - "所有文件存在"
      - "无YAML残留"
      - "契约检查通过"
      - "功能测试通过"
```

### 5.3 回滚方案

```bash
# 如果迁移失败，一键回滚
cp -r prompts.backup.20260501/* prompts/
git checkout core/task_builder.py domains/solution_pro/task_builder.py
rm core/prompt_registry.py
```

---

## 6. 工具支持

### 6.1 CLI工具

```bash
# 验证注册表
python -m tools.prompt_registry validate

# 列出所有prompt
python -m tools.prompt_registry list

# 检查特定prompt
python -m tools.prompt_registry get investment/planner

# 生成文档
python -m tools.prompt_registry generate-docs

# 版本对比
python -m tools.prompt_registry diff investment/planner v1.0.0 v2.0.0
```

### 6.2 预提交钩子

```yaml
# .pre-commit-hooks.yaml
- id: validate-prompt-registry
  name: Validate Prompt Registry
  entry: python -m tools.prompt_registry validate
  language: python
  files: ^prompts/
```

---

## 7. 验证清单

### 7.1 技术验证

- [ ] `registry.yaml` 格式正确，可解析
- [ ] 所有prompt文件在注册表中有对应条目
- [ ] 所有注册表条目对应的文件存在
- [ ] Prompt文件不含YAML Front Matter
- [ ] `read_prompt()` 返回纯净内容
- [ ] `PromptRegistry.validate()` 无错误
- [ ] 全量测试通过
- [ ] 契约检查通过

### 7.2 功能验证

- [ ] Investment模块正常工作
- [ ] Solution模块正常工作
- [ ] 长川科技测试用例通过
- [ ] 版本检查功能正常
- [ ] 变量替换功能正常

---

## 8. 开放问题（供评审讨论）

1. **版本号管理**: 语义化版本（semver）是否合适？还是需要包含日期？

2. **变量定义**: 是否需要强类型的变量定义（schema），还是简单列表足够？

3. **多语言支持**: 未来是否需要支持多语言prompt？如何设计？

4. **A/B测试**: 是否需要支持同一prompt的多个版本并行（用于实验）？

5. **权限控制**: 是否需要字段级别的权限控制（如某些prompt仅特定用户可用）？

6. **外部prompt**: 是否支持引用外部/远程prompt（URL）？

---

## 9. 参考文档

- [Semantic Versioning](https://semver.org/)
- [YAML Specification](https://yaml.org/spec/)
- [Prompt Engineering Guide](https://www.promptingguide.ai/)

---

## 10. 路径变量最佳实践

<!-- FixFlow R10 (2026-07-22) 新增：路径变量命名规范 -->

### 10.1 双花括号 vs 单花括号约定

模板中的变量替换使用花括号语法，但**路径相关变量**和**非路径变量**有严格的区分：

| 类型 | 语法 | 语义 | 缺失行为 | 示例 |
|:---|:---|:---|:---|:---|
| **路径变量（必需）** | `{{variable}}` | 双花括号 = 必需参数 | **fail-fast**：缺失时 raise ValueError | `{{wp_subdir}}`、`{{project_name}}` |
| **非路径变量（可选）** | `{variable}` | 单花括号 = 可选参数 | 有 fallback 或默认值 | `{deepflow_root}`、`{task_id}` |

### 10.2 设计理由

路径变量使用双花括号的核心理由：

1. **静默错误比崩溃更危险**：路径变量缺失时，单花括号会被 LLM 原样保留（如 `{wp_subdir}` 变成字面字符串），导致写入错误目录但无报错
2. **fail-fast 原则**：双花括号在 `str.format()` 中缺失 key 会立即抛 `KeyError`，在 `read_prompt_with_vars()` 中可被捕获并转为明确的参数缺失错误
3. **意图信号**：双花括号向 LLM 和人类读者明确传达"此变量必须提供，不可省略"

### 10.3 案例：FixFlow R10 (2026-07-22)

**问题**：`deliver_worker_base.md` 中 `{wp_subdir}` 和 `{project_name}` 使用单花括号。

**故障链**：
```
commit 3489118 漏传 wp_subdir 参数
    ↓
str.format() 对单花括号 {wp_subdir} 不报错（保留字面量）
    ↓
Worker 写入 deliver_pro/{wp_subdir}/ 字面路径
    ↓
step4_check_workers 在错误路径找不到产出 → 报 MISSING
    ↓
排查困难：错误信息是"产出缺失"，根因是"路径变量未替换"
```

**修复**：`{wp_subdir}` → `{{wp_subdir}}`，`{project_name}` → `{{project_name}}`

**效果**：参数缺失时立即 `KeyError`，fail-fast 暴露根因。

### 10.4 实施规则

1. **新增 prompt 时**：路径拼接变量一律用 `{{double_braces}}`
2. **已有 prompt 迁移**：发现路径变量用单花括号时，改为双花括号
3. **`read_prompt_with_vars()` 适配**：双花括号变量通过 `str.format()` 替换，单花括号变量通过显式 `.replace()` 或 fallback 链处理
4. **验证**：DryRun 检查 prompt 中所有 `{...}` 模式，路径变量必须是 `{{...}}`

---

## 11. 修订历史

| 版本 | 日期 | 变更 |
|:---|:---|:---|
| 1.0.0 | 2026-05-01 | 初始版本 |
| 1.1.0 | 2026-07-22 | FixFlow R10: 新增 §10 路径变量最佳实践（双花括号=必需，单花括号=可选） |

---

**下一步**: 请多位专家进行评审，讨论开放问题，确定最终方案。
