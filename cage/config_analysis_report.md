# DeepFlow 配置化改造分析报告

## 问题确认

### 1. Tushare "未注册" 根因

**问题链**：
```
tushare_provider.py import 错误 
  → TushareProvider 未注册 
  → investment.yaml 中 provider: tushare 任务执行失败
  → 抛出 "Provider 'tushare' 未注册。可用: ['akshare', 'sina_finance', 'web_fetch']"
```

**代码证据**：
```python
# data_providers/investment.py:register_providers()
try:
    from data_providers.tushare_provider import TushareProvider
    ProviderRegistry.register("tushare", TushareProvider())
except ImportError:
    pass  # ← 静默跳过，导致 tushare 未注册
```

**根本原因**：`tushare_provider.py` 第1行有 import 路径错误：
```python
from data_manager import DataProvider, DataQuery, DataResult, DataFinding
# 应为：from core.data_manager import ...
```

### 2. Gemini CLI 不可用

**实际情况**：
- ✅ gemini CLI 已安装（`/opt/homebrew/bin/gemini v0.27.0`）
- ✅ GEMINI_API_KEY 已配置（环境变量）
- ❌ 但 Prompt 中写死了 `gemini -p "查询"` 命令格式
- ❌ Agent 在隔离环境中执行时可能找不到 gemini 命令

**问题**：Prompt 假设工具一定可用，没有配置化 fallback。

---

## 用户建议分析

> "搜索类，财经api类已经是用配置，引入openclaw 当前配置，然后prompt再引入这些prompt"

**核心思想**：
1. **配置驱动**：搜索工具、财经 API 应该是可配置的（而非硬编码）
2. **OpenClaw 集成**：复用 OpenClaw 已有的配置（如 GEMINI_API_KEY）
3. **Prompt 模板化**：Prompt 中通过变量引用配置，而非写死工具命令

---

## 系统性解决方案

### 方案 A：配置化改造（推荐）

#### 1. 创建 `deepflow.yaml` 配置文件

```yaml
# ~/.openclaw/deepflow.yaml
version: "1.0"

# 搜索工具配置
search:
  primary:
    name: "gemini_cli"
    enabled: true
    command: "gemini -p '{query}'"
    timeout: 30
    api_key: "${GEMINI_API_KEY}"  # 引用环境变量
  
  fallback:
    - name: "duckduckgo"
      enabled: true
      module: "duckduckgo_search"
      timeout: 20
    - name: "web_fetch"
      enabled: true
      timeout: 15

# 财经数据源配置
data_providers:
  tushare:
    enabled: true
    token: "${TUSHARE_TOKEN}"  # 引用环境变量
    tier: "pro"  # pro 版无限制
  
  akshare:
    enabled: true
    # 免费，无需配置
  
  sina_finance:
    enabled: true
    # 免费，无需配置
  
  eastmoney:
    enabled: true
    # 免费，无需配置

# 报告输出配置
output:
  format: "markdown"  # markdown / json / html
  auto_send: true     # 完成后自动发送到飞书
  feishu_target: "${FEISHU_USER_ID}"
```

#### 2. 修改 Prompt 模板系统

```python
# core/prompt_loader.py
import yaml
from jinja2 import Template

class PromptLoader:
    def __init__(self, config_path: str = "~/.openclaw/deepflow.yaml"):
        self.config = self._load_config(config_path)
    
    def load_prompt(self, prompt_name: str, context: Dict = None) -> str:
        """加载 Prompt，注入配置变量"""
        prompt_path = f"prompts/{prompt_name}.md"
        with open(prompt_path) as f:
            template = Template(f.read())
        
        # 注入配置变量
        config_context = {
            "search_tools": self._get_search_tools(),
            "data_providers": self._get_data_providers(),
            **(context or {})
        }
        
        return template.render(**config_context)
    
    def _get_search_tools(self) -> str:
        """生成搜索工具说明（基于配置）"""
        tools = []
        
        if self.config["search"]["primary"]["enabled"]:
            primary = self.config["search"]["primary"]
            tools.append(f"1. **{primary['name']}**（首选）→ `{primary['command']}`")
        
        for fallback in self.config["search"]["fallback"]:
            if fallback["enabled"]:
                tools.append(f"2. **{fallback['name']}**（fallback）→ `{fallback.get('command', fallback.get('module', 'N/A'))}`")
        
        return "\n".join(tools) if tools else "⚠️ 无可用搜索工具"
    
    def _get_data_providers(self) -> str:
        """生成数据源说明（基于配置）"""
        providers = []
        for name, config in self.config["data_providers"].items():
            if config["enabled"]:
                providers.append(f"- **{name}**: {'✅ 可用' if self._check_provider(name) else '❌ 不可用'}")
        return "\n".join(providers)
```

#### 3. 修改 Prompt 文件（示例）

```markdown
# prompts/investment/researcher_macro_chain.md
# 使用 Jinja2 模板语法

## 可用搜索工具
{{ search_tools }}

## 可用数据源
{{ data_providers }}

## 任务
1. 使用上述可用工具搜索 {{ industry }} 行业趋势
2. 如果首选工具失败，自动使用 fallback
3. 所有数据标注来源和 confidence
```

### 方案 B：OpenClaw 配置集成

利用 OpenClaw 的 `config.schema.lookup` 和 `config.get`：

```python
# core/config_bridge.py
from openclaw import config

class OpenClawConfigBridge:
    """桥接 OpenClaw 配置到 DeepFlow"""
    
    @staticmethod
    def get_gemini_config() -> Dict:
        """从 OpenClaw 配置获取 Gemini 设置"""
        try:
            api_key = config.get("GEMINI_API_KEY")
            return {
                "enabled": bool(api_key),
                "api_key": api_key,
                "command": "gemini -p '{query}'"
            }
        except:
            return {"enabled": False}
    
    @staticmethod
    def get_tushare_config() -> Dict:
        """从 OpenClaw 配置获取 Tushare 设置"""
        try:
            # 从 .credentials/ 或环境变量获取
            token = config.get("TUSHARE_TOKEN") or os.getenv("TUSHARE_TOKEN")
            return {
                "enabled": bool(token),
                "token": token
            }
        except:
            return {"enabled": False}
```

### 方案 C：Prompt 动态生成（最灵活）

```python
# core/dynamic_prompt.py
class DynamicPromptBuilder:
    """根据当前环境动态生成 Prompt"""
    
    def build_researcher_prompt(self, role: str, context: Dict) -> str:
        """构建 Researcher Prompt"""
        
        # 1. 检测可用工具
        tools = self._detect_available_tools()
        
        # 2. 生成工具说明
        tool_instructions = self._generate_tool_instructions(tools)
        
        # 3. 生成 fallback 链
        fallback_chain = self._generate_fallback_chain(tools)
        
        # 4. 组装 Prompt
        prompt = f"""# {role} Agent Prompt

## 你的身份
你是 {role}，负责...

## 可用工具（已检测）
{tool_instructions}

## 数据获取策略
{fallback_chain}

## 任务
{context['task_description']}
"""
        return prompt
    
    def _detect_available_tools(self) -> Dict:
        """检测当前环境可用的工具"""
        tools = {
            "gemini_cli": self._check_gemini(),
            "duckduckgo": self._check_duckduckgo(),
            "tushare": self._check_tushare(),
            "akshare": self._check_akshare(),
        }
        return {k: v for k, v in tools.items() if v["available"]}
    
    def _check_gemini(self) -> Dict:
        import subprocess
        try:
            result = subprocess.run(["gemini", "--version"], capture_output=True, timeout=5)
            return {
                "available": result.returncode == 0,
                "version": result.stdout.decode().strip(),
                "command": "gemini -p '{query}'"
            }
        except:
            return {"available": False}
    
    def _generate_tool_instructions(self, tools: Dict) -> str:
        """生成工具使用说明"""
        instructions = []
        
        if "gemini_cli" in tools:
            instructions.append("1. **Gemini CLI**（首选）→ `gemini -p '你的查询'`")
        
        if "duckduckgo" in tools:
            instructions.append("2. **DuckDuckGo**（fallback）→ `from duckduckgo_search import DDGS; DDGS().text('查询', max_results=5)`")
        
        if "tushare" in tools:
            instructions.append("3. **Tushare Pro**（财经数据）→ 使用 tushare.pro_api()")
        
        return "\n".join(instructions) if instructions else "⚠️ 无可用工具，请基于已有数据进行分析"
    
    def _generate_fallback_chain(self, tools: Dict) -> str:
        """生成 fallback 策略"""
        if not tools:
            return "无可用工具，仅使用 Blackboard 已有数据"
        
        chain = []
        for i, (name, info) in enumerate(tools.items(), 1):
            if i == 1:
                chain.append(f"{i}. 首选：{name}")
            else:
                chain.append(f"{i}. Fallback：{name}")
        
        return " → ".join(chain)
```

---

## 实施建议

### Phase 1：立即修复（P0）

1. **修复 tushare_provider.py import 路径**
   ```python
   # data_providers/tushare_provider.py
   from core.data_manager import DataProvider, DataQuery, DataResult, DataFinding
   # 而不是：from data_manager import ...
   ```

2. **添加配置加载机制**
   ```python
   # core/config.py
   import os
   import yaml
   from pathlib import Path
   
   class DeepFlowConfig:
       def __init__(self):
           self.config_path = Path.home() / ".openclaw" / "deepflow.yaml"
           self.config = self._load_config()
       
       def _load_config(self) -> Dict:
           if self.config_path.exists():
               with open(self.config_path) as f:
                   return yaml.safe_load(f)
           return self._default_config()
       
       def _default_config(self) -> Dict:
           """默认配置：自动检测可用工具"""
           return {
               "search": {
                   "primary": {"name": "gemini_cli", "enabled": self._check_gemini()},
                   "fallback": [
                       {"name": "duckduckgo", "enabled": self._check_duckduckgo()},
                       {"name": "web_fetch", "enabled": True}
                   ]
               },
               "data_providers": {
                   "tushare": {"enabled": self._check_tushare(), "token": os.getenv("TUSHARE_TOKEN", "")},
                   "akshare": {"enabled": self._check_akshare()},
                   "sina_finance": {"enabled": True}
               }
           }
   ```

### Phase 2：Prompt 改造（P1）

3. **将 Prompt 改为 Jinja2 模板**
   - 所有 `prompts/investment/*.md` 添加模板变量
   - `{{ search_tools }}`、`{{ data_providers }}`、`{{ fallback_chain }}`

4. **创建 PromptLoader**
   - 加载时注入配置变量
   - 根据可用工具动态生成 instructions

### Phase 3：OpenClaw 集成（P2）

5. **读取 OpenClaw 配置**
   - API Keys（GEMINI_API_KEY、TUSHARE_TOKEN）
   - 用户偏好（模型选择、输出格式）
   - 通知设置（飞书目标用户）

---

## 预期效果

| 当前问题 | 改造后 |
|:---|:---|
| Prompt 写死 gemini CLI | Prompt 动态检测可用工具 |
| tushare 未注册静默失败 | 配置化启用/禁用，失败有明确提示 |
| 新用户需要修改代码适配环境 | 仅需修改 `~/.openclaw/deepflow.yaml` |
| Agent 报告工具不可用 | Agent 根据配置自动选择可用工具 |
| 无法利用 OpenClaw 配置 | 自动读取 OpenClaw 的 API Keys 和偏好 |

---

## 配置示例（用户视角）

```bash
# 1. 安装 DeepFlow
pip install deepflow

# 2. 创建配置文件
cat > ~/.openclaw/deepflow.yaml << 'EOF'
search:
  primary:
    name: "gemini_cli"
    enabled: true

data_providers:
  tushare:
    enabled: true
    token: "your_tushare_token"
  
  akshare:
    enabled: true

output:
  auto_send: true
  feishu_target: "your_feishu_id"
EOF

# 3. 运行分析
deepflow analyze --code 688981.SH --name 中芯国际

# 4. 自动适配环境
# - 如果 gemini 未安装 → 自动使用 duckduckgo
# - 如果 tushare token 未配置 → 自动使用 akshare
# - 所有配置无需修改代码
```

---

## 结论

**用户建议完全正确**。当前 DeepFlow 的硬编码方式导致：
1. 工具不可用时不优雅降级
2. 新用户适配成本高（需修改代码）
3. 无法利用 OpenClaw 已有的配置体系

**建议实施路径**：
1. **立即**：修复 tushare_provider.py import 错误
2. **本周**：创建 `deepflow.yaml` 配置系统 + Prompt 模板化
3. **下周**：集成 OpenClaw 配置读取
4. **持续**：所有新功能必须配置化，禁止硬编码
