# Tushare 数据获取失败根因深度分析

## 你的质疑完全正确

### 1. 我的根因分析不够深入

我之前的分析停留在表面："Token 未设置"、"ConfigLoader 读取失败"。
但这只是症状，不是真正的根因。

### 2. Token 显式注入确实是大忌

你说得对，将 Token 显式注入到 Task/Prompt 中：
- ❌ 安全风险：Token 会出现在日志、历史记录中
- ❌ 维护困难：每个 Worker 都要改
- ❌ 架构错误：违背了"凭证与代码分离"原则
- ❌ 开源不友好：提交到 Git 会泄露凭证

### 3. 真正的根因分析

#### 现象
- `key_metrics.json` 全 null（262 bytes）
- `main_financial_indicators.json` 有 103KB 数据（bootstrap 成功）
- 没有 `data_manager_result.json`（结果未保存，可能异常退出）

#### 根因链
```
子 Agent 隔离环境
  → 无法访问主环境的 credentials.yaml
  → get_tushare_token() 返回空字符串
  → Tushare API 调用失败（无 Token）
  → fallback 到 realtime_quote（只有股价，无 PE/PB/PS）
  → fallback 到东方财富 API（可能网络受限）
  → 所有字段为 null
  → key_metrics.json 全 null
```

#### 核心问题
**子 Agent（Worker）运行环境与主 Agent 隔离，无法共享配置文件。**

这是 OpenClaw 的架构特性：
- 主 Agent（depth-0）有完整文件系统访问
- 子 Agent（depth-1+）可能是隔离环境
- 环境变量、文件路径可能不一致

### 4. 为什么之前的硬编码能工作？

之前硬编码 token 时：
```python
ts.set_token("c8a3e696e05a145e4c2d9d0452db1fce36d02905c86d2eea8f801880")
```

这确实能工作，因为：
- Token 直接写在代码中
- 子 Agent 执行代码时，Token 已经在代码里
- 不需要读取外部文件

但这正是我们要移除硬编码的原因！

### 5. 正确的解决方案（不立 injection）

#### 方案A：使用 OpenClaw 环境变量传递
OpenClaw 的 `sessions_spawn` 支持 `env` 参数：
```python
sessions_spawn(
    task="...",
    env={"TUSHARE_TOKEN": get_tushare_token()}
)
```

**优点**：
- Token 不出现在代码/Prompt 中
- 只在运行时内存中传递
- 子 Agent 通过 `os.getenv("TUSHARE_TOKEN")` 读取

**缺点**：
- 需要修改 Orchestrator 的 spawn 逻辑
- 每个 Worker 都需要传递

#### 方案B：使用 OpenClaw 的 Secrets/凭证管理
如果 OpenClaw 支持 secrets/credentials 注入：
```yaml
# openclaw.yaml
secrets:
  tushare_token: "xxx"
```

然后子 Agent 自动获得环境变量。

**优点**：
- 最安全的方案
- 符合安全最佳实践

**缺点**：
- 需要确认 OpenClaw 是否支持

#### 方案C：将凭证文件复制到 Blackboard
在 Master Agent 初始化时：
```python
# 将 credentials.yaml 复制到 blackboard/{session_id}/
shutil.copy("data/credentials.yaml", f"blackboard/{session_id}/credentials.yaml")
```

然后 Worker 从 blackboard 读取：
```python
# Worker 中
credentials_path = f"{blackboard_base_path}/credentials.yaml"
```

**优点**：
- 子 Agent 一定能访问（因为 blackboard 是共享目录）
- 不需要修改 spawn 逻辑

**缺点**：
- 凭证文件会出现在 blackboard 中（但 blackboard 是临时目录）
- 需要清理机制

### 6. 推荐方案

**方案C（复制到 Blackboard）+ 方案A（环境变量）结合**：

1. Master Agent 初始化时：
   - 复制 credentials.yaml 到 blackboard/{session_id}/
   - 同时设置环境变量（如果 OpenClaw 支持）

2. Worker 中：
   - 优先从 blackboard 读取 credentials.yaml
   - Fallback 到环境变量
   - 最后 fallback 到默认路径

3. 管线完成后：
   - 清理 blackboard 中的 credentials.yaml（安全）

### 7. 实施计划

```python
# core/master_agent.py - init_session()
def init_session(...):
    # ... 创建目录 ...
    
    # 复制凭证到 blackboard（子 Agent 可访问）
    import shutil
    cred_src = f"{DEEPFLOW_BASE}/data/credentials.yaml"
    cred_dst = f"{base_path}/credentials.yaml"
    if os.path.exists(cred_src):
        shutil.copy(cred_src, cred_dst)
    
    return session_id
```

```python
# core/config_loader.py - 修改加载逻辑
class ConfigLoader:
    def __init__(self, base_path=None, session_id=None):
        # 优先从 blackboard 读取（子 Agent 环境）
        if session_id:
            self.base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
        else:
            self.base_path = DEEPFLOW_BASE
    
    def _load_yaml(self, filename):
        # 1. 尝试从 blackboard 读取（子 Agent）
        filepath = os.path.join(self.base_path, filename)
        if os.path.exists(filepath):
            with open(filepath) as f:
                return yaml.safe_load(f)
        
        # 2. Fallback 到默认路径（主 Agent）
        filepath = os.path.join(DEEPFLOW_BASE, "data", filename)
        # ...
```

### 8. 结论

**真正的根因**：
> 子 Agent 隔离环境无法访问主 Agent 的配置文件，导致凭证读取失败。

**正确的修复**：
> 将凭证复制到 blackboard（子 Agent 可访问的共享目录），而非显式注入到代码/Prompt 中。

**安全原则**：
> 凭证应通过安全通道传递（环境变量、共享凭证文件），绝不显式出现在代码、Prompt、日志中。
