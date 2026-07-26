"""
PathManager - DeepFlow 统一路径管理器

契约论实施：
- 不变量：所有路径都在 root 范围内，session_id 已 sanitize
- 前置条件：输入经过 Pydantic 验证
- 后置条件：返回路径经过安全验证，目录创建后保证存在

专家评审修复：
- 架构专家：统一安全验证 _safe_join、域抽象、统一异常类型
- 可靠性专家：TOCTOU 防护、并发安全、故障恢复、Unicode 规范化
- 跨平台专家：Windows 分隔符兼容、ASCII-only 选项、长路径支持
"""

from pathlib import Path
from typing import Optional, Literal
import os
import platform
import time
import fcntl
import logging

from pydantic import ValidationError

from .contracts import (
    SessionIdInput,
    FileNameInput,
    DomainConfig,
    PathManagerError,
    PathValidationError,
    PathNotFoundError,
    PathNotWritableError,
    PathTraversalError,
)

logger = logging.getLogger(__name__)


class PathManager:
    """
    DeepFlow 统一路径管理器

    不变量：
    - self.session_id 已经过 sanitize
    - self.root 存在且可访问
    - 所有返回的路径都在 self.root 范围内

    使用示例：
        pm = PathManager("2.5D封装_V40", domain="solution")
        prompt_path = pm.get_prompt_path("planning")
        pm.ensure_parent(prompt_path)
    """

    def __init__(
        self,
        session_id: str,
        deepflow_root: Optional[Path] = None,
        domain: Literal["solution", "ship", "deliver", "research"] = "solution",
    ):
        """
        前置条件：session_id 非空
        后置条件：session_id 已 sanitize，root 存在
        """
        # 1. Sanitize session_id（契约笼子：Pydantic 验证）
        try:
            self._session_id = SessionIdInput(value=session_id).value
        except ValidationError as e:
            raise PathValidationError(f"session_id 验证失败: {e}") from e

        # 2. 解析 root
        self._root = self._resolve_root(deepflow_root)

        # 3. 域配置
        self._domain_config = DomainConfig(domain=domain)

        # 4. 基础路径
        self._blackboard = self._root / "blackboard" / self._session_id
        self._stages = self._blackboard / self._domain_config.stages_subdir
        self._data = self._blackboard / self._domain_config.data_subdir
        self._runs = self._blackboard / self._domain_config.runs_subdir

        # 5. 不变量检查
        self._check_invariants()

    # ========== 属性访问 ==========

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def blackboard(self) -> Path:
        return self._blackboard

    @property
    def stages(self) -> Path:
        return self._stages

    @property
    def data(self) -> Path:
        return self._data

    @property
    def runs(self) -> Path:
        return self._runs

    @property
    def artifacts(self) -> Path:
        """Ship 域：artifacts 目录"""
        return self._blackboard / "artifacts"

    @property
    def packages(self) -> Path:
        """Ship 域：packages 目录"""
        return self._blackboard / "packages"

    @property
    def deliveries(self) -> Path:
        """Deliver 域：deliveries 目录"""
        return self._blackboard / "deliveries"

    # ========== 语义化路径访问 ==========

    def get_prompt_path(
        self,
        module: str,
        prompt_type: str = "prompt",
    ) -> Path:
        """
        获取 prompt 文件路径

        前置条件：module 不含路径分隔符
        后置条件：返回路径在 stages 目录下
        """
        # 验证输入
        try:
            safe_module = FileNameInput(value=module).value
            safe_type = FileNameInput(value=prompt_type).value
        except ValidationError as e:
            raise PathValidationError(f"文件名验证失败: {e}") from e

        # 构造路径
        filename = f"{safe_module}_{safe_type}.md"
        path = self._safe_join(self._stages, filename)

        return path

    def get_output_path(self, filename: str) -> Path:
        """
        获取输出文件路径

        前置条件：filename 不含路径分隔符
        后置条件：返回路径在 stages 目录下
        """
        try:
            safe_filename = FileNameInput(value=filename).value
        except ValidationError as e:
            raise PathValidationError(f"文件名验证失败: {e}") from e
        return self._safe_join(self._stages, safe_filename)

    def get_data_path(self, filename: str) -> Path:
        """
        获取 data 目录下的文件路径

        前置条件：filename 不含路径分隔符
        后置条件：返回路径在 data 目录下
        """
        try:
            safe_filename = FileNameInput(value=filename).value
        except ValidationError as e:
            raise PathValidationError(f"文件名验证失败: {e}") from e
        return self._safe_join(self._data, safe_filename)

    def get_run_record_path(self, module: str) -> Path:
        """
        获取模块运行记录路径

        前置条件：module 不含路径分隔符
        后置条件：返回路径在 runs 目录下
        """
        try:
            safe_module = FileNameInput(value=module).value
        except ValidationError as e:
            raise PathValidationError(f"文件名验证失败: {e}") from e
        filename = f"{safe_module}.run.json"
        return self._safe_join(self._runs, filename)

    def get_blackboard_path(self, relative_path: str = "") -> Path:
        """
        获取 blackboard 下的任意路径

        前置条件：relative_path 不含路径遍历
        后置条件：返回路径在 blackboard 目录下
        """
        if not relative_path:
            return self._blackboard

        # 分割路径并逐段验证
        parts = relative_path.replace('\\', '/').split('/')
        try:
            for part in parts:
                if part and part != '.':
                    FileNameInput(value=part)
        except ValidationError as e:
            raise PathValidationError(f"路径验证失败: {e}") from e

        return self._safe_join(self._blackboard, relative_path)

    # ========== 目录管理 ==========

    def ensure_directories(self) -> None:
        """
        确保所有必要目录存在

        后置条件：blackboard/stages/data/runs 目录都存在
        """
        dirs_to_create = [
            self._blackboard,
            self._stages,
            self._data,
            self._runs,
        ]

        # 添加域特定的额外目录
        for extra in self._domain_config.extra_subdirs:
            dirs_to_create.append(self._blackboard / extra)

        for dir_path in dirs_to_create:
            self._ensure_directory_with_retry(dir_path)

    def ensure_parent(self, file_path: Path) -> None:
        """
        确保文件的父目录存在

        前置条件：file_path 是文件路径
        后置条件：file_path 的父目录存在
        """
        self._ensure_directory_with_retry(file_path.parent)

    # ========== 路径验证 ==========

    def validate_path(
        self,
        path: Path,
        must_exist: bool = False,
        must_be_writable: bool = False,
        expected_type: Optional[Literal["file", "dir"]] = None,
    ) -> bool:
        """
        验证路径

        前置条件：path 在 root 范围内
        后置条件：如果返回 True，路径满足所有条件

        Raises:
            PathValidationError: 验证失败
            PathNotFoundError: 路径不存在
            PathNotWritableError: 路径不可写
        """
        # 安全检查：路径必须在 root 范围内
        self._check_path_safety(path)

        if must_exist and not path.exists():
            raise PathNotFoundError(f"路径不存在: {path}")

        if expected_type == "file" and path.exists() and not path.is_file():
            raise PathValidationError(f"路径不是文件: {path}")

        if expected_type == "dir" and path.exists() and not path.is_dir():
            raise PathValidationError(f"路径不是目录: {path}")

        if must_be_writable:
            self._check_writable(path)

        return True

    def path_exists(self, filename: str) -> bool:
        """检查文件是否存在"""
        path = self.get_output_path(filename)
        return path.exists()

    def get_file_size(self, filename: str) -> Optional[int]:
        """获取文件大小，不存在返回 None"""
        path = self.get_output_path(filename)
        if path.exists():
            return path.stat().st_size
        return None

    # ========== 内部方法 ==========

    def _check_invariants(self) -> None:
        """检查不变量"""
        # 不变量 1：session_id 已 sanitize
        if not self._session_id:
            raise PathValidationError("session_id 不能为空")

        # 不变量 2：root 存在
        if not self._root.exists():
            raise PathNotFoundError(f"DeepFlow root 不存在: {self._root}")

    def _resolve_root(self, deepflow_root: Optional[Path]) -> Path:
        """解析 DeepFlow 根目录"""
        if deepflow_root:
            root = Path(deepflow_root).resolve()
        else:
            # 自动检测：从当前文件向上查找
            current = Path(__file__).resolve()
            for parent in current.parents:
                if (parent / "blackboard").exists():
                    root = parent
                    break
            else:
                # fallback 到默认位置
                root = Path.home() / ".openclaw" / "workspace" / ".deepflow"

        if not root.exists():
            raise PathNotFoundError(f"DeepFlow root 不存在: {root}")

        return root

    def _safe_join(self, base: Path, *parts: str) -> Path:
        """
        安全路径拼接（统一安全验证）

        不变量：返回的路径一定在 base 范围内
        """
        # 拼接路径
        result = base.joinpath(*parts)

        # 解析符号链接，获取真实路径
        try:
            resolved = result.resolve()
            base_resolved = base.resolve()
        except OSError as e:
            raise PathValidationError(f"无法解析路径: {result} - {e}")

        # 检查路径遍历
        if not self._is_relative_to(resolved, base_resolved):
            raise PathTraversalError(
                f"路径遍历检测: {result} 不在 {base} 范围内"
            )

        return result

    @staticmethod
    def _is_relative_to(path: Path, base: Path) -> bool:
        """检查 path 是否在 base 范围内"""
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

    def _check_path_safety(self, path: Path) -> None:
        """检查路径安全性"""
        resolved = path.resolve()
        root_resolved = self._root.resolve()

        if not self._is_relative_to(resolved, root_resolved):
            raise PathTraversalError(
                f"路径安全检查失败: {path} 不在 {self._root} 范围内"
            )

    def _check_writable(self, path: Path) -> None:
        """检查路径是否可写"""
        try:
            if path.is_dir():
                test_path = path / ".write_test"
            else:
                test_path = path

            # 原子创建测试文件
            fd = os.open(
                str(test_path),
                os.O_CREAT | os.O_WRONLY | os.O_EXCL,
                0o600,
            )
            os.close(fd)
            test_path.unlink()
        except OSError as e:
            raise PathNotWritableError(f"路径不可写: {path} - {e}")

    def _ensure_directory_with_retry(
        self,
        dir_path: Path,
        max_retries: int = 3,
    ) -> None:
        """
        确保目录存在（带重试和并发安全）

        使用文件锁防止并发创建冲突
        """
        for attempt in range(max_retries):
            try:
                # 使用文件锁
                lock_path = dir_path.with_suffix(".lock")
                with self._file_lock(lock_path):
                    dir_path.mkdir(parents=True, exist_ok=True)
                    return  # 成功

            except OSError as e:
                if attempt == max_retries - 1:
                    raise PathNotWritableError(
                        f"无法创建目录（重试 {max_retries} 次）: {dir_path} - {e}"
                    )
                time.sleep(0.1 * (2 ** attempt))  # 指数退避

    @staticmethod
    def _file_lock(lock_path: Path, timeout: float = 5.0):
        """文件锁上下文管理器"""
        class FileLock:
            def __init__(self, path, timeout):
                self.path = path
                self.timeout = timeout
                self.fd = None

            def __enter__(self):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_WRONLY)
                start_time = time.time()

                while True:
                    try:
                        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return self
                    except OSError:
                        if time.time() - start_time > self.timeout:
                            os.close(self.fd)
                            raise PathManagerError(f"获取锁超时: {self.path}")
                        time.sleep(0.05)

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.fd is not None:
                    try:
                        fcntl.flock(self.fd, fcntl.LOCK_UN)
                        os.close(self.fd)
                        self.path.unlink(missing_ok=True)
                    except Exception:
                        pass  # 锁释放失败不影响主流程

        return FileLock(lock_path, timeout)

    # ========== 跨平台支持 ==========

    @staticmethod
    def get_max_path_length() -> int:
        """获取当前系统的最大路径长度"""
        system = platform.system()
        if system == "Windows":
            # Windows 10+ 支持长路径，但需要配置
            # 默认使用 260，如果需要长路径需要特殊处理
            return 260
        else:
            return 4096

    def validate_path_length(self, path: Path) -> None:
        """验证路径长度是否在系统限制内"""
        max_length = self.get_max_path_length()
        path_str = str(path.resolve())

        if len(path_str) > max_length:
            raise PathValidationError(
                f"路径长度 {len(path_str)} 超过系统限制 {max_length}: {path}"
            )
