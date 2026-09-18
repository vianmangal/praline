"""Raw repeated timing evidence. Never substitute estimates for measurements."""
from __future__ import annotations
from datetime import datetime, timezone
import statistics
from praline.execution.validate import execute


def summary(values: list[float]) -> dict:
    return dict(median_seconds=statistics.median(values), min_seconds=min(values),
                max_seconds=max(values), spread_seconds=max(values)-min(values))


def benchmark_pair(compilation: dict, validation: dict, *, sizes: list[int], seeds: list[int],
                   thread_counts: list[int], trials: int = 5, warmups: int = 1,
                   target: str = "cpu", timeout: float = 30, environment: dict | None = None) -> dict:
    if trials < 5 or warmups < 0 or not thread_counts or any(t < 1 for t in thread_counts):
        raise ValueError("Use at least five trials, nonnegative warmups and positive thread counts")
    result = dict(status="unavailable", timestamp=datetime.now(timezone.utc).isoformat(),
                  trial_count=trials, trials=[], summaries=[], commands=[],
                  source_hashes={k:v.get("source_hash") for k,v in compilation.items()},
                  warmups=warmups, measurements=[], environment=environment,
                  compilation=compilation, timing_scope={"kernel":"Program-reported elapsed kernel time, excludes allocation, initialization and JSON serialization",
                  "end_to_end":"Subprocess wall time includes harness launch/reaping overhead, startup, allocation, initialization, kernel, checksum, and JSON serialization",
                  "gpu":"Only device-verified mandatory offload qualifies as GPU evidence"})
    if validation.get("status") != "passed":
        result["reason"] = "Benchmark requires passing whole-output validation"
        return result
    if validation.get("compilation") != compilation:
        result["reason"] = "Validation belongs to a different compilation"
        return result
    cases = {(c["size"],c["seed"],c["threads"]) for c in validation["cases"] if c["status"] == "passed"}
    if any((n,s,t) not in cases for n in sizes for s in seeds for t in thread_counts):
        result["reason"] = "Validate every benchmark size, seed and thread count first"
        return result
    if any(compilation[v]["status"] != "ok" for v in ("sequential","generated")):
        result["reason"] = "Compilation failed"
        return result
    result["status"] = "measured"
    for size in sizes:
        for seed in seeds:
            for threads in thread_counts:
                measurement = dict(size=size, seed=seed, threads=threads, status="measured", variants={})
                for variant in ("sequential","generated"):
                    samples, warmup_results = [], []
                    for trial in range(-warmups, trials):
                        outcome = execute(compilation[variant]["output"], size, seed, mode="benchmark",
                                          threads=threads if variant == "generated" else 1,
                                          target=target if variant == "generated" else "sequential", timeout=timeout)
                        device_ok = target != "gpu" or variant == "sequential" or (outcome.get("data") or {}).get("device",{}).get("initial_device") is False
                        item = {"trial":trial, "status":outcome["status"] if device_ok else "device_unverified",
                                "process":outcome["process"], "kernel_seconds":(outcome.get("data") or {}).get("kernel_seconds"),
                                "end_to_end_seconds":outcome["process"]["elapsed_seconds"],
                                "checksum":(outcome.get("data") or {}).get("checksum"),
                                "timer_resolution_seconds":(outcome.get("data") or {}).get("timer_resolution_seconds"),
                                "device":(outcome.get("data") or {}).get("device")}
                        (warmup_results if trial < 0 else samples).append(item)
                        if item["status"] != "ok":
                            measurement["status"] = result["status"] = "failed"
                            break
                    entry = dict(samples=samples, warmups=warmup_results, status="measured")
                    if len(samples) == trials and all(s["status"] == "ok" for s in samples) and measurement["status"] == "measured":
                        entry["kernel"] = summary([s["kernel_seconds"] for s in samples])
                        entry["end_to_end"] = summary([s["end_to_end_seconds"] for s in samples])
                    else:
                        entry["status"] = "failed"
                    measurement["variants"][variant] = entry
                variants = measurement["variants"]
                if measurement["status"] == "measured":
                    checksums = {s["checksum"] for v in variants.values() for s in v["samples"]}
                    if len(checksums) != 1 or None in checksums:
                        measurement["status"] = result["status"] = "failed"
                        measurement["reason"] = "Benchmark outputs/checksums changed across trials"
                    else:
                        for scope in ("kernel", "end_to_end"):
                            denominator = variants["generated"][scope]["median_seconds"]
                            numerator = variants["sequential"][scope]["median_seconds"]
                            resolution = max((s.get("timer_resolution_seconds") or 0) for v in variants.values() for s in v["samples"]) if scope == "kernel" else 0
                            resolved = numerator > resolution and denominator > resolution
                            measurement[scope+"_speedup"] = numerator/denominator if resolved else None
                            measurement[scope+"_speedup_reason"] = None if resolved else "Median timing is at or below reported timer resolution; no reliable ratio"
                        measurement["observed_end_to_end_winner"] = "sequential" if variants["sequential"]["end_to_end"]["median_seconds"] < variants["generated"]["end_to_end"]["median_seconds"] else target
                result["measurements"].append(measurement)
                for variant, entry in measurement["variants"].items():
                    for sample in entry["samples"]:
                        for scope in ("kernel", "end_to_end"):
                            result["trials"].append(dict(variant=variant,size=size,seed=seed,threads=threads if variant == "generated" else 1,
                                seconds=sample[scope+"_seconds"],timing_scope=scope,trial=sample["trial"],status=sample["status"]))
                        result["commands"].append(sample["process"]["command"])
                result["summaries"].append({k:v for k,v in measurement.items() if k != "variants"} | {
                    "variants":{k:{scope:v.get(scope) for scope in ("kernel","end_to_end")} for k,v in measurement["variants"].items()}})
    return result
