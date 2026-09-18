# Demo recording script

Working duration: 3 minutes 40 seconds. This is a recording-ready script, not a completed video. Organizer limits have not been checked in an authenticated dashboard.

Before recording, integrate the actual compiler core, run the tests and `praline demo --out runs/demo`, and inspect the HTML reports. Use only those actual recorded runs. Run `git rev-parse HEAD` and `git status --short`; if changes are uncommitted, record that fact and preserve the exact evidence files. Enlarge the terminal and browser text. Hide unrelated windows and notifications.

| Time | Visual and action | Narration |
| --- | --- | --- |
| 0:00–0:20 | Open examples/helper_map.c with loop and apply visible | “This C loop calls a helper for every element. We need to understand the helper's effects before generating parallel code.” |
| 0:20–0:55 | Run `praline analyze examples/helper_map.c --out runs/video-analysis`. Open report.html. Show decision, effects and assumptions | “Praline uses the actual Clang syntax tree. This report explains the loop decision and records the restrict and input-bound assumptions.” |
| 0:55–1:30 | Run `praline transform examples/helper_map.c --target cpu --out runs/video-cpu`, then `praline validate examples/helper_map.c --generated runs/video-cpu/generated.c --out runs/video-cpu --sizes 0,1,1024,65536,1048576 --seeds 1,7`. Show patch and validation | “The generated file preserves the original. The harness compares every output element with sequential execution, then checks the serial result against an independent reference calculation.” |
| 1:30–2:00 | Open runs/demo/map-cpu/report.html at measured runtime table | “These are recorded real measurements, with five trials after warmup. Kernel timing and whole-process timing answer different questions. Read the actual values on screen, including any slowdowns.” |
| 2:00–2:35 | Run `praline analyze examples/global_write.c --out runs/video-unsafe`. Show helper write and refusal with `praline transform examples/global_write.c --target cpu --out runs/video-unsafe` | “This helper increments shared state. The report cites that effect, and transformation refuses this unsafe loop.” |
| 2:35–3:15 | Show generated GPU patch and doctor.json | “GPU directives and mappings are generation evidence. This Mac has no verified OpenMP offload device. We make no claim of GPU speedup. Device verification needs mandatory offload and evidence from the generated kernel.” |
| 3:15–3:40 | Open README and MANIFEST | “This prototype supports a conservative C11 subset. The repository records the exact commands, raw trials, limitations and steps still needed for submission.” |

Recording procedure on macOS: press Shift-Command-5, choose Record Selected Portion, select the editor/terminal/browser area, choose an available microphone in Options, and begin. Run the sequence above at a readable pace. Stop via the menu-bar recording control. Save the original local recording, export an MP4 if the submission form requires it, and replay it in full to check audio, text, duration and content. Screen recording/microphone permissions and human narration have not been exercised by this build task.

After recording: replace the manifest's missing video field with the actual path and duration. Publish only to the team's authorized destination, test the link signed out, and add the verified URL. Do not describe a local file as a published video. Final form submission and deadline/limit verification remain manual steps.
