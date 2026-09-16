# Praline

Praline is a local C parallelization prototype: helper-aware compiler analysis and source generation are supplied by the compiler core, while this task provides toolchain discovery, deterministic examples, compilation, whole-output validation, repeated timings and a plain HTML evidence report. It targets SegFault P05 with a focused C11 subset and a Clang adapter. It does not integrate ROSE.

## Install and reproduce

Python 3.11 or newer and Clang are required. No third-party Python runtime dependency is needed.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
praline doctor --out runs/toolchain
praline demo --out runs/demo
```

Open `runs/demo/map-cpu/report.html` locally. The demo generates the helper map, checks every output element against sequential execution and an independent reference, records five trials after a warmup, analyzes the negative examples, and attempts GPU generation. No benchmark value is a speedup guarantee.

During separate-worktree development, set `PRALINE_CORE_ROOT` to the compiler checkout. The CLI reports missing integration explicitly. The final combined checkout must include the core-owned modules and `docs/CONTRACT.md`; see [integration notes](submission/INTEGRATION.md). The examples are repository assets, so run the demo from the repository root or supply `--examples /path/to/examples`.

On this Mac, Apple Clang 21 with Homebrew libomp 23.1.1 passed a real two-thread OpenMP probe. If needed, `brew install libomp` provides the runtime. Doctor probes `-fopenmp` first, then the explicit Homebrew include/link flags on macOS. System `gcc` may be Apple Clang. GPU offload is **unavailable** on the current host.

## Commands

```sh
praline analyze examples/helper_map.c --out runs/map
praline transform examples/helper_map.c --target cpu --out runs/map-cpu
praline validate examples/helper_map.c --generated runs/map-cpu/generated.c --out runs/map-cpu --sizes 0,1,1024,65536,1048576 --seeds 1,7 --threads 2
praline benchmark examples/helper_map.c --generated runs/map-cpu/generated.c --out runs/map-cpu --sizes 1024,65536,1048576 --seeds 1,7 --threads 1,2,4 --trials 5 --warmups 1
praline transform examples/helper_map.c --target gpu --extent input=n --extent output=n --out runs/map-gpu
praline analyze examples/global_write.c --out runs/unsafe
praline report runs/map-cpu
python -m pytest
```

`--clang PATH` selects the analysis compiler. Repeated `--clang-arg=-I/path` forwards compiler flags. `--cc PATH` selects the execution compiler. `--extent input=n` supplies explicit extents, and `--assume-disjoint input,output` supplies an explicit user alias contract. These are assumptions, not inferred facts. The default map fixture uses valid restrict parameters and disjoint allocations. Negative examples must never produce a parallel patch.

Exit codes: 0 successful command (including unsafe/unknown analysis), 1 compiler/runtime/unavailable error, 2 invalid invocation or refused transformation. Commands have configurable subprocess timeouts. Invalid protocol output, compiler errors, mismatches and missing GPU evidence are reported separately.

## Execution protocol and evidence

Validation and benchmarking accept the explicit `praline-output-v1` protocol, rather than arbitrary program stdout. Programs take `SIZE SEED MODE`, where mode is `validate`, `reference` or `benchmark`, and emit one JSON object. Validation/reference include every output element. All modes include protocol, size, seed, nonnegative kernel_seconds, checksum and auxiliary observables. The included runtime accepts up to 4,194,304 elements and unsigned 32-bit seeds. Larger validation output may hit the 32 MiB capture limit.

Integers compare exactly. For `--numeric float`, `--atol` and `--rtol` set `abs(error) <= atol + rtol * abs(reference)`. NaN mismatches fail. `--no-reference` supports external protocol adapters without the example reference mode and is recorded in evidence. Passing tests are observed equivalence on those inputs, not a formal proof.

Kernel timing excludes input allocation, initialization and output serialization equally across variants. End-to-end subprocess timing includes all those operations, process startup, checksum calculation, output, and harness launch/reaping overhead. A blocking OS wait avoids timeout-polling delays. Each timed trial starts a new process. Warmups are separate processes and do not imply persistent runtime/device caches. Raw trials, medians, max-minus-min spread, speedups, thread counts, source hashes, commands and environment are saved. GPU end-to-end timing must include transfers and synchronization.

The execution harness does not calibrate a profitability model. Static recommendations remain `insufficient_evidence` when no calibration is supplied. The report displays actual workload-specific measurements separately.

## Linux GPU recipe

Use an existing compatible Linux OpenMP offload toolchain and device. Supply backend flags through `PRALINE_OFFLOAD_FLAGS`, for example the flags required by your installed Clang NVIDIA or AMD toolchain. No device architecture or driver version is assumed.

```sh
export CC=/path/to/offload-capable/clang
export PRALINE_OFFLOAD_FLAGS='YOUR_VERIFIED_BACKEND_FLAGS'
praline doctor --out runs/gpu-doctor
praline transform examples/helper_map.c --target gpu --extent input=n --extent output=n --out runs/map-gpu
praline validate examples/helper_map.c --generated runs/map-gpu/generated.c --target gpu --out runs/map-gpu
```

Doctor sets `OMP_TARGET_OFFLOAD=MANDATORY` and checks `omp_get_num_devices()` and `omp_is_initial_device()`. Validation additionally requires evidence from the actual generated kernel (`device.initial_device: false` in its output). The current example protocol has no generated-kernel device instrumentation. **That instrumentation and a GPU host are still required before GPU validation can pass.** Compilation or host fallback alone never counts as device verification. Capture GPU model, driver, backend and runtime versions on the eventual host.

## Submission drafts

[Manifest](submission/MANIFEST.md), [abstract](submission/abstract.md), [seven-slide content](submission/deck.md), and [recording script](submission/video-script.md) record completion states. Public repository/video links, authenticated organizer limits and final form upload are not supplied. No license has been chosen on behalf of the team.

## Combined source snapshot

`python scripts/assemble_checkout.py --core-root /path/to/compiler-checkout --out runs/combined --archive submission/praline-source.tar.gz` creates a portable combined snapshot while copying compiler-owned files unchanged. It records a SHA-256 provenance manifest. Use a new output directory for each snapshot. Unpack the archive, install `.[test]`, and run the normal commands without `PRALINE_CORE_ROOT`. The source archive is a local artifact, not a published repository.

The deck can be regenerated with `scripts/build_deck.mjs` using the bundled presentation runtime (`RUNTIME_NODE_MODULES`, `RUNTIME_NODE`, `RUNTIME_PYTHON` and `RUNTIME_BIN_DIR`). Choose a new `PRALINE_DECK_OUTPUT` filename because the finalizer preserves prior output. `scripts/export_deck_pdf.py` assembles the reviewed PNG exports using bundled Pillow. CLI users do not need these artifact-creation dependencies.

Recorded submission evidence is in [results](submission/results.md) and [the actual report](submission/evidence/map-cpu/report.html). The simple helper map shows OpenMP overhead on this host. GPU source has passed only a host syntax check. The submitted recording and public links still need to be created.
