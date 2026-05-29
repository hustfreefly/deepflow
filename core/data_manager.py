"""兼容层：已迁移到 core.data.data_manager"""
from core.data.data_manager import *
from core.data.data_manager import DataProvider, DataQuery, DataResult, DataFinding, Observability, ProviderRegistry
try:
    from core.data.data_manager import DataEvolutionLoop, ConfigDrivenCollector
except ImportError:
    pass
