"""PyG Data builder — construct PyTorch Geometric Data objects from service graphs.

Converts the extracted (node_features, edge_index, edge_attr) arrays into
torch_geometric.data.Data objects suitable for GNN model input.

AC-2.5: Graph construction latency < 2s (from span to PyG Data object).

Design note: PyTorch and PyG are optional dependencies. The builder works
with NumPy arrays and converts to tensors only when PyTorch is available.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import numpy as np


# Optional PyTorch / PyG imports
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

try:
    from torch_geometric.data import Data as PyGData

    PYG_AVAILABLE = True
except ImportError:  # pragma: no cover
    PyGData = None  # type: ignore
    PYG_AVAILABLE = False


class PyGDataBuilder:
    """Builder for constructing PyTorch Geometric Data objects.

    Converts the ServiceGraph snapshot output into a PyG Data object with
    node_features, edge_index, and edge_attr tensors. Handles edge cases:
    empty graphs, single-node graphs, and graphs with no edges.

    Attributes:
        device: PyTorch device string ('cpu' or 'cuda').
        dtype: Default tensor dtype.

    Example:
        >>> builder = PyGDataBuilder()
        >>> graph = ServiceGraph()
        >>> # ... ingest spans ...
        >>> node_feats, edge_idx, edge_attr = graph.snapshot()
        >>> data = builder.build(node_feats, edge_idx, edge_attr)
        >>> print(data)  # Data(x=[N,F], edge_index=[2,E], edge_attr=[E,D])
    """

    def __init__(self, device: str = "cpu", dtype: str = "float32") -> None:
        self.device = device
        self._dtype_map = {"float32": np.float32, "float64": np.float64}
        self._np_dtype = self._dtype_map.get(dtype, np.float32)
        self._dtype_str = dtype

    @property
    def is_available(self) -> bool:
        """Check if PyTorch and PyG are both available."""
        return TORCH_AVAILABLE and PYG_AVAILABLE

    def build(
        self,
        node_features: np.ndarray,
        edge_index: np.ndarray,
        edge_attr: np.ndarray,
        graph_id: Optional[str] = None,
    ) -> "PyGData":
        """Build a PyG Data object from graph arrays.

        Args:
            node_features: (N, D_node) float32 array.
            edge_index: (2, E) int64 array.
            edge_attr: (E, D_edge) float32 array.
            graph_id: Optional identifier for the graph snapshot.

        Returns:
            PyG Data object with tensors on the configured device.

        Raises:
            ImportError: If PyTorch or PyG are not installed.
            ValueError: If input arrays have incompatible shapes.
        """
        if not self.is_available:
            raise ImportError(
                "PyTorch and PyTorch Geometric are required for PyG Data construction. "
                "Install with: pip install torch torch-geometric"
            )

        start = time.perf_counter()

        # Validate shapes
        self._validate_shapes(node_features, edge_index, edge_attr)

        # Convert to tensors
        x = self._to_tensor(node_features, dtype=self._np_dtype)
        edge_index_t = self._to_tensor(edge_index, dtype=np.int64)
        edge_attr_t = self._to_tensor(edge_attr, dtype=self._np_dtype)

        # Build PyG Data object
        data = PyGData(
            x=x,
            edge_index=edge_index_t,
            edge_attr=edge_attr_t,
        )

        # Attach metadata
        data.num_nodes = node_features.shape[0]
        data.num_edges = edge_index.shape[1] if edge_index.size > 0 else 0
        if graph_id is not None:
            data.graph_id = graph_id

        elapsed = time.perf_counter() - start
        data._build_time_s = elapsed

        return data

    def build_from_snapshot(
        self,
        snapshot: Tuple[np.ndarray, np.ndarray, np.ndarray],
        graph_id: Optional[str] = None,
    ) -> "PyGData":
        """Convenience method: build from a ServiceGraph.snapshot() output.

        Args:
            snapshot: Tuple of (node_features, edge_index, edge_attr).
            graph_id: Optional graph identifier.

        Returns:
            PyG Data object.
        """
        node_features, edge_index, edge_attr = snapshot
        return self.build(node_features, edge_index, edge_attr, graph_id=graph_id)

    def build_empty_graph(self) -> "PyGData":
        """Build an empty PyG Data object (no nodes, no edges).

        Useful as a placeholder or for testing.

        Returns:
            PyG Data object with zero-length tensors.

        Raises:
            ImportError: If PyTorch or PyG are not installed.
        """
        if not self.is_available:
            raise ImportError("PyTorch and PyTorch Geometric are required.")
        return PyGData(
            x=torch.empty((0, 0), dtype=getattr(torch, self._dtype_str)),
            edge_index=torch.empty((2, 0), dtype=torch.int64),
            edge_attr=torch.empty((0, 0), dtype=getattr(torch, self._dtype_str)),
        )

    def _to_tensor(self, array: np.ndarray, dtype: type = np.float32) -> "torch.Tensor":
        """Convert NumPy array to PyTorch tensor on configured device."""
        t = torch.from_numpy(np.asarray(array, dtype=dtype))
        if self.device != "cpu":
            t = t.to(self.device)
        return t

    @staticmethod
    def _validate_shapes(
        node_features: np.ndarray,
        edge_index: np.ndarray,
        edge_attr: np.ndarray,
    ) -> None:
        """Validate that input arrays have compatible shapes.

        Args:
            node_features: (N, D_node) array.
            edge_index: (2, E) array.
            edge_attr: (E, D_edge) array.

        Raises:
            ValueError: If shapes are incompatible.
        """
        N = node_features.shape[0]

        if edge_index.size == 0:
            # Empty graph with no edges is valid
            return

        if edge_index.ndim != 2 or edge_index.shape[0] != 2:
            raise ValueError(f"edge_index must be (2, E), got {edge_index.shape}")

        E = edge_index.shape[1]

        # Validate edge indices are within bounds
        if edge_index.max() >= N:
            raise ValueError(
                f"edge_index contains node index {edge_index.max()} "
                f"but only {N} nodes exist"
            )
        if edge_index.min() < 0:
            raise ValueError("edge_index contains negative node indices")

        if edge_attr.shape[0] != E:
            raise ValueError(
                f"edge_attr has {edge_attr.shape[0]} rows but edge_index has {E} edges"
            )
