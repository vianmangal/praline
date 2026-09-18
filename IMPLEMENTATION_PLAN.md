# Praline: execution plan for today

Read PRD.md first. This is a proposed 10–12 hour work budget, not a promise that complex compiler or hardware integration will finish in that time. If less time is available, preserve the main helper-map pipeline and reserve time for submission.

## 1. Immediate decisions

Use C11, Python, Clang AST JSON, source edits, OpenMP, pytest, and generated HTML. Begin with one translation unit and direct helpers. Reuse installed tools; record versions and pin dependencies after successful smoke tests. Do not spend the day building a compiler toolchain from source.

Confirm access to an existing compatible Linux GPU host immediately. Local Mac CPU work can proceed while GPU access is resolved. Hardware absence does not block CPU analysis but prevents a verified GPU claim. Do not purchase GPU time, create paid resources, or publish externally without the user's direction.

## 2. Responsibilities

Person A owns analysis semantics and generated code review. Person B owns examples, harness, report, recording, slides, and submission checks. The coding agent implements modules and tests against the shared schema. Both people inspect the safe/unsafe evidence and final claims.

If separate agents are used, give them different file ownership. Parallelize the report renderer and benchmark adapters only after model/schema contracts are fixed. Integration belongs to one coordinator.

## 3. Ordered gates

### Gate 0 — Toolchain, 0:00–0:45

Inspect repository instructions and existing changes. Scaffold CLI, packaging, and tests. Implement doctor. Verify a tiny AST dump and CPU OpenMP hello-world. Determine whether actual GPU offload exists. Record commands and results in docs/BUILD_LOG.md.

Exit: one known working Clang path and a truthful capability report. If OpenMP is missing, use an existing packaged compiler/runtime and verify flags rather than assuming Apple system gcc is GNU GCC.

### Gate 1 — Schema and fixtures, 0:45–1:30

Define schema version 1 and internal declarations/access expressions. Write helper_map, global_write, prefix_dependency, alias_unknown, scatter_write, and unknown_call examples with independent reference outputs. Freeze report JSON before other modules use it.

Exit: fixtures compile sequentially, AST identities and source ranges are understood, serialized report is stable.

### Gate 2 — Analysis, 1:30–4:00

Implement canonical loop extraction, declaration-based reads/writes, helper effect summaries, call-site parameter substitution, and supported dependency checks. Start with scalar pure helpers and unique output indexing. Explicitly enforce alias conditions and reject unsupported nodes.

Exit: positive and negative suite passes; purity alone never bypasses dependency checks; each reason cites a source span. Review safety implementation before transformation work proceeds.

### Gate 3 — CPU generation and execution, 4:00–5:30

Generate source edits, guard stale hashes, compile output, validate multiple seeds/sizes, and benchmark with comparable flags. Make `praline demo` produce a complete real run directory.

Exit: helper map works from source to report; unsafe/unknown candidates generate no parallel patch; all raw timings are retained.

### Gate 4 — GPU path and target policy, 5:30–7:30

Generate target teams/distribute/parallel-for, data extents/maps, and device helper declarations. On compatible hardware require mandatory offload and device evidence. Calibrate transfer/launch costs if possible; implement a simple recommendation with documented uncertainty.

Exit: generated GPU source and explicit verification status. If hardware works, record validation and end-to-end results for small/large sizes. If unavailable, retain honest generated-code evidence and a tested CPU submission; describe the P05 gap prominently.

### Gate 5 — Report and reproducibility, 7:30–8:30

Finish the plain HTML report, source diff, helper chain, charts, raw evidence links, error states, README setup, and supported-input guide. Test from a fresh environment or documented clean setup.

Exit: a judge can run two commands and view the result; screenshots reflect actual runs.

### Gate 6 — Submission package, 8:30–10:30

Freeze feature claims. Prepare abstract, deck, and video storyboard from measured evidence. Render and inspect slide output using the presentation skill if producing PPTX/PDF. Record a real demo or provide the exact manual recording procedure if capture is unavailable. Check audio, readability, duration, and links.

Exit: local submission files are ready; repository/video publication states are recorded. Publishing requires the actual destination and relevant authorization, not fabricated URLs.

### Gate 7 — Final checks and buffer, 10:30–12:00

Run targeted tests and end-to-end demo, verify report/deck/abstract consistency, inspect artifacts, and complete submission/MANIFEST.md. Fix only defects that affect correctness, reproduction, or the demo.

## 4. Cut order if time is short

Cut React, multi-file analysis, recursive summaries, floating point reductions, nested stencils, and complex calibration first. Keep conservative helper analysis, real CPU transformation, GPU generation with mapping, validation, recorded evidence, and four submission materials. Do not expand supported syntax by weakening safety rules.

After the midpoint, add features only when the complete helper-map path already works. Reserve at least two hours for materials. A two-example convincing demo is preferable to several broken claims.

## 5. Tests with purpose

- Unit: binding-aware effects, helper substitution, alias states, conflicting access pairs, mapping extents, source edits.
- Integration: real Clang parsing; CPU OpenMP compile/run; repeated transformation; stale-source rejection.
- Negative: globals, collisions, dependencies, unknown calls, macros, shadowed variables, unresolved pointers.
- Validation: intentional wrong generated output must fail; integer equality and optional float tolerance must work.
- GPU: compile/device execution only on a supported runner; capability skips are visible and never counted as passes.
- Packaging: CLI installation, clean demo command, schema and report generation.

Use deterministic expected outcomes and real compiler execution. Avoid tests that merely assert hand-authored example names receive canned labels.

## 6. Completion report

Record implementation coverage, test command/results, available hardware, actual benchmark observations, GPU verification status, four submission artifact locations/URLs, and any publication/upload action still required. State why remaining gaps exist. Do not call the project fully verified if the GPU path has only been generated.
