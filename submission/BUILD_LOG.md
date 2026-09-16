# Experience build log

18 September 2026. Ownership: CLI, doctor, execution/report modules, examples, integration tests, scripts, README, submission and Python packaging. Compiler-owned files have not been edited. The three plans are specifications and draft instructions, not completed-product evidence. The user's ownership boundaries override their suggested schema/work allocation.

## Toolchain and setup

- Apple Clang 21.0.0, arm64 macOS. Tiny C11 compile and Clang AST JSON probe passed.
- Initial OpenMP `-fopenmp` failed on Apple Clang. Installed the small existing Homebrew libomp bottle, version 23.1.1, rather than building LLVM.
- Real OpenMP two-thread reduction probe passed using explicit Homebrew include/link flags. Raw commands and output are in `evidence/doctor.json`.
- Mandatory GPU target probe failed to establish non-host execution. GPU offload is unavailable on this host. No GPU speedup is claimed.
- Created `.venv` with Python 3.14.5, installed pytest 8.4.2, and installed `.[test]` editable. Runtime Python dependencies are empty.

## Harness evidence

`python -m pytest tests/integration/test_execution.py -q`: six tests passed. Fixtures execute on real compilers. Tests cover all six deterministic programs across zero/boundary/regular sizes and multiple seeds, independent reference calculations, full-output mismatches hidden by a sum, corrupted generated output, raw five-trial timing collection, subprocess timeout, invalid protocol, missing compiler, compile failure, tolerance/NaN policy, CLI invocation and HTML escaping.

The hand-inserted pragma fixture in the execution test tests the harness only. It is not used in submission evidence or represented as compiler-generated code.

## Contract and report

Read the other task's `docs/CONTRACT.md`, schema version 1. The only compiler integration adapter is `praline/execution/core.py`. The CLI uses the real APIs lazily, with an optional `PRALINE_CORE_ROOT` for split worktrees. No temporary mock analysis model or fake decision is used. No safety analysis is implemented by this task.

HTML separates core status, assumptions, source witnesses, helpers, mappings, actual diff, validation, raw timings and unavailable GPU evidence. Output is escaped. Runtime evidence does not change static decisions or hashes. New generation/execution invalidates stale performance evidence. Benchmarking requires the same compilation and all measured size/seed/thread cases to have passed validation.

## Submission drafts

Created abstract, recording script, seven-slide editable PPTX and seven-page portable PDF. Slide renders have been inspected. Initial deck has no invented results; compiler-backed evidence will replace unavailable text after the core implementation is callable. The PDF is assembled from the reviewed slide renders, while PPTX remains editable.

Video recording, microphone capture, publication, participant-dashboard limits and final upload are not completed. No paid resource, publication, license choice or fabricated URL has been introduced.

## Actual core integration

The real compiler adapter classifies all six executable examples as expected: helper map safe, global/prefix/scatter unsafe, alias/library-call unknown. The core-generated CPU program passed all 30 size/seed/thread validation cases. The integration suite now passes all nine tests with `PRALINE_CORE_ROOT` pointing to the actual compiler checkout, including GPU source generation and stale-source refusal.

GPU generation correctly refused unresolved buffer extents. Explicit `--extent input=n --extent output=n` contracts enable generation, and the report records those assumptions. No device execution is claimed.

The initial recorded map measurements show CPU OpenMP overhead exceeding the serial arithmetic workload. Results will show slowdowns. Timer resolution is captured by the C adapter, and ratios at or below resolution are unavailable instead of artificial zero-speedup claims. Timing evidence is being refreshed against that final adapter.

Browser UI inspection of local report.html was blocked by the browser URL security policy. No alternate route was attempted. HTML is covered by escaping and artifact tests, but browser visual QA and actual application screenshots are incomplete.

Wheel construction passed with `python -m pip wheel --no-deps --wheel-dir runs/wheels .`. A combined source snapshot will test installation without the external-core adapter and preserve compiler source byte-for-byte with provenance hashes.

## Final evidence and clean setup

The actual core-generated CPU program passed eight supplementary ASan/UBSan cases. GPU output passed an actual host OpenMP syntax check; its status is `syntax_checked`, explicitly without GPU backend or device verification.

The combined snapshot installed in a new virtual environment and passed all 49 tests present at assembly. Added a visible hardware-gated GPU execution test afterward (GPU unavailable is a skip, never a pass) and an input-preservation test for a source named generated.c in its output directory. Final snapshot verification will include those checks.

Deck and abstract now contain actual core decisions and measured medians. The seven-slide deck and portable PDF were inspected. Draft result placeholders have been replaced. The video remains a script and manual recording checklist.

Final timing refinement: subprocess execution now uses a blocking OS wait with a separate timeout/output-limit watchdog. POSIX `Popen.wait(timeout)` polls with backoff and can inflate very short whole-process measurements. The raw evidence has been refreshed with the corrected wait. Timing scope explicitly includes harness launch/reaping overhead. The output watchdog is tested and kills the full child process group on timeout or excessive output.

Final clean installation result: **59 passed, two GPU hardware skips**, using a fresh virtual environment in runs/final-checkout with PRALINE_CORE_ROOT unset. GPU execution was skipped in both experience and core tests because this host has no verified non-host offload device. The final source archive uses this exact tested core snapshot, copied unchanged, together with final experience files. The live compiler task has made subsequent changes; those remain separately owned and require a new snapshot and verification before replacing the tested core.

Submission consistency checker passed: all local materials present, CPU validation passed, benchmarks measured, original/generated source hashes agree, all cases passed, and sanitizer evidence matches the generated source. The abstract is 150 words excluding its heading. Seven PPTX slides and seven PDF pages contain actual decisions and measurements. Recording, publication and authenticated upload remain incomplete.
