"""
DataManager — V1.0 通用数据采集基础设施层

职责：
- 配置驱动采集（YAML 定义 bootstrap + dynamic_rules）
- 数据版本管理（原子写入，v0/v1/vN）
- Agent 数据交互（collect_requests / ingest_findings）
- 数据质量检查（时效性 + 来源验证）

Author: 小满
Date: 2026-04-19
"""

import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.observability import Observability

logger = Observability.get_logger("data_manager")


# ============================================================
# 通用数据类型（不含任何领域术语）
# ============================================================

@dataclass
class DataQuery:
    """通用数据查询请求"""
    source_id: str          # 对应 YAML 中的 id
    params: Dict[str, Any]  # 动态参数
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文


@dataclass
class DataResult:
    """通用数据采集结果"""
    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[bytes] = None


@dataclass
class DataRequest:
    """Agent 提出的数据需求"""
    requestor: str
    data_type: str
    query: str
    priority: str  # "high" / "medium" / "low"
    reason: str


@dataclass
class DataFinding:
    """Agent 发现并回流的数据"""
    discoverer: str
    data_type: str
    key: str
    value: Any
    source: str
    timestamp: str = ""
    confidence: float = 0.5


# ============================================================
# Provider 接口（完全通用）
# ============================================================

class DataProvider(ABC):
    """领域数据提供者接口（每个数据源实现此接口）"""

    @abstractmethod
    def fetch(self, query: DataQuery) -> DataResult:
        """执行数据采集
        
        Args:
            query: 通用查询对象
        Returns:
            采集结果
        """
        ...

    def validate_finding(self, finding: DataFinding) -> bool:
        """验证 Agent 回流的数据质量
        
        默认实现：检查 source 存在 + 数值合理性
        子类可覆盖实现领域特定验证
        """
        if not finding.source or finding.source == "unknown":
            return False
        if finding.confidence < 0.7:
            return False
        return True


# ============================================================
# Provider 注册表
# ============================================================

class ProviderRegistry:
    """Provider 注册表（代码侧注册，配置侧引用）"""
    _providers: Dict[str, DataProvider] = {}

    @classmethod
    def register(cls, name: str, provider: DataProvider) -> None:
        cls._providers[name] = provider

    @classmethod
    def get(cls, name: str) -> DataProvider:
        if name not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(f"Provider '{name}' 未注册。可用: {available}")
        return cls._providers[name]

    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._providers.keys())


# ============================================================
# 条件表达式求值器（JMESPath 沙箱）
# ============================================================

class ConditionEvaluator:
    """dynamic_rules 条件求值器"""

    @staticmethod
    def evaluate(condition: Any, context: Dict[str, Any]) -> bool:
        """求值条件表达式
        
        支持格式：
        - 字符串: "data_request.type == 'competitor'"（简单相等）
        - 字典: {eq: ["a", "b"]}（JMESPath 风格）
        """
        if isinstance(condition, str):
            return ConditionEvaluator._eval_string(condition, context)
        elif isinstance(condition, dict):
            return ConditionEvaluator._eval_dict(condition, context)
        return False

    @staticmethod
    def _eval_string(expr: str, context: Dict[str, Any]) -> bool:
        """简单字符串表达式求值（安全沙箱）"""
        try:
            # 安全替换：将 context 中的变量引用替换为实际值
            replacements = []
            for key, value in context.items():
                if isinstance(value, dict):
                    for k, v in value.items():
                        placeholder = f"{key}.{k}"
                        if isinstance(v, str):
                            # 记录替换，避免影响操作符
                            replacements.append((f"{placeholder}", f"\"{v}\""))
                        else:
                            replacements.append((placeholder, str(v)))

            # 按长度降序替换（避免短占位符误替换长占位符）
            for old, new in sorted(replacements, key=lambda x: len(x[0]), reverse=True):
                expr = expr.replace(old, new)

            # 安全求值（只允许基本比较）
            safe_globals = {"__builtins__": {}}
            return bool(eval(expr, safe_globals, {}))
        except Exception:
            logger.warning("condition_eval_failed", expression=expr)
            return False

    @staticmethod
    def _eval_dict(condition: Dict, context: Dict[str, Any]) -> bool:
        """字典格式条件求值"""
        if "eq" in condition:
            left = ConditionEvaluator._resolve(condition["eq"][0], context)
            right = condition["eq"][1]
            return left == right
        elif "and" in condition:
            return all(ConditionEvaluator.evaluate(c, context) for c in condition["and"])
        elif "or" in condition:
            return any(ConditionEvaluator.evaluate(c, context) for c in condition["or"])
        elif "regex" in condition:
            import re
            pattern = condition["regex"][1]
            value = ConditionEvaluator._resolve(condition["regex"][0], context)
            return bool(re.match(pattern, str(value)))
        return False

    @staticmethod
    def _resolve(expr: str, context: Dict[str, Any]) -> Any:
        """解析 context 中的变量引用"""
        if "." in expr:
            parts = expr.split(".", 1)
            if parts[0] in context and isinstance(context[parts[0]], dict):
                return context[parts[0]].get(parts[1], expr)
        return context.get(expr, expr)


# ============================================================
# 配置驱动采集器
# ============================================================

class ConfigDrivenCollector:
    """通用配置驱动采集器 — 读 YAML，执行采集"""

    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.data_version: int = 0
        self.data_log: List[Dict] = []

    @staticmethod
    def _load_config(config_path: str) -> Dict:
        path = Path(config_path)
        if not path.exists():
            raise ValueError(f"配置文件不存在: {config_path}")
        with open(path) as f:
            return yaml.safe_load(f)

    def get_bootstrap_tasks(self) -> List[Dict]:
        return self.config.get("bootstrap", [])

    def get_dynamic_rules(self) -> List[Dict]:
        return self.config.get("dynamic_rules", [])

    def get_extractor_configs(self) -> List[Dict]:
        return self.config.get("extractors", [])

    def resolve_placeholders(self, config: Dict, context: Dict) -> Dict:
        """替换配置中的 {placeholder} 占位符（P0-3: 支持 Jinja2 风格默认值）"""
        import re
        
        def replace_jinja2_template(text: str, ctx: Dict) -> str:
            """处理 {{ var | default('N/A') }} 风格的模板"""
            pattern = r'\{\{\s*([^|}]+?)\s*(?:\|\s*default\(([^)]+)\))?\s*\}\}'
            
            def replacer(match):
                var_name = match.group(1).strip()
                default_val = match.group(2)
                
                # 解析变量路径（如 data.industry）
                parts = var_name.split('.')
                value = ctx
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        # 变量不存在，使用默认值
                        if default_val:
                            # 去除引号
                            return default_val.strip().strip("'\"")
                        return f"{{{var_name}}}"  # 保留原样
                
                return str(value)
            
            return re.sub(pattern, replacer, text)
        
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str):
                # 先尝试 Jinja2 风格模板
                result = replace_jinja2_template(value, context)
                # 如果仍有普通占位符，尝试 format
                if '{' in result and '}' in result:
                    try:
                        result = result.format(**context)
                    except KeyError:
                        pass  # 保留原文
                resolved[key] = result
            elif isinstance(value, dict):
                resolved[key] = self.resolve_placeholders(value, context)
            else:
                resolved[key] = value
        return resolved

    def get_task_dependencies(self) -> Dict[str, List[str]]:
        """P0-2: 获取任务依赖关系"""
        tasks = self.get_bootstrap_tasks()
        deps = {}
        for task in tasks:
            task_id = task["id"]
            depends_on = task.get("depends_on", [])
            if isinstance(depends_on, str):
                depends_on = [depends_on]
            deps[task_id] = depends_on
        return deps

    def get_execution_order(self) -> List[str]:
        """P0-2: 计算任务执行顺序（拓扑排序）"""
        deps = self.get_task_dependencies()
        tasks = self.get_bootstrap_tasks()
        task_ids = [t["id"] for t in tasks]
        
        # Kahn's algorithm for topological sort
        in_degree = {tid: 0 for tid in task_ids}
        graph = {tid: [] for tid in task_ids}
        
        for task_id, dependencies in deps.items():
            for dep in dependencies:
                if dep in task_ids:
                    graph[dep].append(task_id)
                    in_degree[task_id] += 1
        
        queue = [tid for tid in task_ids if in_degree[tid] == 0]
        order = []
        
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(order) != len(task_ids):
            raise ValueError(f"检测到循环依赖: {set(task_ids) - set(order)}")
        
        return order

    def get_summary_templates(self) -> Dict[str, str]:
        """P0-3: 获取摘要模板配置"""
        return self.config.get("summary_templates", {})

    def render_summary_template(self, template_name: str, data: Dict) -> str:
        """P0-3: 渲染摘要模板（Jinja2 风格，变量缺失时使用默认值）"""
        import re
        
        templates = self.get_summary_templates()
        if template_name not in templates:
            raise ValueError(f"模板 '{template_name}' 不存在。可用模板: {list(templates.keys())}")
        
        template_text = templates[template_name]
        
        # Jinja2 风格：{{ var | default('N/A') }}
        pattern = r'\{\{\s*([^|}]+?)\s*(?:\|\s*default\(([^)]+)\))?\s*\}\}'
        
        def replacer(match):
            var_path = match.group(1).strip()
            default_val = match.group(2)
            
            # 解析嵌套路径（如 financials.name）
            parts = var_path.split('.')
            value = data
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # 变量不存在，使用默认值
                    if default_val:
                        return default_val.strip().strip("'\"")
                    return f"{{{var_path}}}"  # 保留原样
            
            return str(value)
        
        return re.sub(pattern, replacer, template_text)


# ============================================================
# 数据进化循环引擎
# ============================================================

class DataEvolutionLoop:
    """通用数据进化循环（领域无关）"""

    def __init__(self, collector: ConfigDrivenCollector, blackboard,
                 provider_registry: ProviderRegistry = None):
        self.collector = collector
        self.blackboard = blackboard
        self.registry = provider_registry or ProviderRegistry()
        self.data_version: int = 0
        self.data_log: List[Dict] = []

    def bootstrap_phase(self, context: Dict) -> Dict:
        """P0-2: 阶段1 - 初始化采集（支持 depends_on 依赖链）"""
        all_data = {}
        
        # P0-2: 获取执行顺序（拓扑排序）
        try:
            execution_order = self.collector.get_execution_order()
        except ValueError as e:
            logger.error("dependency_resolution_failed", error=str(e))
            execution_order = [t["id"] for t in self.collector.get_bootstrap_tasks()]
        
        # 构建任务 ID 到任务的映射
        task_map = {t["id"]: t for t in self.collector.get_bootstrap_tasks()}
        
        for task_id in execution_order:
            task = task_map[task_id]
            try:
                # P0-2: 将已采集的数据加入 context，供依赖任务使用
                enriched_context = {**context}
                deps = task.get("depends_on", [])
                if isinstance(deps, str):
                    deps = [deps]
                
                for dep_id in deps:
                    if dep_id in all_data:
                        # 将依赖数据注入 context（如 financials.industry）
                        dep_data = all_data[dep_id].get("data", {})
                        if isinstance(dep_data, dict):
                            enriched_context[dep_id] = dep_data
                
                data = self._execute_task(task, enriched_context)
                if data:
                    all_data[task_id] = {
                        "data": data,
                        "source": task.get("provider", "unknown"),
                        "version": self.data_version,
                        "collected_at": datetime.now().isoformat(),
                        "ttl": task.get("ttl", "30d"),
                    }
                    self.data_log.append({
                        "action": "bootstrap_success",
                        "task_id": task_id,
                        "keys": list(data.keys()) if isinstance(data, dict) else 1,
                    })
            except Exception as e:
                self.data_log.append({
                    "action": "bootstrap_failed",
                    "task_id": task.get("id", "unknown"),
                    "error": str(e),
                })
                logger.error("bootstrap_task_failed",
                           task_id=task.get("id"), error=str(e))

        if all_data:
            self._write_to_blackboard(all_data)
            self.data_version += 1

        return all_data

    def collect_requests(self, agent_outputs: List[Dict]) -> List[DataRequest]:
        """阶段2: 从 Agent 输出中提取数据需求"""
        requests = []
        seen = set()

        for output in agent_outputs:
            if "data_requests" in output:
                for req_data in output["data_requests"]:
                    req = DataRequest(
                        requestor=output.get("agent_role", "unknown"),
                        data_type=req_data.get("type", "unknown"),
                        query=req_data.get("query", ""),
                        priority=req_data.get("priority", "medium"),
                        reason=req_data.get("reason", ""),
                    )
                    dedup_key = f"{req.data_type}:{req.query}"
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        requests.append(req)

        return requests

    def fulfill_requests(self, requests: List[DataRequest],
                        context: Dict) -> Dict[str, Any]:
        """阶段3: 执行补充采集"""
        new_data = {}
        priority_order = {"high": 0, "medium": 1, "low": 2}

        for req in sorted(requests,
                         key=lambda r: priority_order.get(r.priority, 1)):
            try:
                # 匹配 dynamic_rules
                data = self._match_and_fulfill(req, context)
                if data:
                    key = f"{req.data_type}_{req.query}"
                    new_data[key] = {
                        "data": data,
                        "source": f"fulfilled_request_{req.requestor}",
                        "version": self.data_version,
                        "collected_at": datetime.now().isoformat(),
                    }
                    self.data_log.append({
                        "action": "fulfilled",
                        "requestor": req.requestor,
                        "query": req.query,
                    })
            except Exception as e:
                self.data_log.append({
                    "action": "request_failed",
                    "requestor": req.requestor,
                    "query": req.query,
                    "error": str(e),
                })

        return new_data

    def ingest_findings(self, agent_outputs: List[Dict]) -> Dict[str, Any]:
        """阶段4: 合并 Agent 回流的数据"""
        findings = {}
        seen_hashes = set()

        for output in agent_outputs:
            if "findings" in output:
                raw_findings = output["findings"]
                # 支持 dict 和 list 两种格式
                if isinstance(raw_findings, dict):
                    findings_list = raw_findings.items()
                elif isinstance(raw_findings, list):
                    findings_list = [(f.get("key", f"finding_{i}"), f)
                                    for i, f in enumerate(raw_findings)]
                else:
                    continue

                for key, finding_data in findings_list:
                    if isinstance(finding_data, dict):
                        finding = DataFinding(
                            discoverer=output.get("agent_role", "unknown"),
                            data_type=finding_data.get("type", "unknown"),
                            key=key,
                            value=finding_data.get("value"),
                            source=finding_data.get("source", "unknown"),
                            timestamp=finding_data.get("timestamp", ""),
                            confidence=finding_data.get("confidence", 0.5),
                        )

                        # 去重：基于 type + key
                        dedup_hash = hash(f"{finding.data_type}:{finding.key}")
                        if dedup_hash in seen_hashes:
                            continue
                        seen_hashes.add(dedup_hash)

                        # 尝试验证
                        try:
                            provider_name = self.collector.config.get("domain", "general")
                            try:
                                provider = self.registry.get(provider_name)
                                is_valid = provider.validate_finding(finding)
                            except ValueError:
                                # provider 未注册，使用 DataProvider 基类默认验证
                                base_provider = DataProvider()
                                # DataProvider 是 ABC，用其子类的默认行为
                                is_valid = (finding.source and
                                           finding.source != "unknown" and
                                           finding.confidence >= 0.7)

                            if is_valid:
                                findings[key] = {
                                    "data": finding.value,
                                    "source": finding.source,
                                    "discoverer": finding.discoverer,
                                    "confidence": finding.confidence,
                                    "version": self.data_version,
                                }
                        except Exception:
                            pass  # 验证失败，跳过

        return findings

    def update_blackboard(self, new_data: Dict[str, Any]) -> None:
        """阶段5: 更新 Blackboard 数据层"""
        if new_data:
            self._write_to_blackboard(new_data)
            self.data_version += 1

    def is_data_fresh(self, dataset_id: str, max_age_hours: int = 4320) -> bool:
        """检查数据是否在有效期内（默认 180 天）"""
        try:
            data_dir = self._get_data_dir()
            latest_version = self._get_latest_version()
            if not latest_version:
                return False

            filepath = data_dir / latest_version / f"{dataset_id}.json"
            if not filepath.exists():
                return False

            data = json.loads(filepath.read_text())
            metadata = data.get("_metadata", {})
            collected_at = metadata.get("collected_at")
            if not collected_at:
                return False

            age = datetime.now() - datetime.fromisoformat(collected_at)
            return age.total_seconds() < max_age_hours * 3600
        except Exception:
            return False

    def get_dataset(self, dataset_id: str,
                   version: str = "latest") -> Optional[Dict]:
        """获取数据集内容"""
        try:
            data_dir = self._get_data_dir()
            if version == "latest":
                ver = self._get_latest_version()
            else:
                ver = version

            if not ver:
                return None

            filepath = data_dir / ver / f"{dataset_id}.json"
            if not filepath.exists():
                return None

            return json.loads(filepath.read_text())
        except Exception:
            return None

    def list_datasets(self) -> List[str]:
        """返回可用数据集列表"""
        try:
            data_dir = self._get_data_dir()
            latest_version = self._get_latest_version()
            if not latest_version:
                return []

            version_dir = data_dir / latest_version
            datasets = []
            for item in version_dir.iterdir():
                if item.is_file() and item.suffix == ".json":
                    datasets.append(item.stem)
            return datasets
        except Exception:
            return []

    # ============================================================
    # 内部方法
    # ============================================================

    def _execute_task(self, task: Dict, context: Dict) -> Any:
        """执行单个采集任务"""
        provider_name = task.get("provider")
        if not provider_name:
            raise ValueError(f"Task {task['id']} 缺少 provider")

        provider = self.registry.get(provider_name)
        config = self.collector.resolve_placeholders(
            task.get("config", {}), context)

        # P0-fix: 传递完整 config，让 provider 自行解析 api 和 params
        query = DataQuery(
            source_id=task["id"],
            params=config,
            context=context,
        )

        result = provider.fetch(query)
        return result.data

    def _match_and_fulfill(self, request: DataRequest,
                          context: Dict) -> Optional[Dict]:
        """匹配 dynamic_rules 并执行采集"""
        rules = self.collector.get_dynamic_rules()

        for rule in rules:
            condition = rule.get("condition")
            if condition and ConditionEvaluator.evaluate(
                    condition, {"data_request": {
                        "type": request.data_type,
                        "query": request.query,
                        "priority": request.priority,
                    }}):
                action = rule.get("action", {})
                provider_name = action.get("provider")
                if not provider_name:
                    continue

                provider = self.registry.get(provider_name)
                action_config = self.collector.resolve_placeholders(
                    action.get("config", {}),
                    {"query": request.query, **context})

                query = DataQuery(
                    source_id=f"dynamic_{request.data_type}",
                    params=action_config,
                    context=context,
                )

                result = provider.fetch(query)
                return result.data

        return None

    def _write_to_blackboard(self, data: Dict) -> None:
        """原子写入 Blackboard/data/vN/"""
        data_dir = self._get_data_dir()
        version_dir = data_dir / f"v{self.data_version}"

        # 使用临时目录 + rename 实现原子写入
        temp_dir = data_dir / f"v{self.data_version}.tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            for key, value in data.items():
                filepath = temp_dir / f"{key}.json"

                # 添加元信息
                if isinstance(value, dict):
                    value["_metadata"] = {
                        "version": self.data_version,
                        "collected_at": value.get(
                            "collected_at", datetime.now().isoformat()),
                        "total_keys": len([
                            k for k in value if not k.startswith("_")]),
                    }

                # 原子写入
                fd, tmp_path = tempfile.mkstemp(
                    dir=temp_dir, suffix='.tmp')
                try:
                    with os.fdopen(fd, 'w') as f:
                        json.dump(value, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.rename(tmp_path, filepath)
                except Exception:
                    os.unlink(tmp_path)
                    raise

            # 原子切换到新版本
            if version_dir.exists():
                import shutil
                shutil.rmtree(version_dir)
            temp_dir.rename(version_dir)

            # 更新 INDEX.json
            self._update_index()

        except Exception:
            # 回滚：清理临时目录
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _update_index(self) -> None:
        """更新 INDEX.json（单一事实来源）"""
        data_dir = self._get_data_dir()
        latest_version = self._get_latest_version()
        if not latest_version:
            return

        index = {}
        version_dir = data_dir / latest_version
        for item in version_dir.iterdir():
            if item.is_file() and item.suffix == ".json":
                dataset_id = item.stem
                try:
                    data = json.loads(item.read_text())
                    metadata = data.get("_metadata", {})
                    ttl_str = metadata.get("ttl", "30d")
                    ttl_days = int("".join(filter(str.isdigit, ttl_str)) or "30")
                    collected_at = metadata.get("collected_at", "")

                    expires_at = ""
                    if collected_at:
                        dt = datetime.fromisoformat(collected_at)
                        expires_at = (dt + timedelta(days=ttl_days)).isoformat()

                    index[dataset_id] = {
                        "path": str(item.relative_to(data_dir)),
                        "version": latest_version,
                        "last_updated": collected_at,
                        "ttl_days": ttl_days,
                        "expires_at": expires_at,
                        "total_keys": metadata.get("total_keys", 0),
                    }
                except Exception:
                    pass

        # 原子写入 INDEX.json
        index_path = data_dir / "INDEX.json"
        fd, tmp_path = tempfile.mkstemp(dir=data_dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, index_path)
        except Exception:
            os.unlink(tmp_path)
            raise

    def _get_data_dir(self) -> Path:
        """获取 Blackboard/data/ 目录"""
        session_dir = getattr(self.blackboard, 'session_dir', None)
        if session_dir:
            return Path(session_dir) / "data"
        # fallback
        return Path(self.blackboard._base_dir) / "data"

    def _get_latest_version(self) -> Optional[str]:
        """获取最新版本号"""
        data_dir = self._get_data_dir()
        if not data_dir.exists():
            return None

        versions = []
        for item in data_dir.iterdir():
            if item.is_dir() and item.name.startswith("v") and not item.name.endswith(".tmp"):
                try:
                    ver_num = int(item.name[1:])
                    versions.append((ver_num, item.name))
                except ValueError:
                    pass

        if not versions:
            return None

        return max(versions)[1]
