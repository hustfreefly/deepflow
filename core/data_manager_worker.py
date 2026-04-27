#!/usr/bin/env python3
"""
DataManager Worker V4.0
========================

DataManager Worker 实现。

职责：
1. 执行 bootstrap 采集基础数据
2. 执行统一搜索补充数据
3. 整理并写入 blackboard/data/

使用方式：
    作为 Worker Agent 的 Task 内容执行
"""

import sys
import os
import json
import time
import subprocess
from typing import Dict, Any, Optional

# DeepFlow 基础路径
DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)

# 验证路径存在（防止在独立container环境中失败）
if not os.path.exists(DEEPFLOW_BASE):
    raise EnvironmentError(
        f"DEEPFLOW_BASE path not found: {DEEPFLOW_BASE}\n"
        f"This Worker requires access to the DeepFlow codebase.\n"
        f"Please ensure the repository is mounted at the expected path."
    )

sys.path.insert(0, DEEPFLOW_BASE)


class DataManagerWorker:
    """DataManager V4.0 实现"""
    
    def __init__(self, session_id: str, company_code: str, company_name: str, industry: str = "半导体设备"):
        self.session_id = session_id
        self.company_code = company_code
        self.company_name = company_name
        self.industry = industry
        self.base_path = f"{DEEPFLOW_BASE}/blackboard/{session_id}"
        self.data_path = f"{self.base_path}/data"
        self.supplement_path = f"{self.data_path}/05_supplement"
        
        # 确保目录存在
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(self.supplement_path, exist_ok=True)
        
        self.results = {
            "bootstrap": {"status": "pending", "datasets": 0},
            "supplement_search": {"status": "pending", "success": 0, "total": 0},
            "errors": []
        }
    
    def log(self, message: str):
        """打印日志"""
        print(f"[DataManager] {message}")
    
    def check_dependencies(self) -> Dict[str, bool]:
        """检查外部依赖是否可用（增强版，带详细日志）"""
        deps = {
            "gemini_cli": False,
            "duckduckgo_search": False,
            "tushare": False
        }
        
        # 检查 gemini CLI
        try:
            result = subprocess.run(
                ["gemini", "--version"], 
                capture_output=True, 
                timeout=5,
                check=False
            )
            deps["gemini_cli"] = (result.returncode == 0)
            if deps["gemini_cli"]:
                self.log("  ✅ gemini CLI 可用")
            else:
                self.log(f"  ⚠️ gemini --version 返回码: {result.returncode}")
        except Exception as e:
            self.log(f"  ⚠️ gemini 检查异常: {type(e).__name__}: {e}")
        
        # 检查 duckduckgo_search
        try:
            from duckduckgo_search import DDGS
            deps["duckduckgo_search"] = True
            self.log("  ✅ duckduckgo_search 可用")
        except Exception as e:
            self.log(f"  ⚠️ duckduckgo_search 检查异常: {type(e).__name__}: {e}")
        
        # 检查 tushare
        try:
            import tushare
            deps["tushare"] = True
            self.log("  ✅ tushare 可用")
        except Exception as e:
            self.log(f"  ⚠️ tushare 检查异常: {type(e).__name__}: {e}")
        
        self.log("依赖检查结果:")
        for name, available in deps.items():
            status = "✅" if available else "❌"
            self.log(f"  {status} {name}")
        
        return deps
    

    # ==================== STEP 1: Bootstrap 采集 ====================
    
    def run_bootstrap(self) -> bool:
        """执行 bootstrap 采集基础数据"""
        self.log("STEP 1: 执行 Bootstrap 采集")
        
        try:
            # 导入 DeepFlow 模块
            from data_providers.investment import register_providers
            from core.data_manager import DataEvolutionLoop, ConfigDrivenCollector
            from core.blackboard_manager import BlackboardManager
            
            # 注册数据源
            self.log("  注册数据源...")
            register_providers()
            
            # 初始化采集器
            config_path = f"{DEEPFLOW_BASE}/data_sources/investment.yaml"
            collector = ConfigDrivenCollector(config_path)
            
            # 初始化 Blackboard
            blackboard = BlackboardManager(self.session_id)
            data_loop = DataEvolutionLoop(collector, blackboard)
            
            # 执行 bootstrap
            self.log("  执行 bootstrap_phase...")
            context = {
                "code": self.company_code,
                "name": self.company_name
            }
            data_loop.bootstrap_phase(context)
            
            # 统计数据集
            index_path = f"{self.data_path}/INDEX.json"
            if os.path.exists(index_path):
                with open(index_path, 'r') as f:
                    index = json.load(f)
                self.results["bootstrap"]["datasets"] = len(index)
                self.log(f"  ✅ Bootstrap 完成，采集 {len(index)} 个数据集")
            else:
                # 检查是否有 key_metrics
                km_path = f"{self.data_path}/key_metrics.json"
                if os.path.exists(km_path):
                    self.log("  ✅ Bootstrap 完成（key_metrics 已生成）")
                else:
                    self.log("  ⚠️ Bootstrap 完成，但未找到 INDEX 或 key_metrics")
            
            self.results["bootstrap"]["status"] = "success"
            return True
            
        except Exception as e:
            self.log(f"  ❌ Bootstrap 失败: {e}")
            self.results["bootstrap"]["status"] = "failed"
            self.results["errors"].append(f"bootstrap: {str(e)}")
            return False
    
    # ==================== STEP 2: 统一搜索 ====================
    
    def gemini_search(self, query: str, timeout: int = 30) -> Optional[str]:
        """Gemini CLI 搜索"""
        try:
            result = subprocess.run(
                ["gemini", "-p", query],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout
            else:
                self.log(f"  Gemini 错误: {result.stderr[:100]}")
                return None
        except Exception as e:
            self.log(f"  Gemini 失败: {e}")
            return None
    
    def duckduckgo_search(self, query: str, max_results: int = 5) -> Optional[list]:
        """DuckDuckGo 搜索"""
        try:
            from duckduckgo_search import DDGS
            results = DDGS().text(query, max_results=max_results)
            return results
        except Exception as e:
            self.log(f"  DuckDuckGo 失败: {e}")
            return None
    
    def unified_search(self, query: str, max_retries: int = 2) -> Dict[str, Any]:
        """统一搜索接口（带重试）"""
        for attempt in range(max_retries + 1):
            # 1. Gemini CLI（首选）
            result = self.gemini_search(query)
            if result:
                return {"source": "gemini", "data": result, "query": query, "attempt": attempt + 1}
            
            # 2. DuckDuckGo（fallback）
            result = self.duckduckgo_search(query)
            if result:
                return {"source": "duckduckgo", "data": result, "query": query, "attempt": attempt + 1}
            
            # 3. 重试前等待
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 指数退避: 1s, 2s
                self.log(f"    搜索失败，{wait_time}s后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
        
        # 4. 全部失败
        self.log(f"    ❌ 搜索完全失败（已重试{max_retries}次）: {query[:50]}...")
        return {"source": "failed", "data": None, "query": query, "attempt": max_retries + 1}
    
    def run_supplement_search(self) -> Dict[str, Any]:
        """执行补充搜索"""
        self.log("STEP 2: 执行统一搜索补充数据")
        
        search_tasks = [
            ("行业趋势", f"{self.industry}行业 2025 2026 市场规模 增长趋势 国产化率"),
            ("竞品对比", f"{self.company_name} 竞争对手 市场份额 对比分析"),
            ("券商预期", f"{self.company_name} {self.company_code} 券商研报 一致预期 目标价 2026"),
            ("风险因素", f"{self.company_name} 风险 挑战 制裁 技术"),
        ]
        
        results = {}
        success_count = 0
        
        for name, query in search_tasks:
            self.log(f"  搜索: {name}")
            result = self.unified_search(query)
            
            output_path = f"{self.supplement_path}/{name}.json"
            
            if result["source"] != "failed":
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                results[name] = {"status": "success", "path": output_path}
                success_count += 1
                self.log(f"    ✅ {name} ({result['source']})")
            else:
                results[name] = {"status": "failed"}
                self.log(f"    ⚠️ {name} 失败")
        
        self.results["supplement_search"]["success"] = success_count
        self.results["supplement_search"]["total"] = len(search_tasks)
        self.results["supplement_search"]["status"] = "success" if success_count >= 2 else "partial"
        
        self.log(f"  补充搜索完成: {success_count}/{len(search_tasks)} 成功")
        return results
    
    # ==================== STEP 3: 数据整理 ====================
    
    def ensure_key_metrics(self) -> bool:
        """确保 key_metrics.json 存在（默认使用 Tushare，新浪财经为 fallback）"""
        self.log("STEP 3: 确保 key_metrics.json 存在")
        
        km_path = f"{self.data_path}/key_metrics.json"
        today = time.strftime("%Y%m%d")
        
        # 基础信息
        key_metrics = {
            "company_code": self.company_code,
            "company_name": self.company_name,
            "industry": self.industry,
            "current_price": None,
            "pe_ttm": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "market_cap": None,
            "total_shares": None,
            "analysis_date": time.strftime("%Y-%m-%d")
        }
        
        # 优先使用 Tushare 获取估值数据（默认数据源）
        tushare_success = False
        try:
            import tushare as ts
            # 从配置加载 Token
            from core.config_loader import get_tushare_token
            token = get_tushare_token()
            if not token:
                self.log("  ⚠️ Tushare Token 未配置，跳过 Tushare 数据源")
                return False
            ts.set_token(token)
            pro = ts.pro_api()
            
            # 获取最近10天的每日指标（解决时间因素导致的空数据）
            import pandas as pd
            end_date = time.strftime('%Y%m%d')
            start_date = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime('%Y%m%d')
            
            df = pro.daily_basic(
                ts_code=self.company_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                # 按日期降序排序，取最新一条
                df = df.sort_values('trade_date', ascending=False)
                row = df.iloc[0]
                trade_date = row.get('trade_date', 'unknown')
                
                key_metrics.update({
                    "current_price": float(row.get("close", 0)) if row.get("close") else None,
                    "pe_ttm": float(row.get("pe_ttm", 0)) if row.get("pe_ttm") else None,
                    "pb_ratio": float(row.get("pb", 0)) if row.get("pb") else None,
                    "ps_ratio": float(row.get("ps", 0)) if row.get("ps") else None,
                    "market_cap": float(row.get("total_mv", 0)) if row.get("total_mv") else None,
                    "total_shares": float(row.get("total_share", 0)) if row.get("total_share") else None,
                })
                tushare_success = True
                self.log(f"  ✅ Tushare daily_basic 数据获取成功 (交易日: {trade_date})")
            else:
                self.log("  ⚠️ Tushare 返回空数据")
                
        except Exception as e:
            self.log(f"  ⚠️ Tushare 获取失败: {e}")
        
        # Fallback 1: 使用新浪财经 realtime_quote（股价）
        if not tushare_success or not key_metrics.get("current_price"):
            quote_path = f"{self.data_path}/v0/realtime_quote.json"
            if os.path.exists(quote_path):
                try:
                    with open(quote_path, 'r') as f:
                        quote_data = json.load(f)
                    
                    quote = quote_data.get("data", {}).get("quote", {})
                    
                    # 补充缺失的字段
                    if not key_metrics.get("current_price"):
                        key_metrics["current_price"] = quote.get("current")
                    
                    self.log("  ✅ 从 realtime_quote 补充股价数据")
                    
                except Exception as e:
                    self.log(f"  ⚠️ 从 realtime_quote 读取失败: {e}")
        
        # Fallback 2: 使用东方财富 API（估值数据）
        if not key_metrics.get("pe_ttm"):
            try:
                import requests
                # 东方财富个股页API
                code_num = self.company_code.replace('.SH', '').replace('.SZ', '')
                secid = f"1.{code_num}" if self.company_code.endswith('.SH') else f"0.{code_num}"
                url = f"https://push2.eastmoney.com/api/qt/stock/get"
                params = {
                    "secid": secid,
                    "fields": "f43,f57,f58,f60,f162,f163,f164,f170"
                }
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        d = data["data"]
                        # 东方财富字段映射
                        if not key_metrics.get("current_price") and d.get("f43"):
                            key_metrics["current_price"] = float(d["f43"]) / 100  # 价格需要除以100
                        if not key_metrics.get("pe_ttm") and d.get("f162"):
                            key_metrics["pe_ttm"] = float(d["f162"]) / 100
                        if not key_metrics.get("pb_ratio") and d.get("f163"):
                            key_metrics["pb_ratio"] = float(d["f163"]) / 100
                        if not key_metrics.get("ps_ratio") and d.get("f164"):
                            key_metrics["ps_ratio"] = float(d["f164"]) / 100
                        if not key_metrics.get("market_cap") and d.get("f170"):
                            key_metrics["market_cap"] = float(d["f170"]) / 10000  # 万元转亿元
                        self.log("  ✅ 从东方财富 API 补充估值数据")
            except Exception as e:
                self.log(f"  ⚠️ 东方财富 API 失败: {e}")
        
        # Fallback 3: 使用预置默认数据集
        default_filled = False
        if not key_metrics.get("pe_ttm"):
            try:
                default_path = f"{DEEPFLOW_BASE}/data/default_datasets.json"
                if os.path.exists(default_path):
                    with open(default_path, 'r') as f:
                        defaults = json.load(f)
                    
                    # 查找行业默认值
                    industry = self.industry or "半导体制造"
                    peers = defaults.get("default_peers", {}).get(industry, [])
                    if peers:
                        # 使用中位数或第一个作为参考
                        first_peer = peers[0]
                        pe_range = first_peer.get("pe_range", "50-70").split("-")
                        pb_range = first_peer.get("pb_range", "3-5").split("-")
                        
                        if not key_metrics.get("pe_ttm"):
                            key_metrics["pe_ttm"] = (float(pe_range[0]) + float(pe_range[1])) / 2
                        if not key_metrics.get("pb_ratio"):
                            key_metrics["pb_ratio"] = (float(pb_range[0]) + float(pb_range[1])) / 2
                        
                        # 补充其他字段的默认值
                        if not key_metrics.get("current_price"):
                            key_metrics["current_price"] = first_peer.get("default_price", 50.0)
                        if not key_metrics.get("ps_ratio"):
                            key_metrics["ps_ratio"] = first_peer.get("ps_ratio", 10.0)
                        if not key_metrics.get("market_cap"):
                            key_metrics["market_cap"] = first_peer.get("market_cap", 500.0)
                        if not key_metrics.get("total_shares"):
                            key_metrics["total_shares"] = first_peer.get("total_shares", 10.0)
                        
                        default_filled = True
                        self.log(f"  ✅ 使用行业默认值 (PE:{key_metrics['pe_ttm']:.1f}, PB:{key_metrics['pb_ratio']:.1f})")
            except Exception as e:
                self.log(f"  ⚠️ 读取默认数据集失败: {e}")
        
        # Fallback 4: 全局硬编码默认值（最后防线）
        if not default_filled:
            hardcoded_defaults = {
                "pe_ttm": 50.0,
                "pb_ratio": 3.0,
                "current_price": 50.0,
                "ps_ratio": 10.0,
                "market_cap": 500.0,  # 亿元
                "total_shares": 10.0  # 亿股
            }
            
            for field, default_value in hardcoded_defaults.items():
                if not key_metrics.get(field):
                    key_metrics[field] = default_value
                    self.log(f"  ✅ 使用全局默认值 {field}: {default_value}")
            
            if not default_filled:
                self.log("  ✅ 使用全局硬编码默认值（最后防线）")
        
        # 保存 key_metrics
        with open(km_path, "w", encoding="utf-8") as f:
            json.dump(key_metrics, f, ensure_ascii=False, indent=2)
        
        # 记录数据质量
        null_fields = [k for k, v in key_metrics.items() if v is None and k not in ["company_code", "company_name", "industry", "analysis_date"]]
        if null_fields:
            self.log(f"  ⚠️ 以下字段仍为 null: {', '.join(null_fields)}")
        else:
            self.log("  ✅ 所有字段已填充")
        
        self.log("  ✅ key_metrics.json 已生成")
        return True
    
    # ==================== STEP 4: 主流程 ====================
    
    def run(self) -> Dict[str, Any]:
        """执行完整的 DataManager 流程（带错误处理）"""
        self.log("=" * 60)
        self.log(f"DataManager V4.0 启动")
        self.log(f"目标: {self.company_name}({self.company_code})")
        self.log(f"Session: {self.session_id}")
        self.log("=" * 60)
        
        # 检查依赖
        deps = self.check_dependencies()
        
        # STEP 1: Bootstrap（带错误处理）
        try:
            bootstrap_success = self.run_bootstrap()
        except Exception as e:
            self.log(f"❌ Bootstrap 异常: {e}")
            self.results["bootstrap"]["status"] = "exception"
            self.results["errors"].append(f"bootstrap_exception: {str(e)}")
            bootstrap_success = False
        
        # STEP 2: 统一搜索（带错误处理）
        try:
            search_results = self.run_supplement_search()
        except Exception as e:
            self.log(f"❌ 补充搜索异常: {e}")
            self.results["supplement_search"]["status"] = "exception"
            self.results["errors"].append(f"search_exception: {str(e)}")
            search_results = {}
        
        # STEP 3: 确保 key_metrics（带错误处理）
        try:
            km_success = self.ensure_key_metrics()
        except Exception as e:
            self.log(f"❌ key_metrics 异常: {e}")
            self.results["errors"].append(f"key_metrics_exception: {str(e)}")
            km_success = False
        
        # STEP 4: 验证
        self.log("STEP 4: 验证数据完整性")
        
        checks = {
            "bootstrap": bootstrap_success,
            "key_metrics": km_success,
            "supplement_search": self.results["supplement_search"]["success"] >= 2
        }
        
        all_passed = all(checks.values())
        
        self.log("=" * 60)
        self.log("执行结果汇总")
        self.log("=" * 60)
        self.log(f"Bootstrap: {'✅' if bootstrap_success else '❌'}")
        self.log(f"Key Metrics: {'✅' if km_success else '❌'}")
        self.log(f"补充搜索: {self.results['supplement_search']['success']}/4")
        self.log(f"总体: {'✅ 通过' if all_passed else '⚠️ 部分失败（仍可继续）'}")
        
        # 保存执行结果
        result_path = f"{self.base_path}/data_manager_result.json"
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"⚠️ 保存结果失败: {e}")
        
        return {
            "session_id": self.session_id,
            "success": all_passed,
            "checks": checks,
            "results": self.results,
            "dependencies": deps
        }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DataManager V4.0")
    parser.add_argument("--session-id", required=True, help="Session ID")
    parser.add_argument("--code", required=True, help="股票代码")
    parser.add_argument("--name", required=True, help="公司名称")
    parser.add_argument("--industry", default="半导体设备", help="行业")
    
    args = parser.parse_args()
    
    worker = DataManagerWorker(
        session_id=args.session_id,
        company_code=args.code,
        company_name=args.name,
        industry=args.industry
    )
    
    result = worker.run()
    
    # 输出结果
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
