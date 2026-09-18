# Seven-slide deck content

## 1. Praline

Explain and test helper-aware C loop parallelization. SegFault P05. Local C11, Clang and OpenMP prototype. Team name was not supplied.

## 2. The problem

`output[i] = apply(input[i]);` can contain independent arithmetic or a hidden shared write. The decision requires helper effects and loop dependencies.

## 3. How it works

Clang syntax tree and declaration identities, helper effects, dependency checks, explicit alias and bounds assumptions, separate OpenMP source, whole-output validation and repeated measurements. The interface is schema version 1 in docs/CONTRACT.md. No calibrated profitability model is implemented.

## 4. Seeing through a call

Actual helper map: safe, INDEPENDENT_MAP. Actual shared-write helper: unsafe, GLOBAL_WRITE with witness kernel loop / apply / counter write. Restrict contracts and separate allocations are explicit. The full effects, source spans and messages appear in evidence/*/analysis.json.

## 5. Generated code

CPU source generated, compiled and output-validated. Actual pragma: `#pragma omp parallel for default(none) shared(input, n, output)`.

GPU source generated and host syntax checked, device unverified. Actual mappings: `map(to: input[0:n]) map(tofrom: output[0:n])`. Helper apply is wrapped in declare target. No GPU speedup claim.

## 6. Results

- n=1024, seed 1, four threads: serial 0.0010 ms, CPU 0.2780 ms kernel median.
- n=65536, seed 1, four threads: serial 0.0160 ms, CPU 0.2950 ms kernel median.
- n=1048576, seed 1, four threads: serial 0.2730 ms, CPU 0.5450 ms kernel median.

Thirty whole-output cases passed. Five timed trials after one process warmup per variant. Apple Clang 21, arm64 Mac, libomp 23.1.1. Kernel excludes allocation, initialization and output. Whole-process includes those costs and harness launch/reaping overhead. See results.md for actual end-to-end ratios and benchmark.json for every trial and spread. This workload shows OpenMP overhead.

## 7. Delivery and gaps

CLI, deterministic examples, execution harness and plain HTML report. Focused C11 subset and explicit assumptions. Clang rather than ROSE. GPU hardware verification, recording, publication and authenticated submission checks remain incomplete. No public URL was supplied. See MANIFEST.md.
