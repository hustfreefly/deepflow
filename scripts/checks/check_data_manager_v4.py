#!/usr/bin/env python3
"""
DataManager V4.0 契约验证脚本
检查 DataManager Worker 输出是否满足契约
"""

import json
import os
import sys
from typing import Dict, List, Tuple


class DataManagerContractVerifier:
    """DataManager V4.0 契约验证器"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.base_path = f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{session_id}/data"
        self.errors = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_failed = 0
    
    def log_check(self, name: str, passed: bool, message: str):
        """记录检查结果"""
        if passed:
            self.checks_passed += 1
            print(f"  ✅ {name}: {message}")
        else:
            self.checks_failed += 1
            self.errors.append(f"{name}: {message}")
            print(f"  ❌ {name}: {message}")
    
    def check_key_metrics(self) -> bool:
        """检查 key_metrics.json 格式"""
        print("\n[Check 1] key_metrics.json 结构验证")
        
        km_path = f"{self.base_path}/key_metrics.json"
        
        # 检查文件存在
        if not os.path.exists(km_path):
            self.log_check("文件存在", False, f"key_metrics.json 不存在: {km_path}")
            return False
        
        # 读取并解析
        try:
            with open(km_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.log_check("JSON解析", False, f"解析失败: {e}")
            return False
        
        # 检查必需字段
        required_fields = [
            "company_code", "company_name", "industry",
            "current_price", "pe_ttm", "pb_ratio", "ps_ratio",
            "market_cap", "total_shares", "analysis_date"
        ]
        
        missing = [f for f in required_fields if f not in data]
        if missing:
            self.log_check("必需字段", False, f"缺少: {missing}")
            return False
        
        self.log_check("必需字段", True, f"所有 {len(required_fields)} 个字段都存在")
        
        # 检查字段类型
        type_checks = {
            "company_code": str,
            "company_name": str,
            "industry": str,
            "current_price": (int, float),
            "pe_ttm": (int, float),
            "pb_ratio": (int, float),
            "ps_ratio": (int, float),
            "market_cap": (int, float),
            "total_shares": (int, float),
            "analysis_date": str
        }
        
        type_errors = []
        for field, expected_type in type_checks.items():
            value = data.get(field)
            if value is not None and not isinstance(value, expected_type):
                type_errors.append(f"{field}: 期望 {expected_type.__name__}, 实际 {type(value).__name__}")
        
        if type_errors:
            self.log_check("字段类型", False, f"类型错误: {type_errors}")
            return False
        
        self.log_check("字段类型", True, "所有字段类型正确")
        return True
    
    def check_index_or_data(self) -> bool:
        """检查 INDEX.json 或数据目录存在"""
        print("\n[Check 2] 数据文件存在性验证")
        
        index_path = f"{self.base_path}/INDEX.json"
        
        if os.path.exists(index_path):
            self.log_check("INDEX.json", True, "存在")
            return True
        
        # 检查是否有其他数据目录
        subdirs = [d for d in os.listdir(self.base_path) 
                   if os.path.isdir(os.path.join(self.base_path, d)) and d != "05_supplement"]
        
        if subdirs:
            self.log_check("数据目录", True, f"找到 {len(subdirs)} 个数据目录: {subdirs}")
            return True
        
        self.log_check("数据存在", False, "INDEX.json 和数据目录都不存在")
        return False
    
    def check_supplement_search(self) -> bool:
        """检查补充搜索结果"""
        print("\n[Check 3] 补充搜索验证")
        
        supplement_dir = f"{self.base_path}/05_supplement"
        
        if not os.path.exists(supplement_dir):
            self.log_check("补充目录", False, "05_supplement 不存在")
            return False
        
        required_searches = ["行业趋势", "竞品对比", "券商预期", "风险因素"]
        found = []
        missing = []
        
        for search_name in required_searches:
            file_path = f"{supplement_dir}/{search_name}.json"
            if os.path.exists(file_path):
                # 检查内容长度
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    content = json.dumps(data)
                    if len(content) >= 100:
                        found.append(search_name)
                    else:
                        missing.append(f"{search_name}(内容太短)")
                except:
                    missing.append(f"{search_name}(解析失败)")
            else:
                missing.append(search_name)
        
        success_rate = len(found) / len(required_searches)
        
        if success_rate >= 0.5:  # 至少50%
            self.log_check("补充搜索", True, f"{len(found)}/4 成功: {found}")
            if missing:
                self.warnings.append(f"缺失: {missing}")
            return True
        else:
            self.log_check("补充搜索", False, f"仅 {len(found)}/4 成功，需要至少2个")
            return False
    
    def check_directory_structure(self) -> bool:
        """检查目录结构"""
        print("\n[Check 4] 目录结构验证")
        
        if not os.path.exists(self.base_path):
            self.log_check("目录存在", False, f"目录不存在: {self.base_path}")
            return False
        
        self.log_check("目录存在", True, self.base_path)
        
        # 检查是否有文件
        files = os.listdir(self.base_path)
        if not files:
            self.log_check("目录非空", False, "目录为空")
            return False
        
        self.log_check("目录非空", True, f"包含 {len(files)} 个文件/目录")
        return True
    
    def run_all_checks(self) -> Dict:
        """运行所有检查"""
        print(f"\n{'='*60}")
        print(f"DataManager V4.0 契约验证")
        print(f"Session: {self.session_id}")
        print(f"{'='*60}")
        
        checks = [
            ("目录结构", self.check_directory_structure),
            ("key_metrics.json", self.check_key_metrics),
            ("数据文件存在性", self.check_index_or_data),
            ("补充搜索", self.check_supplement_search),
        ]
        
        results = {}
        for name, check_func in checks:
            results[name] = check_func()
        
        # 输出汇总
        print(f"\n{'='*60}")
        print("验证结果汇总")
        print(f"{'='*60}")
        print(f"通过: {self.checks_passed}")
        print(f"失败: {self.checks_failed}")
        
        if self.warnings:
            print(f"\n警告:")
            for w in self.warnings:
                print(f"  ⚠️ {w}")
        
        if self.errors:
            print(f"\n错误:")
            for e in self.errors:
                print(f"  ❌ {e}")
        
        all_passed = all(results.values())
        print(f"\n{'='*60}")
        print(f"总体: {'✅ 通过' if all_passed else '❌ 失败'}")
        print(f"{'='*60}")
        
        return {
            "session_id": self.session_id,
            "all_passed": all_passed,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "results": results,
            "errors": self.errors,
            "warnings": self.warnings
        }


if __name__ == "__main__":
    # 测试用法
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
    else:
        # 查找最新的 session
        blackboard_base = "/Users/allen/.openclaw/workspace/.deepflow/blackboard"
        if os.path.exists(blackboard_base):
            sessions = [d for d in os.listdir(blackboard_base) 
                       if os.path.isdir(os.path.join(blackboard_base, d))]
            if sessions:
                session_id = sorted(sessions)[-1]
                print(f"使用最新 session: {session_id}")
            else:
                print("错误: 没有找到 session")
                sys.exit(1)
        else:
            print("错误: blackboard 目录不存在")
            sys.exit(1)
    
    verifier = DataManagerContractVerifier(session_id)
    result = verifier.run_all_checks()
    
    sys.exit(0 if result["all_passed"] else 1)