"""
Config Loader - DeepFlow 统一配置加载器

职责：
- 加载所有配置文件（search, output, credentials）
- 支持环境变量覆盖
- 提供统一的配置访问接口

使用方式：
    from core.config_loader import ConfigLoader
    
    config = ConfigLoader()
    tushare_token = config.get_credential("tushare", "token")
    feishu_target = config.get_output("feishu", "target_open_id")
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

# DeepFlow 基础路径
DEEPFLOW_BASE = "/Users/allen/.openclaw/workspace/.deepflow"


class ConfigLoader:
    """统一配置加载器"""
    
    def __init__(self, base_path: str = DEEPFLOW_BASE):
        self.base_path = base_path
        self._search_config: Optional[Dict] = None
        self._output_config: Optional[Dict] = None
        self._credentials: Optional[Dict] = None
    
    def _load_yaml(self, filename: str) -> Dict:
        """加载 YAML 配置文件"""
        filepath = os.path.join(self.base_path, "data", filename)
        try:
            with open(filepath, 'r') as f:
                config = yaml.safe_load(f) or {}
            # 解析环境变量占位符
            return self._resolve_env_vars(config)
        except FileNotFoundError:
            return {}
        except Exception as e:
            print(f"[ConfigLoader] 加载 {filename} 失败: {e}")
            return {}
    
    def _resolve_env_vars(self, obj: Any) -> Any:
        """递归解析 ${VAR_NAME} 环境变量占位符"""
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.getenv(env_var, "")
        return obj
    
    @property
    def search_config(self) -> Dict:
        """搜索配置"""
        if self._search_config is None:
            self._search_config = self._load_yaml("search_config.yaml")
        return self._search_config
    
    @property
    def output_config(self) -> Dict:
        """输出配置"""
        if self._output_config is None:
            self._output_config = self._load_yaml("output_config.yaml")
        return self._output_config
    
    @property
    def credentials(self) -> Dict:
        """凭证配置"""
        if self._credentials is None:
            self._credentials = self._load_yaml("credentials.yaml")
        return self._credentials
    
    def get_search(self, *keys, default=None) -> Any:
        """获取搜索配置项"""
        return self._get_nested(self.search_config, keys, default)
    
    def get_output(self, *keys, default=None) -> Any:
        """获取输出配置项"""
        return self._get_nested(self.output_config, keys, default)
    
    def get_credential(self, service: str, key: str, default=None) -> Any:
        """
        获取凭证
        
        优先级：
        1. credentials.yaml
        2. 环境变量（自动解析 ${VAR}）
        3. 默认值
        """
        # 1. 从 credentials.yaml 读取
        cred = self.credentials.get("data_sources", {}).get(service, {})
        value = cred.get(key)
        if value:
            return value
        
        # 2. 从环境变量读取
        env_map = {
            "tushare": {"token": "TUSHARE_TOKEN"},
            "gemini": {"api_key": "GEMINI_API_KEY"},
            "google_places": {"api_key": "GOOGLE_PLACES_API_KEY"},
        }
        env_var = env_map.get(service, {}).get(key)
        if env_var:
            value = os.getenv(env_var)
            if value:
                return value
        
        # 3. 尝试从 openclaw.json 读取（飞书凭证）
        if service == "feishu" and key in ["app_id", "app_secret"]:
            value = self._get_from_openclaw_json(service, key)
            if value:
                return value
        
        return default
    
    def _get_from_openclaw_json(self, service: str, key: str) -> Optional[str]:
        """从 openclaw.json 读取凭证"""
        try:
            openclaw_path = os.path.expanduser("~/.openclaw/openclaw.json")
            with open(openclaw_path, 'r') as f:
                import json
                config = json.load(f)
            
            # 飞书凭证路径
            if service == "feishu":
                feishu = config.get("feishu", {})
                if key == "app_id":
                    return feishu.get("appId")
                elif key == "app_secret":
                    return feishu.get("appSecret")
            
            return None
        except Exception:
            return None
    
    def _get_nested(self, data: Dict, keys: tuple, default=None) -> Any:
        """递归获取嵌套字典值"""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def get_feishu_target(self) -> str:
        """获取飞书目标用户 OpenID"""
        # 1. 从 output_config 读取
        target = self.get_output("feishu", "target_open_id")
        if target:
            return target
        
        # 2. 从环境变量读取
        return os.getenv("FEISHU_USER_OPEN_ID", "")
    
    def get_tushare_token(self) -> str:
        """获取 Tushare Token（兼容旧代码）"""
        # 1. 从 credentials.yaml 读取
        token = self.get_credential("tushare", "token")
        if token:
            return token
        
        # 2. 从环境变量读取
        return os.getenv("TUSHARE_TOKEN", "")
    
    def get_gemini_api_key(self) -> str:
        """获取 Gemini API Key（兼容旧代码）"""
        # 1. 从 credentials.yaml 读取
        key = self.get_credential("gemini", "api_key")
        if key:
            return key
        
        # 2. 从环境变量读取
        return os.getenv("GEMINI_API_KEY", "")


# 全局配置实例（单例模式）
_config_instance: Optional[ConfigLoader] = None


def get_config() -> ConfigLoader:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader()
    return _config_instance


# 便捷函数
def get_tushare_token() -> str:
    """获取 Tushare Token"""
    return get_config().get_tushare_token()


def get_gemini_api_key() -> str:
    """获取 Gemini API Key"""
    return get_config().get_gemini_api_key()


def get_feishu_credentials() -> Dict[str, str]:
    """获取飞书凭证"""
    config = get_config()
    return {
        "app_id": config.get_credential("feishu", "app_id", "cli_a917c939e1f91ceb"),
        "app_secret": config.get_credential("feishu", "app_secret", "TIox2Tmsv1RSNNrL2vi9Kg8jvP2bXX5g"),
        "target_open_id": config.get_feishu_target(),
    }