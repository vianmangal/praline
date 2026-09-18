# Praline compiler / Experience contract

Schema version: **1**. Frozen on 2026-09-18. This file is the integration authority.
Compiler ownership is limited to `praline/frontend/`, `praline/analysis/`,
`praline/transform/`, `praline/model.py`, `tests/unit/`, `tests/fixtures/`, and this file.
Experience owns CLI packaging, doctor, execution, benchmarks, and presentation.
Changes to this contract must be explicitly reported before consumers adopt them.

## Python API (Python 3.10+, standard library only)

```python
from praline.model import AnalysisConfig, PralineError
from praline.analysis import analyze_source
from praline.transform import transform_source

config = AnalysisConfig(
    clang="clang",                  # executable path or name
    clang_args=(),                   # additional compilation flags, e.g. -I...
    timeout_seconds=30.0,
    extents={},                     # buffer NAME -> C extent, e.g. {"input": "n"}
    assume_disjoint=(),              # pairs of buffer NAMES, e.g. (("input", "output"),)
)
analysis = analyze_source("examples/helper_map.c", config=config)  # JSON-native dict
result = transform_source(
    "examples/helper_map.c", analysis, target="cpu", # "cpu" | "gpu"
    output_dir="runs/map-cpu",       # optional; no disk writes if None
    loop_ids=None,                  # None selects all safe loops; tuple selects IDs
)                                  # JSON-native transformation dict
```

`analyze_source` returns schema-v1 report, including on parse/compiler errors.
`transform_source` raises `PralineError` with `.code` and `.message` for stale
source, invalid target/selection, no safe loops, or unsupported generation.
It never transforms unsafe/unknown loops. With `output_dir`, it writes
`generated.c`, `patch.diff`, and `analysis.json` (the returned report with
transformation metadata). It never overwrites the input file. Without an output
directory it returns generated source and diff in memory. API inputs may be
`str` or `pathlib.Path`. Configured assumptions are explicit user contracts,
not facts inferred from pointer names. A successful analysis does not run C code.

The transformation result has exactly these required keys:
`target` (cpu/gpu), `source` (generated C string), `diff` (unified diff string),
`transformed_loop_ids` (string array), `report` (updated full analysis report).
Analysis input is not mutated. Compiler and execution subprocess failures must
be shown distinctly from unsafe or unknown analysis decisions.

## JSON schema

The following JSON Schema describes the required stable fields. Additional
properties are permitted for additive evidence. All required fields exist even
when unavailable. A null field has an explanation in adjacent `reason`,
`limitations`, `errors`, or its enclosing stage's `reason` field. Consumers must
handle empty arrays and null values. Bytes are UTF-8 offsets, end-exclusive;
lines and columns are one-based. AST declaration IDs are opaque and run-local.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Praline report v1",
  "type": "object",
  "required": ["schema_version", "run_id", "created_at", "status", "source", "compiler", "loops", "functions", "assumptions", "recommendation", "artifacts", "validation", "benchmark", "gpu", "errors", "limitations"],
  "properties": {
    "schema_version": {"const": 1},
    "run_id": {"type": "string"},
    "created_at": {"type": "string"},
    "status": {"enum": ["analyzed", "generated", "error"]},
    "source": {"type": "object", "required": ["path", "sha256", "text"], "properties": {"path": {"type": "string"}, "sha256": {"type": ["string", "null"]}, "text": {"type": ["string", "null"]}}},
    "compiler": {"type": "object", "required": ["executable", "version", "command"], "properties": {"executable": {"type": "string"}, "version": {"type": ["string", "null"]}, "command": {"type": "array", "items": {"type": "string"}}}},
    "loops": {"type": "array", "items": {"$ref": "#/$defs/loop"}},
    "functions": {"type": "array", "items": {"$ref": "#/$defs/function"}},
    "assumptions": {"type": "array", "items": {"type": "string"}},
    "recommendation": {"$ref": "#/$defs/recommendation"},
    "artifacts": {"type": "object", "required": ["analysis", "generated", "diff", "validation", "benchmark", "report"], "additionalProperties": {"type": ["string", "null"]}},
    "validation": {"$ref": "#/$defs/stage"},
    "benchmark": {"$ref": "#/$defs/stage"},
    "gpu": {"type": "object", "required": ["status", "reason", "device", "mandatory_offload", "is_initial_device", "compile_command"], "properties": {"status": {"enum": ["unavailable", "generated", "syntax_checked", "compiled", "verified", "failed"]}, "reason": {"type": ["string", "null"]}, "device": {"type": ["object", "null"]}, "mandatory_offload": {"type": ["boolean", "null"]}, "is_initial_device": {"type": ["boolean", "null"]}, "compile_command": {"type": ["array", "null"]}}},
    "errors": {"type": "array", "items": {"type": "object", "required": ["code", "message"], "properties": {"code": {"type": "string"}, "message": {"type": "string"}}}},
    "limitations": {"type": "array", "items": {"type": "string"}}
  },
  "$defs": {
    "span": {"type": ["object", "null"], "required": ["start", "end", "line", "column", "end_line"], "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}, "line": {"type": "integer"}, "column": {"type": "integer"}, "end_line": {"type": "integer"}}},
    "reason": {"type": "object", "required": ["code", "message", "span", "helper_chain"], "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "span": {"$ref": "#/$defs/span"}, "helper_chain": {"type": "array", "items": {"type": "string"}}}},
    "effect": {"type": "object", "required": ["kind", "declaration_id", "name", "storage", "index", "span", "helper_chain"], "properties": {"kind": {"enum": ["read", "write", "escape"]}, "declaration_id": {"type": "string"}, "name": {"type": "string"}, "storage": {"enum": ["parameter", "local", "global", "unknown"]}, "index": {"type": ["string", "null"]}, "span": {"$ref": "#/$defs/span"}, "helper_chain": {"type": "array", "items": {"type": "string"}}}},
    "function": {"type": "object", "required": ["id", "name", "span", "parameters", "effects", "calls", "unknown_reasons", "pure", "return_expression"], "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "span": {"$ref": "#/$defs/span"}, "parameters": {"type": "array"}, "effects": {"type": "array", "items": {"$ref": "#/$defs/effect"}}, "calls": {"type": "array", "items": {"type": "string"}}, "unknown_reasons": {"type": "array", "items": {"$ref": "#/$defs/reason"}}, "pure": {"type": "boolean"}, "return_expression": {"type": ["string", "null"]}}},
    "recommendation": {"type": "object", "required": ["target", "confidence", "reason"], "properties": {"target": {"enum": ["sequential", "cpu", "gpu", "insufficient_evidence"]}, "confidence": {"enum": ["low", "medium", "high"]}, "reason": {"type": "string"}}},
    "loop": {"type": "object", "required": ["id", "function", "span", "source", "decision", "reasons", "assumptions", "iterator", "lower_bound", "upper_bound", "trip_count", "effects", "calls", "mappings", "eligible_targets", "recommendation"], "properties": {"id": {"type": "string"}, "function": {"type": "string"}, "span": {"$ref": "#/$defs/span"}, "source": {"type": "string"}, "decision": {"enum": ["safe", "unsafe", "unknown"]}, "reasons": {"type": "array", "items": {"$ref": "#/$defs/reason"}}, "assumptions": {"type": "array", "items": {"type": "string"}}, "iterator": {"type": ["string", "null"]}, "lower_bound": {"type": ["string", "null"]}, "upper_bound": {"type": ["string", "null"]}, "trip_count": {"type": ["string", "null"]}, "effects": {"type": "array", "items": {"$ref": "#/$defs/effect"}}, "calls": {"type": "array", "items": {"type": "string"}}, "mappings": {"type": "array", "items": {"type": "object", "required": ["name", "declaration_id", "direction", "extent", "extent_source"], "properties": {"name": {"type": "string"}, "declaration_id": {"type": "string"}, "direction": {"enum": ["to", "from", "tofrom"]}, "extent": {"type": ["string", "null"]}, "extent_source": {"type": ["string", "null"]}}}}, "eligible_targets": {"type": "array", "items": {"enum": ["cpu", "gpu"]}}, "recommendation": {"$ref": "#/$defs/recommendation"}}},
    "stage": {"type": "object", "required": ["status", "reason", "results"], "properties": {"status": {"enum": ["not_run", "passed", "failed", "unavailable", "measured"]}, "reason": {"type": ["string", "null"]}, "results": {"type": ["object", "null"]}}}
  }
}
```

`validation.results`, when supplied by Experience, contains `cases` (each with
size, seed, passed, comparison, commands, returncodes, stdout/stderr and source
hashes), `atol`, and `rtol`. Exact integer comparison uses zero tolerances.
`benchmark.results` contains `trials` (variant, size, seed, threads,
seconds, timing_scope), `summaries` (median, spread, speedup), `environment`,
`commands`, and `source_hashes`. Predicted values must never occupy trial fields.
GPU `device` includes model, driver, backend and runtime versions when known.
`verified` requires actual device execution evidence, mandatory offload and
`is_initial_device: false`; successful host fallback is insufficient.

Reason codes initially include `INDEPENDENT_MAP`, `GLOBAL_WRITE`,
`SHARED_WRITE`, `CROSS_ITERATION_DEPENDENCE`, `WRITE_COLLISION`,
`ALIAS_UNRESOLVED`, `UNKNOWN_CALL`, `RECURSION`, `UNSUPPORTED_LOOP`,
`UNSUPPORTED_SYNTAX`, `UNSUPPORTED_ACCESS`, `MACRO_EXPANSION`,
`EXISTING_OPENMP`, `EXTENT_UNKNOWN`, and `VOLATILE_OR_ATOMIC`.
Codes are extensible; the UI must display unfamiliar codes with their messages.
`pure` describes a function's observable effects only, never loop independence.
All shared access pairs still require dependency/alias checks.

## CLI contract (implemented by Experience)

```text
praline doctor [--out RUN_DIR]
praline analyze SOURCE --out RUN_DIR [--clang PATH] [--extent NAME=EXPR] [--assume-disjoint A,B]
praline transform SOURCE --target {cpu,gpu} --out RUN_DIR [--clang PATH] [--extent NAME=EXPR] [--assume-disjoint A,B]
praline validate SOURCE --generated FILE [--sizes 1024,65536,1048576] [--out RUN_DIR]
praline benchmark SOURCE --generated FILE [--sizes 1024,65536,1048576] [--threads 1,2,4] [--trials 5] [--out RUN_DIR]
praline report RUN_DIR
praline demo [--out RUN_DIR]
```

Extent/disjoint options repeat. `transform` calls analysis then transformation;
it does not imply compilation, validation, or measured performance. Exit codes:
0 successful command (including analyzed unsafe/unknown), 1 tool/runtime error,
2 invalid invocation or refused transformation. Execution adapters may further
restrict accepted benchmark programs; arbitrary C stdout is not a validation
protocol. CLI defaults, installation, doctor implementation and rendering remain
Experience integration tasks.

| Run artifact | Producer / meaning |
| --- | --- |
| `analysis.json` | Core or CLI; full version-1 report |
| `generated.c` | Core transformation; separate source |
| `patch.diff` | Core transformation; unified source diff |
| `doctor.json` | Experience; discovered capabilities |
| `validation.json` | Experience; raw equivalence results |
| `benchmark.json` | Experience; raw trials and summaries |
| `report.html` | Experience; static report |

Artifact fields are run-relative names or null. CLI/report merges execution
results into `analysis.json` without replacing static decisions or source hashes.
Execution state belongs in stage fields; top-level status describes core work.

## Supported subset and verification obligations

Start with C11 single translation unit, direct acyclic helpers, canonical unit
stride maps. Only proven/explicitly assumed separate buffers are accepted.
Restrict assumptions, source-validity/bounds preconditions and user extents are
shown explicitly. Unsupported reductions, pointer escapes, function pointers,
macros, recursion and ambiguous ranges are refused conservatively. GPU mappings
preserve untouched output elements (`tofrom` unless full overwrite is proven).
No profitability calibration is part of core: recommendation remains
`insufficient_evidence` for safe loops until Experience supplies measurements.

## Progress and integration log (non-normative)

- 2026-09-18: Contract frozen before implementation. Repository has no existing
  Python package or tests. Apple Clang 21 is available. System Python lacks
  pytest. CPU OpenMP runtime and GPU execution have not yet been verified.
- Remaining integration: Experience must provide CLI/package, doctor, harness,
  report renderer, examples and submission evidence. Core API needs no third-party
  Python runtime dependency. Tests and capability evidence will be recorded here.

### Core implementation handoff — 2026-09-18

The normative contract and public signatures above remain unchanged. The core
is implemented. This section records evidence and remaining integration work;
it does not expand the supported semantics.

- Real Clang JSON extraction preserves declaration identity, UTF-8 byte spans,
  macro provenance and redeclaration chains. Header-defined helper bodies are
  conservatively unresolved. Compiler errors and timeouts have distinct codes.
- Acyclic scalar/pointer helpers have transitive effects and actual-argument
  substitution, including pointer offsets and `&buffer[index]`. Global writes,
  shared scalars, noninjective stores and in-place dependencies are rejected.
  Unknown calls, unsupported indices, recursion and unresolved aliases remain
  unknown. Purity is never a shortcut around dependency checks.
- Restrict separation applies to stable caller parameters. A local alias derived
  from a restrict parameter, a rebound parameter or an address-taken parameter
  does not acquire a false disjointness proof. Named explicit user assumptions
  remain conditional contracts. Distinct fixed local arrays are supported;
  allocation-origin inference for `malloc` is not implemented.
- CPU emits `parallel for default(none) shared(...)`; loop-local variables are
  private by C/OpenMP scope. GPU emits target teams/distribute/parallel-for,
  `declare target` for transitive helpers, scalar captures and array sections.
  Outputs use `tofrom` to preserve untouched/conditional elements. Runtime
  nonpositive extents skip offload. Read-only buffers with unresolved mutual
  overlap can remain CPU-safe but are not GPU-eligible without mapping evidence.
- Supported explicit extents are positive integer literals or visible integer
  scalar names (normally parameters). General C extent expressions are refused. Offset
  accesses currently need numeric bounds and extents. Canonical increments are
  `++i` or `i++`; `i += 1`, reductions, nested loops and indirect calls are not
  supported. No performance or speedup claims are produced.
- Additive report evidence includes loop `helper_ids`, `shared_variables`,
  `firstprivate_variables`, and `generation_reasons`, plus `transformation`
  metadata after generation. Preserve these fields when passing saved analysis
  back to transformation. The containing function may have an unsupported-loop
  summary even when one of its individual loop regions is independently safe.

### Verified locally

On this macOS arm64 host: Apple Clang 21.0.0, Homebrew libomp 23.1.1.
A linked OpenMP probe actually reported `workers=2 devices=0`. CPU threading
works; the installed runtime exposes no target devices. This is not evidence
that the physical Mac lacks a GPU, only that this toolchain cannot verify it.

```sh
/opt/anaconda3/bin/python -m pytest tests/unit -q -p no:cacheprovider
# 55 passed, 1 skipped (real GPU execution)

# Dependency-free alternative; the optional JSON Schema check also skips
# when jsonschema is not installed:
python3 -m unittest discover -s tests/unit -v
```

CPU tests compile both original and generated sources with `-std=c11 -O2`,
then compare every element against an independent formula, including untouched
sentinels. Both scalar and pointer helper kernels pass sizes 0, 1, 2, 31, 1024,
65536; seeds 1, 17, 12345; and one/four CPU threads: 144 program executions
across serial and generated variants. A deliberately wrong kernel fails the
same comparison adapter. This is correctness testing, not benchmark evidence.

The working local CPU OpenMP flags are:

```text
-Xclang -fopenmp -L/opt/homebrew/opt/libomp/lib -Wl,-rpath,/opt/homebrew/opt/libomp/lib -lomp
```

The AST adapter passes `-Xclang -fopenmp` to recognize existing directives even
on Apple Clang, whose driver rejects ordinary `-fopenmp`. Match include paths,
defines and other preprocessing options between analysis and both compiled
variants; source conditional on `_OPENMP` must use consistent OpenMP parsing
flags in the serial reference as well.

GPU scalar/pointer helper output passes real Clang OpenMP syntax checking with
`-std=c11 -Xclang -fopenmp -Werror -fsyntax-only`. Generated GPU source also
compiled to a **host object** in a smoke check. Neither check compiles device
code or verifies GPU execution. The core API correctly returns GPU status
`generated`; external execution code may promote it to `syntax_checked` only
after recording its own command/result. Never promote it to `verified` from
these local tests.

### Compatible Linux GPU verification recipe (not executed here)

Use an LLVM installation with the matching OpenMP target runtime/plugin and
vendor toolchain. On a supported NVIDIA A100 host, for example:

```sh
PRALINE_TEST_CLANG=clang \
PRALINE_TEST_OPENMP_FLAGS='-fopenmp' \
PRALINE_TEST_OFFLOAD_FLAGS='-fopenmp --offload-arch=sm_80' \
python3 -m pytest tests/unit/test_generated_execution.py -v
```

Choose an architecture that matches the actual device. LLVM documents these
flags in its [OpenMP command-line reference](https://openmp.llvm.org/CommandLineArgumentReference.html).
The opt-in GPU test compiles a device probe, sets `OMP_TARGET_OFFLOAD=MANDATORY`,
requires a positive device count and `omp_is_initial_device() == 0`, then compiles
and validates both generated kernels on multiple sizes. It fails rather than
accepting host fallback. Record model, driver, backend, runtime/compiler
versions and complete commands on that host before making submission claims.

### Experience integration still required

1. Package the namespace modules and implement the frozen CLI. Core imports
   already work from the checkout with standard Python; no top-level package,
   CLI, doctor, report or execution files were created by the compiler task.
2. Use `tests/fixtures/helper_map.c` for the safe library kernel (`helper_map`)
   and `tests/fixtures/global_write.c` for the unsafe global-counter kernel.
   `pointer_helper.c` demonstrates transitive pointer effects. The test-only
   `map_driver.c` adapter supplies a `main`; these kernel fixtures alone are not
   standalone executable examples.
3. For GPU analysis of the positive kernels supply
   `AnalysisConfig(extents={"input": "n", "output": "n"})`. CPU safety does not
   require guessed buffer lengths. Show recorded assumptions and per-target
   generation reasons alongside the safe/unsafe/unknown decision.
4. Own validation/benchmark records, timing methodology and profitability policy.
   Merge stage evidence into reports without relabeling static decisions.
   No UI or benchmark harness is included in the core work.
5. GPU hardware validation remains outstanding. Keep the submission description
   at “GPU code generated and syntax-checked; device execution unverified” until
   the compatible-host test and device evidence are available.

Machine-readable local verification evidence is saved under
`tests/fixtures/evidence/core-verification.json`.
