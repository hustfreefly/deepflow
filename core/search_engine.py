#!/usr/bin/env python3
"""
SearchEngine - DeepFlow 统一搜索接口（方案C：混合模式）

职责：
- 自动检测可用搜索工具（Gemini API, DuckDuckGo, WebFetch）
- 按配置优先级执行搜索
- 支持领域特定覆盖
- 无配置时自动检测并智能排序

使用方式：
    from core.search_engine import SearchEngine
    
    search = SearchEngine(domain="investment")
    results = search.search("中芯国际 2026年 业绩")
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("search_engine")

# DeepFlow 基础路径
DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"


class SearchEngine:
    """统一搜索接口 - 混合模式（配置化 + 自动检测）"""
    
    def __init__(self, domain: str = "general", config_path: Optional[str] = None):
        """
        初始化搜索引擎
        
        Args:
            domain: 领域名称（如 investment, code），用于加载领域特定配置
            config_path: 配置文件路径，默认使用 data/search_config.yaml
        """
        self.domain = domain
        self.config = self._load_config(config_path)
        self.sources = self._initialize_sources()
        
        logger.info(f"SearchEngine 初始化完成: domain={domain}, sources={list(self.sources.keys())}")
    
    # ==================== 配置加载 ====================
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """加载搜索配置"""
        # 1. 尝试读取配置文件
        if config_path is None:
            config_path = f"{DEEPFLOW_BASE}/data/search_config.yaml"
        
        config = {}
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"已加载配置文件: {config_path}")
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}，使用默认配置")
        
        # 2. 合并领域特定配置
        domain_config = config.get("domains", {}).get(self.domain, {})
        if domain_config:
            logger.info(f"应用领域配置: {self.domain}")
        
        # 3. 合并配置（领域覆盖全局）
        merged = {**config.get("search", {}), **domain_config.get("search", {})}
        
        # 4. 如果没有配置，使用自动检测
        if not merged.get("sources"):
            merged["sources"] = self._auto_detect_sources()
            logger.info("使用自动检测的搜索源")
        
        return merged
    
    def _auto_detect_sources(self) -> Dict[str, Any]:
        """自动检测可用搜索工具"""
        sources = {}
        
        # 检测 Gemini API
        gemini_available = self._check_gemini_api()
        if gemini_available:
            sources["gemini"] = {
                "enabled": True,
                "weight": 100,
                "model": "gemini-2.5-flash",  # 用户指定的模型版本
                "config": {
                    "api_key": os.getenv("GEMINI_API_KEY", "")
                },
                "features": ["grounding", "citations"]
            }
            logger.info("✅ 检测到 Gemini API")
        
        # 检测 DuckDuckGo
        ddg_available = self._check_duckduckgo()
        if ddg_available:
            sources["duckduckgo"] = {
                "enabled": True,
                "weight": 80,
                "features": ["realtime", "free"]
            }
            logger.info("✅ 检测到 DuckDuckGo")
        
        # 检测 Tushare（投资领域）
        if self.domain == "investment":
            tushare_available = self._check_tushare()
            if tushare_available:
                sources["tushare"] = {
                    "enabled": True,
                    "weight": 90,
                    "config": {
                        "token": os.getenv("TUSHARE_TOKEN", "")
                    },
                    "features": ["financial_data", "realtime"]
                }
                logger.info("✅ 检测到 Tushare")
        
        # 总是启用 web_fetch 作为最后 fallback
        sources["web_fetch"] = {
            "enabled": True,
            "weight": 60,
            "features": ["direct"]
        }
        
        return sources
    
    # ==================== 工具检测 ====================
    
    def _check_gemini_api(self) -> bool:
        """检查 Gemini API 是否可用"""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.debug("GEMINI_API_KEY 未设置")
            return False
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            # 快速验证：列出模型
            client.models.list()
            return True
        except ImportError:
            logger.debug("google-genai 未安装")
            return False
        except Exception as e:
            logger.debug(f"Gemini API 检查失败: {e}")
            return False
    
    def _check_duckduckgo(self) -> bool:
        """检查 DuckDuckGo 是否可用"""
        try:
            from duckduckgo_search import DDGS
            return True
        except ImportError:
            logger.debug("duckduckgo_search 未安装")
            return False
    
    def _check_tushare(self) -> bool:
        """检查 Tushare 是否可用"""
        # 支持多种配置方式：环境变量、配置文件
        token = (os.getenv("TUSHARE_TOKEN") or 
                self._get_config_token("tushare"))
        
        if not token:
            logger.debug("TUSHARE_TOKEN 未配置")
            return False
        
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            # 快速验证
            pro.trade_cal(exchange='SSE', limit=1)
            return True
        except ImportError:
            logger.debug("tushare 未安装")
            return False
        except Exception as e:
            logger.debug(f"Tushare 检查失败: {e}")
            return False
    
    def _get_config_token(self, source_name: str) -> Optional[str]:
        """从配置文件获取 token"""
        sources = self.config.get("sources", {})
        source_config = sources.get(source_name, {})
        config = source_config.get("config", {})
        return config.get("token", "")
    
    # ==================== 搜索源初始化 ====================
    
    def _initialize_sources(self) -> Dict[str, Any]:
        """初始化搜索源"""
        sources = {}
        
        for name, config in self.config.get("sources", {}).items():
            if not config.get("enabled", True):
                continue
            
            # 检查源是否实际可用
            if name == "gemini" and not self._check_gemini_api():
                logger.warning(f"Gemini API 不可用，跳过")
                continue
            
            if name == "duckduckgo" and not self._check_duckduckgo():
                logger.warning(f"DuckDuckGo 不可用，跳过")
                continue
            
            if name == "tushare" and not self._check_tushare():
                logger.warning(f"Tushare 不可用，跳过")
                continue
            
            sources[name] = config
        
        # 按权重排序
        return dict(sorted(sources.items(), 
                          key=lambda x: x[1].get("weight", 0), 
                          reverse=True))
    
    # ==================== 统一搜索接口 ====================
    
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        统一搜索接口 - 自动选择最佳工具
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            
        Returns:
            搜索结果列表，每个结果包含:
            {
                "title": "标题",
                "content": "内容摘要",
                "url": "来源URL",
                "source": "gemini|duckduckgo|web_fetch|tushare",
                "confidence": 0.9,
                "query": "原始查询"
            }
        """
        logger.info(f"搜索: {query[:80]}...")
        
        # 按优先级尝试各个搜索源
        for source_name, source_config in self.sources.items():
            try:
                if source_name == "gemini":
                    results = self._gemini_search(query, max_results)
                elif source_name == "duckduckgo":
                    results = self._duckduckgo_search(query, max_results)
                elif source_name == "tushare":
                    results = self._tushare_search(query)
                elif source_name == "web_fetch":
                    results = self._web_fetch_search(query, max_results)
                else:
                    continue
                
                if results:
                    logger.info(f"✅ {source_name} 搜索成功，返回 {len(results)} 条结果")
                    return results
                    
            except Exception as e:
                logger.warning(f"⚠️ {source_name} 搜索失败: {e}")
                continue
        
        logger.error(f"❌ 所有搜索源均失败: {query[:80]}...")
        return []
    
    # ==================== 具体搜索实现 ====================
    
    def _gemini_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """使用 Gemini API (google-genai) grounding 搜索"""
        from google import genai
        
        config = self.sources.get("gemini", {}).get("config", {})
        # 从配置加载 API Key
        from core.config_loader import get_gemini_api_key
        api_key = config.get("api_key") or get_gemini_api_key()
        
        if not api_key:
            logger.warning("Gemini API Key 未配置")
            return False
        model_name = config.get("model", "gemini-2.5-flash")
        
        client = genai.Client(api_key=api_key)
        
        try:
            # 使用 grounding（搜索增强）
            response = client.models.generate_content(
                model=model_name,
                contents=query,
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
                )
            )
            
            results = [{
                "title": "Gemini Search Result",
                "content": response.text,
                "url": "",
                "source": "gemini",
                "confidence": 0.9,
                "query": query
            }]
            
            return results[:max_results]
            
        except Exception as e:
            error_msg = str(e)
            if "User location is not supported" in error_msg:
                logger.warning("Gemini API 地理限制：当前地区不支持 API 使用，建议使用 VPN 或切换到 DuckDuckGo")
            else:
                logger.warning(f"Gemini 搜索失败: {e}")
            return []
    
    def _duckduckgo_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """使用 DuckDuckGo 搜索"""
        from duckduckgo_search import DDGS
        
        results = []
        ddg_results = DDGS().text(query, max_results=max_results)
        
        for r in ddg_results:
            results.append({
                "title": r.get("title", ""),
                "content": r.get("body", ""),
                "url": r.get("href", ""),
                "source": "duckduckgo",
                "confidence": 0.7,
                "query": query
            })
        
        return results
    
    def _tushare_search(self, query: str) -> List[Dict[str, Any]]:
        """使用 Tushare 搜索财经数据"""
        import tushare as ts
        
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            return []
        
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 解析查询（简单关键词匹配）
        # 这里可以做得更智能，比如用 NLP 解析查询意图
        results = []
        
        # 如果是股票代码查询
        if ".SH" in query or ".SZ" in query or query.isdigit():
            code = query.strip()
            try:
                df = pro.daily_basic(ts_code=code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    results.append({
                        "title": f"{code} 基本面数据",
                        "content": f"PE: {row.get('pe', 'N/A')}, PB: {row.get('pb', 'N/A')}",
                        "url": "",
                        "source": "tushare",
                        "confidence": 0.95,
                        "query": query
                    })
            except Exception as e:
                logger.warning(f"Tushare 查询失败: {e}")
        
        return results
    
    def _web_fetch_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """使用 web_fetch 搜索（简化实现）"""
        # 构建搜索 URL
        search_url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}"
        
        try:
            import urllib.request
            req = urllib.request.Request(
                search_url, 
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            
            return [{
                "title": "Web Fetch Result",
                "content": content[:2000],
                "url": search_url,
                "source": "web_fetch",
                "confidence": 0.5,
                "query": query
            }]
        except Exception as e:
            logger.warning(f"Web fetch 失败: {e}")
            return []
    
    # ==================== 工具信息 ====================
    
    def get_available_sources(self) -> List[str]:
        """获取当前可用的搜索源列表"""
        return list(self.sources.keys())
    
    def get_source_info(self) -> Dict[str, Any]:
        """获取搜索源详细信息（用于 Prompt 生成）"""
        info = {}
        for name, config in self.sources.items():
            info[name] = {
                "enabled": config.get("enabled", True),
                "weight": config.get("weight", 0),
                "features": config.get("features", []),
                "model": config.get("model", "") if name == "gemini" else ""
            }
        return info


def get_search_tools_prompt() -> str:
    """生成搜索工具说明（用于 Prompt 模板）"""
    engine = SearchEngine()
    sources = engine.get_source_info()
    
    lines = ["## 可用搜索工具（已自动检测）"]
    
    for name, info in sources.items():
        if not info["enabled"]:
            continue
        
        features = ", ".join(info["features"])
        weight = info["weight"]
        
        if name == "gemini":
            lines.append(f"1. **Gemini Search** (weight={weight}) - 使用 Gemini 2.5 Flash 模型 + Google 搜索增强")
            lines.append(f"   - 特点: {features}")
            lines.append(f"   - 使用: `from core.search_engine import SearchEngine; search = SearchEngine(); results = search.search('查询')`")
        elif name == "duckduckgo":
            lines.append(f"2. **DuckDuckGo** (weight={weight}) - 免费匿名搜索引擎")
            lines.append(f"   - 特点: {features}")
            lines.append(f"   - 使用: 同上，SearchEngine 会自动 fallback")
        elif name == "tushare":
            lines.append(f"3. **Tushare** (weight={weight}) - 中国财经数据接口")
            lines.append(f"   - 特点: {features}")
            lines.append(f"   - 使用: 同上，投资领域自动优先")
        elif name == "web_fetch":
            lines.append(f"4. **Web Fetch** (weight={weight}) - 直接网页抓取")
            lines.append(f"   - 特点: {features}")
    
    lines.append("")
    lines.append("## 使用方式")
    lines.append("```python")
    lines.append("import sys")
    lines.append(f'sys.path.insert(0, "{DEEPFLOW_BASE}")')
    lines.append("from core.search_engine import SearchEngine")
    lines.append("")
    lines.append("search = SearchEngine(domain='investment')  # 投资领域自动优化")
    lines.append("results = search.search('你的查询', max_results=5)")
    lines.append("# results: [{title, content, url, source, confidence}]")
    lines.append("```")
    
    return "\n".join(lines)


# 测试
if __name__ == "__main__":
    print("=== DeepFlow SearchEngine 测试 ===\n")
    
    engine = SearchEngine(domain="investment")
    
    print(f"可用搜索源: {engine.get_available_sources()}")
    print(f"\n搜索源详情:")
    print(json.dumps(engine.get_source_info(), indent=2, ensure_ascii=False))
    
    print("\n=== Prompt 模板 ===")
    print(get_search_tools_prompt())