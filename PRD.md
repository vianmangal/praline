# Praline: product requirements

Status: build specification, 18 September 2026. Nothing in this document is a claim that the product already exists.

## 1. Product and submission

Praline is a local tool that turns supported sequential C programs into OpenMP programs. It looks through helper-function calls inside loops, explains the safety decision, chooses a suitable execution target, and checks the generated program against the original.

The submission track is P05, Automatic Parallelizing Compiler for GPGPU with Interprocedural Analysis. The official brief emphasizes analysis across function boundaries and profitable GPU execution. A CPU pragma generator plus an untested GPU recommendation would be an incomplete P05 implementation. Our intended submission therefore includes GPU directives and data mapping, with hardware verification when a compatible device is available.

The four submission items are a repository URL, a demo video, a slide deck, and a short abstract. All four must describe what the final implementation actually does.

The delivery horizon is today. Use implementation gates, not a month-long roadmap. Reserve the final quarter of the available time for evidence and submission materials.

## 2. Problem and user

A performance engineer sees a loop that processes independent array elements. The loop calls a helper, which may read inputs, write shared state, or access another iteration's data. A rule that rejects all calls misses opportunities; a rule that accepts all calls can generate incorrect programs.

The user needs to answer:

- Can iterations safely run at the same time under the supported assumptions?
- What does each helper read or write?
- Which access makes a loop unsafe or uncertain?
- What code will be generated, and where will the data move?
- Does it produce equivalent output on tested inputs?
- Is CPU threading or GPU execution faster for this workload?

The initial user works locally with small benchmark programs. No accounts, remote service, or hosted execution are needed.

## 3. Main product promise

Given a supported program, Praline produces an evidence report and transformed source. The report distinguishes static analysis, assumptions, runtime validation, performance prediction, and measured results. It never presents a passing test as a mathematical proof of correctness for arbitrary inputs.

The main demo compares a deliberately limited call-blind analysis with Praline's helper-aware analysis. Do not claim production compilers universally reject calls: optimization and automatic parallelization are different questions, and mature tools can analyze or inline helpers.

## 4. Priorities

| Priority | Requirement | Completion evidence |
| --- | --- | --- |
| Required | Analyze a real Clang AST | Parsed declarations, references, loops, and source spans |
| Required | Summarize helper effects | Read/write effects linked to declarations and call sites |
| Required | Conservative loop safety analysis | Safe, unsafe, and unknown fixtures with explanations |
| Required | Generate CPU OpenMP | Generated program compiles and runs |
| Required | Generate GPU target OpenMP | Mapping clauses and supported helper device availability |
| Required | Validate and benchmark | Raw trials, output comparisons, environment metadata |
| Required | Explain decisions in a local report | Source evidence, generated diff, results, limitations |
| Required | Package the four submission items | Checklist and accessible final links/files |
| Conditional | Verify execution on a real GPU | Mandatory offload, device checks, measured results |
| Optional | Floating point reductions | Defined tolerance and reduction semantics tests |
| Optional | Nested stencil loops | Safe accesses, boundaries, mapping, tests |
| Optional | Multiple source files | Actual symbol resolution across translation units |

Prefer a correct map/helper example over adding every optional feature. Do not silently relabel conditional work as completed.

## 5. Supported program contract

Initial target: C11, one translation unit, direct nonrecursive calls, canonical loops with a known nonnegative trip count, unit increment, supported scalar expressions, and one-dimensional contiguous arrays. Parse basic C++ if convenient, but transformation support is C-first and must be advertised accurately.

The simplest accepted kernel is `output[index] = helper(input[index])`, with separate input/output buffers. The tool must establish separation from known distinct allocations, valid `restrict` contracts, or an explicit user-supplied assumption. Different pointer variable names do not prove different buffers.

Loop-local variables are private only when declaration scope and all uses establish that. Scalars declared outside the loop and mutated within it require supported reduction handling or rejection. Read-only globals can be supported if their initialization and stability are known; writes to globals reject the candidate. Volatile/atomic accesses, I/O, allocation, function pointers, recursion, unknown external calls, and unsupported syntax result in unknown or unsafe decisions as appropriate.

Pure helpers alone do not establish loop independence. Analyze the actual loop's read/write relationships as well.

## 6. User workflow

1. Run `praline doctor` to discover the compiler, CPU OpenMP support, and GPU offload support.
2. Run `praline analyze examples/helper_map.c --out runs/map`.
3. Inspect the report's loop list, helper effects, source lines, and assumptions.
4. Run `praline transform examples/helper_map.c --target cpu --out runs/map-cpu`.
5. Run `praline validate examples/helper_map.c --generated runs/map-cpu/generated.c --sizes 1024,65536,1048576`.
6. Run the benchmark harness with explicit thread counts and repeated trials.
7. Generate GPU source and run GPU validation if the doctor identifies a supported device/toolchain.
8. Open the HTML report or use `praline demo` to reproduce the prepared examples.

Exact command syntax can change once, during scaffolding. Freeze it before recording and update every document to match.

## 7. Analysis requirements

### AST extraction

Use Clang's AST rather than regular expressions to infer semantics. The fast initial adapter can use `clang -Xclang -ast-dump=json -fsyntax-only`. Check the exact installed compiler's output, including byte offsets, included files, implicit casts, referenced declaration IDs, and omitted location fields. Write a small extraction smoke test before relying on the format.

Normalize nodes into a small internal model. Preserve declaration identity, types, source byte offsets, spelling versus macro locations, and access expressions. Refuse rewrites inside macros or ambiguous source ranges. Regex is acceptable for presentation or formatting, not safety decisions.

### Effect summaries

For each function, collect reads, writes, escaped pointers, global effects, unknown calls, and supported return expressions. Scalar parameters are passed by value; pointer reads/writes must be expressed relative to formal parameters. At a call site, substitute actual arguments into the helper's summary. Merge transitive effects for an acyclic call graph when implemented; otherwise clearly mark deeper unresolved calls unknown.

Expose a witness chain such as `loop -> apply -> output[index] write`. Recognize supported pure arithmetic by its actual AST. Unsupported built-ins or library functions remain unknown unless a documented allowlist has tests.

### Dependency checks

For each candidate, compare all read/write access pairs after helper substitution. Accept only supported patterns with an independence argument and resolved aliasing. Write-write collisions and cross-iteration read-after-write dependencies reject the loop. Reject `output[index % 2]`, scatter writes, and an in-place `array[index] = array[index - 1] + value`.

Offsets such as `input[index - 1]` may be safe when reading a separate input array and writing a unique output element; require valid loop bounds and verified buffer extents. Unknown access arithmetic stays unknown. Do not infer arbitrary bounds from a sample input.

Each decision includes a reason code, message, source evidence, helper chain, and assumptions. Example codes: `INDEPENDENT_MAP`, `GLOBAL_WRITE`, `CROSS_ITERATION_DEPENDENCE`, `ALIAS_UNRESOLVED`, `UNKNOWN_CALL`, `UNSUPPORTED_LOOP`, `REDUCTION_SUPPORTED`.

### Decisions

- `safe`: supported analysis establishes independence under recorded assumptions.
- `unsafe`: a supported analysis finds an explicit conflict or prohibited effect.
- `unknown`: the tool cannot establish safety.

Only safe loops are eligible for transformation. If assumptions are unresolved, show a conditional recommendation without silently generating executable parallel code.

## 8. Transformation requirements

### CPU

Insert `#pragma omp parallel for` with explicit sharing/private/reduction clauses where required. Preserve the original file and write a separate generated file. Apply edits by byte offsets in descending order. Record the source hash so stale analysis cannot rewrite a changed file. Do not transform overlapping nested candidates twice.

Compile both original and generated versions with comparable optimization flags. Existing directives are detected and reported; repeated transformation must not duplicate pragmas.

### GPU

For supported maps, generate `target teams distribute parallel for` plus array-section mappings with known extents. Use read-only input mapping, appropriate output mapping, and `tofrom` only when required. Do not map an output with `from` if untouched elements must be preserved; initialize/copy or map the full buffer correctly. Map extents must come from supported static analysis or recorded explicit configuration.

Make called helpers device-available, for example through supported `declare target` wrapping. Reject unsupported host-only helpers. Supported reductions must be correct for both backends before being advertised.

On a GPU host, use `OMP_TARGET_OFFLOAD=MANDATORY`, inspect device availability, and demonstrate execution outside the initial host device. Host fallback is not evidence of GPU execution. Apple Clang and a Mac GPU are not assumed to supply the required OpenMP GPU environment.

Record offload compile commands, compiler/runtime versions, GPU model, driver, and backend. If hardware is unavailable, classify GPU artifacts as generated, syntax-checked, or unverified as appropriate; still provide an executable recipe for a supported Linux GPU host.

## 9. Target selection and profitability

Safety and profitability are separate fields. A safe loop can still be faster sequentially.

Start with a transparent calibrated heuristic. Model CPU time, CPU threading overhead, GPU launch overhead, transfer bytes/bandwidth, and device computation. Display the calibration source and assumptions. If calibration is unavailable, report an estimate with low confidence instead of invented hardware parameters.

Recommendations are `sequential`, `cpu`, `gpu`, or `insufficient_evidence`. Where feasible include a crossover input size. Compare the selected policy against sequential execution and an offload-every-safe-loop policy on the same device. Measure end-to-end GPU time, including transfers and synchronization; kernel-only timing is supplemental.

The minimum feature extraction needs trip count, element size, buffer extents, approximate operation count, read/write bytes, and access pattern. Unsupported features must not be reported as exact values.

## 10. Validation and benchmark harness

Use deterministic inputs and multiple sizes/seeds, including boundary sizes. Provide a machine-readable output protocol or benchmark adapter so validation checks the whole result, not only a sum that could hide errors. Keep reference serial computation independent of the generated kernel.

Integer map outputs require exact equality. Floating point tolerance is explicitly configured as `abs(error) <= atol + rtol * abs(reference)`; reject NaN mismatches and report tolerances. Reduction reorderings must be described.

Perform warmups and at least five timed trials by default. Store every trial, median runtime, spread, speedup, thread count, size, seed, source hashes, commands, and environment. Exclude input allocation from kernel timing only when done equally across variants and clearly disclose it. Capture end-to-end timing separately.

Do not guarantee speedup. A slowdown is evidence for retaining sequential execution. Never replace measured values with estimates in charts. Use sanitizers as supplemental checks where supported, and set subprocess timeouts with clear error states.

## 11. Report and interface

Use a generated HTML report first. It avoids a server and lets the frontend work proceed independently. A React application is optional only after the analysis and benchmark path works.

The report has simple headings, neutral colors, source snippets, a helper call/effect view, decision reasons, assumptions, generated source diff, and a runtime comparison. No decorative purple cards are needed. Users can view full source and raw JSON. Every result is labeled: analyzed, generated, compiled, validated, measured, predicted, or unavailable.

The UI handles invalid source, unsupported constructs, missing compiler, missing OpenMP, unavailable GPU, compile failure, output mismatch, timeout, and missing calibration. Prepared examples are labeled as examples. Saved real results are labeled as recorded runs with timestamps.

## 12. Architecture and artifacts

Default stack: Python orchestration and analysis modules, Clang AST JSON adapter, OpenMP source output, pytest, and a static HTML renderer. Use a packaged Python CLI with minimal dependencies. Prefer existing toolchains to compiling LLVM or ROSE from source during the one-day build.

The organizer encourages ROSE, and the earlier full goal names ROSE as a foundation. Our deliberate one-day choice is a Clang adapter; document this deviation in the submission and do not claim ROSE integration. Keep frontend extraction behind an adapter so ROSE can be evaluated later. If the authenticated brief makes ROSE mandatory, that changes compliance and must be disclosed.

Suggested layout:

```text
praline/
  cli.py
  doctor.py
  frontend/clang_ast.py
  model.py
  analysis/{effects,loops,dependencies,profitability}.py
  transform/{cpu,gpu,edits}.py
  execution/{compile,validate,benchmark}.py
  report/{html,templates}.py
examples/
tests/{unit,integration,fixtures}/
scripts/
docs/
submission/
runs/                 # generated, excluded from normal source control
```

Store `analysis.json`, `generated.c`, `patch.diff`, `validation.json`, `benchmark.json`, and `report.html` per run. Commit a small sanitized set of actual submission evidence separately.

Schema version 1 must include run ID, timestamps, source hash/path, compiler metadata, loops, source spans, summaries, safety reasons, assumptions, target recommendations, mapping extents, generated artifacts, validation details, raw timing trials, execution-device evidence, and status/errors. Unknown values are null with reasons, never guessed defaults.

## 13. Example suite and acceptance

| Example | Expected result | Purpose |
| --- | --- | --- |
| Pure scalar helper map | Safe with resolved disjoint buffers | Main opportunity across a call |
| Helper writes global counter | Unsafe | Hidden shared effect |
| In-place prefix dependency | Unsafe | Pure helper is not enough |
| Scatter/modulo output write | Unsafe | Multiple iterations collide |
| Unresolved input/output alias | Unknown | Conservative pointer handling |
| Helper calls unknown function | Unknown | No guessed external semantics |
| Separate-buffer stencil | Safe only if supported and bounded | Optional visual example |
| Integer sum reduction | Safe only with supported reduction generation | Optional reduction example |
| Small safe workload | May stay sequential | Overhead matters |
| Large safe workload | Measured comparison across available targets | Profitability evidence |

Tests cover name shadowing, helper argument substitution, implicit casts, pointer offsets, source spans, macros, stale hashes, negative cases, actual compile/run, and validation mismatches. No transformed unsafe/unknown fixture is permitted. Run transformed positive fixtures on multiple inputs.

## 14. Submission-ready definition

- A new checkout can install and reproduce at least the helper map and unsafe-helper examples from the README.
- Static decisions are backed by source evidence and tests.
- CPU transformation compiles, validates, and has raw benchmark data.
- GPU code includes device helpers and valid data mapping; its verification status is explicit.
- The report opens locally and separates estimates from measurements.
- Limitations describe the supported C subset, alias assumptions, Clang/ROSE choice, and hardware status.
- Repository, video, deck, and abstract agree with the implementation.
- No invented performance values, unavailable URLs, or unverified feature claims appear in final materials.

## 15. Sources and remaining external details

- Official event and track listing: https://segfault.compilertech.org/ (checked 18 September 2026).
- Clang AST tooling tutorial: https://clang.llvm.org/docs/LibASTMatchersTutorial.html
- Clang OpenMP backend support: https://clang.llvm.org/docs/OpenMPSupport.html

The user supplied the four required submission items. The public page does not establish their exact upload limits, video length, abstract word limit, or submission deadline time. Verify those in the existing participant dashboard before final upload. Suggested lengths in the submission plan are working targets, not organizer rules.
