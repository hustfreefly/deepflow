# 契约笼子：DeepFlow 搜索配置化改造

## 目标
实现 DeepFlow 搜索工具的混合模式配置化（方案C），同时修正 Gemini 模型版本为 gemini-2.5-flash

## 背景
- 当前 Prompt 硬编码 gemini CLI 命令，但 gemini CLI 无 search 功能
- 真正的 Gemini Search 需要 google.generativeai API + grounding
- 用户确认 Gemini 模型版本应为 gemini-2.5-flash

## 改造范围

### 1. 新建文件
- `core/search_engine.py` - 统一搜索接口
- `data/search_config.yaml` - 默认搜索配置

### 2. 修改文件
- `prompts/investment/researcher_macro_chain.md` - 修改搜索指令
- `prompts/investment/researcher_market.md` - 修改搜索指令
- `prompts/investment/researcher_sentiment.md` - 修改搜索指令
- `prompts/investment/researcher_tech.md` - 修改搜索指令
- `prompts/investment/researcher_management.md` - 修改搜索指令
- `prompts/investment/researcher_finance.md` - 修改搜索指令
- `prompts/investment/auditor.md` - 修改搜索指令

### 3. 配置内容
```yaml
# data/search_config.yaml
search:
  strategy: "quality_first"  # quality_first / speed_first / cost_first
  
  sources:
    gemini:
      enabled: true
      weight: 100
      model: "gemini-2.5-flash"  # 修正为 2.5
      config:
        api_key: "${GEMINI_API_KEY}"
      features:
        - grounding  # 搜索增强
        - citations  # 引用来源
    
    duckduckgo:
      enabled: true
      weight: 80
      features:
        - realtime  # 实时搜索
        - free      # 免费
    
    web_fetch:
      enabled: true
      weight: 60
      features:
        - direct    # 直接抓取

# 领域特定覆盖
domains:
  investment:
    search:
      strategy: "data_driven"
      sources:
        tushare:
          enabled: true
          weight: 100
          config:
            token: "${TUSHARE_TOKEN}"
        gemini:
          weight: 50
```

## 验证清单
- [ ] google-generativeai 已安装
- [ ] search_engine.py 能正确检测可用工具
- [ ] search_engine.py 能按优先级执行搜索
- [ ] Prompt 已更新为使用统一搜索接口
- [ ] 所有 Researcher Prompt 不再硬编码 gemini CLI
- [ ] 配置化文件能被正确读取
- [ ] 无配置时能自动检测并运行
- [ ] Gemini 模型版本为 gemini-2.5-flash

## 实施步骤
1. 安装 google-generativeai
2. 创建 search_engine.py
3. 创建 search_config.yaml
4. 修改所有相关 Prompt
5. 验证搜索功能
