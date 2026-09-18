# Compiler integration

The compiler interface is the separate compiler task's `docs/CONTRACT.md`, schema version 1. No execution module implements safety analysis or an alternative analysis model.

During development in separate checkouts:

```sh
export PRALINE_CORE_ROOT=/absolute/path/to/compiler-checkout
praline demo --out runs/demo
```

`praline/execution/core.py` appends that checkout's package directory to the namespace package search path. It imports the real `AnalysisConfig`, `analyze_source`, and `transform_source` APIs. No mock analysis is supplied. Missing core modules cause a clear unavailable error for analyze/transform. Execution-only validation can still produce JSON and HTML without static-analysis claims.

For the final combined checkout, integrate the compiler task's `praline/model.py`, `praline/frontend/`, `praline/analysis/`, `praline/transform/`, `tests/unit/`, `tests/fixtures/` and `docs/CONTRACT.md`. Preserve the experience files. Remove `PRALINE_CORE_ROOT`, install with `python -m pip install -e '.[test]'`, and rerun `python -m pytest` and `praline demo`. The packaging discovers namespace packages automatically.

The report consumes the frozen schema and keeps static decisions unchanged when adding `validation` and `benchmark` stages. Execution adapters require the explicit `praline-output-v1` program protocol. Arbitrary C stdout is unsupported.

GPU validation additionally requires actual generated-kernel device evidence in `device.initial_device: false`. A separate successful doctor probe does not prove the generated kernel ran on a GPU. Device model, driver, backend and runtime must be captured on the eventual GPU host.

Integration needs: completed core implementation, final combined-checkout verification, and compatible Linux GPU hardware to verify offload. External publication and final form upload are separate steps.
