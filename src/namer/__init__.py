# -*- coding: utf-8 -*-
"""批量改名工具（学号-姓名-作业 规范化）。"""
from .core import (
    DEFAULT_TEMPLATE,
    PLACEHOLDERS,
    ApplyResult,
    Entry,
    Plan,
    TemplateError,
    apply_plan,
    build_plan,
    build_new_name,
    default_log_dir,
    parse_name,
    split_template,
    undo_log,
)

__version__ = "1.0.0"
__all__ = [
    "DEFAULT_TEMPLATE", "PLACEHOLDERS", "ApplyResult", "Entry", "Plan",
    "TemplateError", "apply_plan", "build_plan", "build_new_name",
    "default_log_dir", "parse_name", "split_template", "undo_log",
    "__version__",
]
