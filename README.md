# Praline

Praline helps you understand whether a C loop can safely run in parallel—even when it calls another function.

It reads the code with Clang, checks what each helper function reads and writes, and explains its decision. For supported safe loops, it generates OpenMP code, checks the output, and measures the runtime.

Built for **SegFault 2026 · P05: Automatic Parallelizing Compiler for GPGPU with Interprocedural Analysis**.

## What it does

- Finds supported loops and follows their helper-function calls.
- Identifies shared writes, dependencies between iterations, and unresolved pointer aliasing.
- Reports each loop as **safe**, **unsafe**, or **unknown**, with source-level reasons.
- Generates CPU OpenMP code and GPU target code with explicit data mappings.
- Compares every output element against sequential execution and an independent reference.
- Creates a local HTML report with analysis, generated code, validation, and timings.

Praline supports a focused C11 subset. Unsupported or uncertain cases are reported rather than automatically parallelized.

## Try it

You need **Python 3.11+**, **Clang**, and an **OpenMP runtime** for CPU execution.

On macOS, install the runtime if it is missing:

```sh
brew install libomp
```

Clone the repository and run the demo:

```sh
git clone https://github.com/vianmangal/praline.git
cd praline

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'

praline doctor --out runs/toolchain
praline demo --out runs/demo
```

Run these commands from the repository root. The doctor command checks the installed compiler and actually compiles and runs capability probes.

Open **`runs/demo/map-cpu/report.html`** in your browser. On macOS:

```sh
open runs/demo/map-cpu/report.html
```

## Run the localhost interface

Start the browser interface from the repository root:

```sh
praline serve
```

Praline opens `http://127.0.0.1:8000`. From there you can paste C source or
upload a `.c` file, choose CPU or GPU generation, run the real analysis, inspect
the decision and download generated source. The localhost interface analyzes
and transforms source; it does not execute arbitrary uploaded C programs.

The demo analyzes the safe example, generates CPU code, validates its output, records timings, and analyzes several unsafe or uncertain examples. It also generates GPU source.

## A simple example

A loop might call a helper for each array element:

```c
static int apply(int value) {
    return value * 3 + 1;
}

void map(const int *restrict input, int *restrict output, int n) {
    for (int index = 0; index < n; ++index) {
        output[index] = apply(input[index]);
    }
}
```

Praline checks the helper's effects, the array accesses, and the alias assumptions before generating a parallel loop. A read-only helper alone is not enough to establish safety.

If the helper instead increments a shared global counter, Praline identifies the shared write and refuses the transformation.

The `restrict` contract and valid array bounds are assumptions the caller must satisfy. Different pointer names do not establish separate buffers.

## Use it step by step

### 1. Analyze a program

```sh
praline analyze examples/helper_map.c --out runs/map
```

### 2. Generate CPU OpenMP code

```sh
praline transform examples/helper_map.c --target cpu --out runs/map-cpu
```

The original stays unchanged. The output directory contains the generated source, a diff, analysis JSON, and an HTML report.

### 3. Check the output

```sh
praline validate examples/helper_map.c \
  --generated runs/map-cpu/generated.c \
  --out runs/map-cpu \
  --sizes 0,1,1024,65536,1048576 \
  --seeds 1,7 --threads 2
```

### 4. Measure performance

```sh
praline benchmark examples/helper_map.c \
  --generated runs/map-cpu/generated.c \
  --out runs/map-cpu \
  --sizes 1024,65536,1048576 \
  --seeds 1,7 --threads 1,2,4 \
  --trials 5 --warmups 1
```

### 5. Inspect an unsafe example

```sh
praline analyze examples/global_write.c --out runs/unsafe
```

Use `praline --help` or `praline <command> --help` for more options.

## Examples

| File | What it demonstrates |
| --- | --- |
| [helper_map.c](examples/helper_map.c) | A supported map with a safe helper call |
| [global_write.c](examples/global_write.c) | A helper writes shared global state |
| [prefix_dependency.c](examples/prefix_dependency.c) | One iteration depends on another |
| [scatter_write.c](examples/scatter_write.c) | Iterations can write to the same element |
| [alias_unknown.c](examples/alias_unknown.c) | Buffer separation cannot be established |
| [unknown_call.c](examples/unknown_call.c) | A called function's effects are unknown |

## What works today

The integrated checkout passed **64 tests, with 3 skips** in the local verification run.

Recorded CPU evidence includes **30 output-validation cases** and **300 timed executions** on an arm64 Mac using Apple Clang and Homebrew libomp.

The simple helper-map benchmark was **slower with OpenMP** on this host. That result matters: a loop can be safe to parallelize without being worth parallelizing. We retain the raw measurements and do not claim universal speedup.

GPU source is generated and has been checked with host-side OpenMP syntax checks. **Execution on a GPU has not been verified.** There are no GPU performance results.

- [Recorded measurements](submission/results.md)
- [Analysis and execution evidence](submission/evidence/)
- [Submission status](submission/MANIFEST.md)

## GPU code generation

Generate GPU target directives with explicit buffer lengths:

```sh
praline transform examples/helper_map.c \
  --target gpu \
  --extent input=n --extent output=n \
  --out runs/map-gpu
```

Running this code requires a compatible OpenMP offload compiler, runtime, and device. A Mac GPU is not assumed to provide that environment.

On a compatible Linux host, configure `CC` and `PRALINE_OFFLOAD_FLAGS` for the installed backend, then run `praline doctor`. The probes require mandatory offload and check that execution happened on a non-host device.

The current execution examples still need generated-kernel device instrumentation before GPU validation can pass. A successful compiler invocation or CPU fallback does not establish GPU execution.

See [the compiler contract](docs/CONTRACT.md) for the compatible-host test recipe and supported generation details.

## Reading the results

The report keeps static analysis, assumptions, output validation, estimates, and measurements separate.

- **Validation** checks tested inputs; it is not a proof for every possible input.
- **Kernel time** measures the computation, excluding allocation and output formatting.
- **End-to-end time** includes the process, initialization, output, and harness overhead.
- **Trials** run in separate processes. Raw timings and their spread are retained.
- **Target recommendations** stay `insufficient_evidence` when calibration is unavailable.

Validation and benchmarking use the examples' `praline-output-v1` JSON protocol. To benchmark your own program, provide the same output adapter; arbitrary program output is not supported. Analysis and transformation do not require that protocol.

## Development

Run the tests:

```sh
python -m pytest -q
```

| Directory | Contents |
| --- | --- |
| `praline/frontend/` | Clang AST extraction |
| `praline/analysis/` | Helper effects and loop dependency checks |
| `praline/transform/` | CPU and GPU source generation |
| `praline/execution/` | Compilation, validation, and benchmarks |
| `praline/report/` | HTML evidence reports |
| `examples/` | Runnable demo programs |
| `tests/` | Unit and integration tests |
| `submission/` | Deck, abstract, script, and recorded evidence |

The project uses Clang rather than ROSE. The [compiler contract](docs/CONTRACT.md) documents supported inputs, assumptions, and interfaces.


