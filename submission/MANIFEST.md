# Praline submission manifest

## Coordinator integration update

Both finished worktrees have been combined in `/Users/vian/Documents/ChatGPT/segfault` using the latest compiler files. The integrated checkout passed **64 tests, with 3 skips**, and `praline demo --out runs/coordinator-demo` completed successfully without `PRALINE_CORE_ROOT`. The submission consistency checker also passed. The earlier archive and submission measurements below remain a historical tested snapshot; the archive does not yet include the latest Core changes. Final repository publication should use this integrated checkout after a commit. GPU device execution, video recording, publication, and organizer upload remain outstanding.

Project: Praline  
Track: P05  
Repository URL: https://github.com/vianmangal/praline  
Base commit: `8317b178b2259fed244d2f96f5f2c7e29a325dee`. Implementation is uncommitted. This commit alone does not reproduce the recording state. Source-snapshot provenance hashes identify the exact copied files.  
Video file and URL: **missing recording and publication**  
Deck: `submission/deck.pdf` (seven pages) and `submission/deck.pptx` (seven editable slides), local and inspected, not published  
Abstract: `submission/abstract.md`, 150 words excluding heading  
Evidence: `submission/evidence/`, actual core-backed analysis, source, diff, validation, raw timings, environment, sanitizer checks and GPU host syntax check  
CPU verification: **30 whole-output cases passed**, 300 timed executions with five trials per variant and process warmups, eight additional ASan/UBSan cases passed  
GPU status: **generated and host syntax checked, device execution unverified**. No compatible device on this Mac. No GPU performance claim.  
Submission deadline and limits checked: **not checked in participant dashboard**  
Final link access checked: **no public links supplied**  
Final form upload: **not performed**

## Reproduction and integration

The actual core API and frozen `docs/CONTRACT.md` were consumed from the separate compiler worktree. Compiler-owned files were not edited. The experience worktree uses `PRALINE_CORE_ROOT` until the two trees are integrated. The tested combined clean snapshot installed in a fresh environment without that override: **59 passed, two GPU hardware skips**. `submission/praline-source.tar.gz` and its `INTEGRATION_PROVENANCE.json` capture the final experience files and the exact tested core snapshot. The live compiler task continues to own subsequent changes. Additional compiler changes after this tested snapshot require a new assembly and test run; they are not silently included in the archive.

Measured kernel times on this simple helper map show OpenMP overhead. End-to-end ratios vary with process and scheduling overhead. See `results.md` and raw trial spread instead of interpreting a small ratio above one as a reliable speedup. No calibrated profitability model or crossover is claimed.

## Missing steps

- Integrate or unpack the final combined source snapshot and rerun the documented commands on the submission environment.
- Verify GPU execution on a compatible Linux host. Generated-kernel device instrumentation, mandatory offload, model/driver/backend/runtime metadata and actual output validation are still needed.
- Record the demo using `video-script.md`, replay it for readability/audio/duration, save a local backup, publish to an authorized destination and check access signed out.
- Publish the repository and deck to the team's authorized destinations. No license has been selected.
- Check authenticated organizer deadline, abstract length, video duration and allowed deck formats. Upload and submit the form separately.
- Browser visual QA and actual application screenshots are incomplete: the browser security policy blocked local report.html access. Artifact/escaping tests passed and deck renders were inspected. No policy bypass was attempted.

Local artifacts do not establish publication or submission. No paid resource or fabricated URL was introduced.
