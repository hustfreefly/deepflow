# deepflow.diagnostics package
"""
DeepFlow Diagnostics Module

This module provides tools for validating and extracting OpenClaw diagnostics data.
It supports monitoring and observability for the DeepFlow multi-agent pipeline framework.

_features:
    - Diagnostics data validation (7-item checklist)
    - Field mapping with fallback support
    -粗粒度 duration extraction from stage files
"""

from .validation import validate_diagnostics
from .fallback_extractor import extract_duration_from_stages

__all__ = ['validate_diagnostics', 'extract_duration_from_stages']
