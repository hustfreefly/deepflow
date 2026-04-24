# DeepFlow 配置指南

> **版本**: 0.1.0 (V4.0)  

## 快速开始

### 1. 安装依赖

```bash
# 搜索功能
pip install google-genai duckduckgo-search

# 财经数据（可选）
pip install tushare akshare

# YAML 配置解析
pip install pyyaml
```

### 2. 配置 API Keys

#### 方式一：环境变量（推荐）

```bash
# 添加到 ~/.zshrc 或 ~/.bash_profile
export GEMINI_API_KEY="你的 Gemini API Key"
export TUSHARE_TOKEN="你的 Tushare Token"
```

#### 方式二：配置文件

创建 `~/.openclaw/deepflow.yaml`：

```yaml
search:
  sources:
    gemini:
      enabled: true
      model: "gemini-2.5-flash"
      config:
        api_key: "你的 Gemini API Key"
    
    tushare:
      enabled: true
      config:
        token: "你的 Tushare Token"
```

#### 方式三：直接修改 data/search_config.yaml

```bash
# 编辑 DeepFlow 自带配置
cd ~/.openclaw/workspace/.deepflow
cp data/search_config.yaml data/search_config.yaml.bak
vim data/search_config.yaml
```

### 3. 获取 API Key

#### Gemini API Key

1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 登录 Google 账号
3. 点击 "Get API Key"
4. 复制 Key 到配置中

> ⚠️ **注意**：Gemini API 在某些地区（如中国大陆）可能受限，建议使用 VPN 或代理。

#### Tushare Token

1. 访问 [Tushare 官网](https://tushare.pro/)
2. 注册账号
3. 在个人中心获取 Token
4. 复制 Token 到配置中

> 💡 **提示**：免费版 Tushare 有调用限制，建议升级到 Pro 版（付费）。

---

## 配置文件详解

### 完整配置示例

```yaml
search:
  # 搜索策略
  strategy: "quality_first"  # quality_first / speed_first / cost_first
  
  # 搜索源配置
  sources:
    gemini:
      enabled: true
      weight: 100        # 优先级权重（越高越优先）
      model: "gemini-2.5-flash"
      config:
        api_key: "${GEMINI_API_KEY}"  # 支持环境变量引用
      features:
        - grounding      # Google 搜索增强
        - citations      # 引用来源
    
    duckduckgo:
      enabled: true
      weight: 80
      features:
        - realtime       # 实时搜索
        - free           # 免费
        - anonymous      # 匿名
    
    tushare:
      enabled: true
      weight: 90
      config:
        token: "${TUSHARE_TOKEN}"
      features:
        - financial_data # 财务数据
        - realtime       # 实时行情
    
    web_fetch:
      enabled: true
      weight: 60
      features:
        - direct         # 直接抓取

# 领域特定覆盖
domains:
  investment:
    search:
      strategy: "data_driven"
      sources:
        tushare:
          weight: 100    # 投资领域优先使用 Tushare
        gemini:
          weight: 50     # Gemini 辅助分析
  
  code:
    search:
      strategy: "tech_focused"
      sources:
        gemini:
          weight: 90
```

### 配置优先级

配置加载顺序（后加载覆盖先加载）：

1. `data/search_config.yaml`（默认配置）
2. `~/.openclaw/deepflow.yaml`（用户配置）
3. 环境变量（最高优先级）

---

## 常见问题

### Q: Gemini API 报错 "User location is not supported"

**原因**：Google 限制了某些地区的 API 访问。

**解决方案**：
1. 使用 VPN 或代理
2. 配置代理环境变量：
   ```bash
   export HTTPS_PROXY="http://proxy.example.com:8080"
   ```
3. 或禁用 Gemini，仅使用 DuckDuckGo：
   ```yaml
   search:
     sources:
       gemini:
         enabled: false
   ```

### Q: Tushare 提示 "Token 无效"

**原因**：Token 未配置或已过期。

**解决方案**：
1. 检查 Token 是否正确
2. 确认 Tushare 账号已激活
3. 免费版有调用限制，考虑升级 Pro

### Q: 如何查看当前使用的搜索源？

```python
from core.search_engine import SearchEngine

search = SearchEngine()
print("可用搜索源:", search.get_available_sources())
print("配置详情:", search.get_source_info())
```

### Q: 可以不配置任何 API Key 使用吗？

可以！DeepFlow 会自动检测可用工具：
- 无 Gemini → 使用 DuckDuckGo（免费）
- 无 Tushare → 使用 AKShare（免费）
- 无任何 API → 使用 Web Fetch（基础功能）

---

## 配置验证

```bash
# 测试搜索功能
cd ~/.openclaw/workspace/.deepflow
python3 -c "
from core.search_engine import SearchEngine
search = SearchEngine(domain='investment')
print('可用搜索源:', search.get_available_sources())

# 测试搜索
results = search.search('中芯国际 2026年 业绩', max_results=3)
for r in results:
    print(f'[{r[\"source\"]}] {r[\"title\"]}')
"
```

---

## 更新日志

- **2026-04-24**：添加 google-genai 支持，迁移自 google-generativeai
- **2026-04-24**：添加配置化搜索源优先级
- **2026-04-24**：添加领域特定配置覆盖
