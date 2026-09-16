# Recorded CPU measurements

Actual compiler-generated helper map on arm64 macOS, Apple Clang 21 and Homebrew libomp 23.1.1. Five trials per variant after one process warmup. Each timed trial starts a new process.

| Size | Seed | Threads | Serial kernel median ms | CPU kernel median ms | Kernel speedup | End-to-end speedup |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 1 | 4 | 0.000000 | 0.270000 | unresolved at timer resolution | 0.743x |
| 1 | 1 | 4 | 0.000000 | 0.304000 | unresolved at timer resolution | 0.709x |
| 1024 | 1 | 4 | 0.001000 | 0.278000 | 0.004x | 0.705x |
| 65536 | 1 | 4 | 0.016000 | 0.295000 | 0.054x | 0.821x |
| 1048576 | 1 | 4 | 0.273000 | 0.545000 | 0.501x | 0.780x |

Validation: 30 whole-output cases passed across sizes [0, 1, 1024, 65536, 1048576], seeds [1, 7], threads [1, 2, 4]. Each case also checks an independent serial reference.

Raw timed executions: 300, each with kernel and end-to-end measurements (600 trial entries). Warmups retained separately.

Kernel timing excludes allocation, initialization, checksum and output serialization. End-to-end includes them, process startup, OpenMP runtime startup and harness launch/reaping overhead. Ratios at or below timer resolution are unavailable. Small differences can reflect timing and scheduling noise. No GPU measurement, calibrated cost model or crossover is available. See raw trials and spread in evidence/map-cpu/benchmark.json.
