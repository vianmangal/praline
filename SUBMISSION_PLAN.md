# Praline: submission materials

These are preparation instructions and draft text. They are not completed submission artifacts. Verify upload limits and exact deadlines in the participant dashboard.

## 1. Repository link

Deliver a repository judges can access and clone. Include:

- README: pitch, quick start, doctor, demo commands, screenshots, and supported environment.
- Source and tests, with dependency versions and example programs.
- Small actual evidence bundle: analysis, generated source, validation, raw timings, compiler/device metadata.
- Architecture explanation and safety assumptions, supported subset, alias handling, and Clang/ROSE choice.
- GPU verification status and reproducible Linux offload instructions.
- Links to video, deck, abstract, and evidence.

Keep temporary outputs and large videos out of Git by default. Do not select a license on behalf of the team without a preference. Test the clone URL using the same access a judge will have. Push only when the user supplies or authorizes the destination. Record the commit used for the recording so evidence is reproducible.

## 2. Demo video

Working target: 3–4 minutes, unless the form states another limit. Record the actual application and explain what happens in simple language. Large source text is more useful than a fast terminal scroll.

| Time | Visual | Message |
| --- | --- | --- |
| 0:00–0:20 | Program and loop/helper | Calls hide effects that determine parallel safety |
| 0:20–0:55 | Analyze command and report | Reads/writes and assumptions come from a real AST |
| 0:55–1:30 | Generated CPU diff and validation | Parallel source is generated and checked against serial |
| 1:30–2:00 | Real timing chart | Show measured results and environment; explain size effects |
| 2:00–2:35 | Shared-write variant | Tool rejects unsafe code with a source witness |
| 2:35–3:15 | GPU mapping/device evidence or explicit limitation | Distinguish generated GPU source from verified execution |
| 3:15–3:40 | Repository and concise wrap | State supported scope and reproducibility |

If using saved runs, label them as recorded real results. Do not fake live execution. GPU host fallback must not appear as a GPU benchmark. Ensure the submitted link is accessible without requesting permission. Keep a local MP4 backup.

## 3. Slide deck

Working target: 7 slides. Simple headings, plain language, neutral colors, readable source excerpts. The earlier preference for minimal formatting applies here too.

1. **Praline** — one sentence, team name, P05.
2. **The problem** — helper-map loop beside an unsafe helper variant; explain the missed opportunity and risk.
3. **How it works** — Clang AST → effects → dependencies → target decision → OpenMP → validation.
4. **Seeing through a call** — actual effect/witness report; alias assumptions explicitly shown.
5. **Generated code** — CPU pragma and GPU target/data mapping; label each verification state.
6. **Results** — measured runtimes, tested inputs, validation count, hardware/compiler, and limitation notes. Fill from actual evidence only.
7. **What we delivered** — supported cases, honest remaining gaps, repository/video link or QR code, next extension.

Export a portable PDF; include PPTX if the form accepts it and editing is useful. Test that links work and every page is readable. Avoid invented success counts or speedup placeholders in the final deck.

## 4. Abstract

Draft below is approximately 150 words. Revise after the build so every statement matches verified behavior; if GPU code is not implemented, remove that claim.

> Praline helps developers parallelize supported C loops that call helper functions. It uses a Clang syntax tree to identify loops, summarize what called functions read or write, and check whether iterations can run independently under explicit alias and input assumptions. Each decision includes a source-level explanation. For supported safe loops, Praline generates CPU OpenMP directives and GPU target directives with data-mapping clauses. It then compiles the generated program, compares its output with the sequential version, and records repeated runtime measurements on available hardware. A transparent cost model separates parallel safety from whether parallel execution is likely to pay off. The demonstration contrasts a safe helper-call loop with a similar loop that writes shared state and must be rejected. Praline implements a focused part of SegFault P05: finding parallelism across function calls and making execution decisions understandable. Its reports clearly distinguish generated code, tested correctness, measured performance, and unverified GPU behavior.

Add actual results only after measurement. Avoid saying whole-program C++ support, ROSE integration, formal proof, or verified GPU speedup unless those have actually been delivered.

## 5. Manifest to create at build completion

Create submission/MANIFEST.md with the following fields:

```text
Project: Praline
Track: P05
Repository URL: pending publication
Recorded commit: pending
Video file and URL: pending
Deck PDF and optional PPTX: pending
Abstract path and word count: pending
Evidence bundle: pending
CPU verification: pending
GPU status: unavailable / generated / compiled / device-verified
Submission deadline and limits checked: pending
Final link access checked: pending
```

Replace pending fields only with actual artifacts or verified facts. Local deck/video files do not imply externally published links. Publication and final form upload remain distinct actions.
