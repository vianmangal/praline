"""The only compiler integration adapter. No analysis semantics live here.

During split-worktree development PRALINE_CORE_ROOT may identify the core
checkout. After integration no environment override is needed.
"""
from __future__ import annotations
import importlib
import os
from pathlib import Path


def _activate():
    root = os.environ.get("PRALINE_CORE_ROOT")
    if root:
        import praline
        package = str(Path(root).resolve() / "praline")
        if not Path(package).is_dir():
            raise RuntimeError("PRALINE_CORE_ROOT must contain the core praline package")
        if package not in praline.__path__:
            praline.__path__ = [*praline.__path__, package]
        importlib.invalidate_caches()


def _modules(*names):
    _activate()
    try:
        return [importlib.import_module("praline."+name) for name in names]
    except ModuleNotFoundError as exc:
        raise RuntimeError("Compiler core is not integrated. Merge the core-owned modules or set PRALINE_CORE_ROOT to the core checkout. See submission/INTEGRATION.md.") from exc


def api():
    _activate()
    try:
        model = importlib.import_module("praline.model")
        analysis = importlib.import_module("praline.analysis")
        transform = importlib.import_module("praline.transform")
    except ModuleNotFoundError as exc:
        raise RuntimeError("Compiler core is not integrated. Merge the core-owned modules or set PRALINE_CORE_ROOT to the core checkout. See submission/INTEGRATION.md.") from exc
    return model.AnalysisConfig, analysis.analyze_source, transform.transform_source


def analyze(source, *, clang="clang", clang_args=(), extents=None,
            assume_disjoint=(), timeout=30):
    model, analysis = _modules("model", "analysis")
    Config, analyze_source = model.AnalysisConfig, analysis.analyze_source
    return analyze_source(source, config=Config(clang=clang, clang_args=tuple(clang_args),
        extents=extents or {}, assume_disjoint=tuple(assume_disjoint), timeout_seconds=timeout))


def transform(source, analysis, *, target, out):
    transform_module, = _modules("transform")
    transform_source = transform_module.transform_source
    return transform_source(source, analysis, target=target, output_dir=out)
