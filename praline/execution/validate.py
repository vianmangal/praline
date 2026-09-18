"""Whole-output validation for the explicit Praline example JSON protocol."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from praline.execution.process import run

PROTOCOL = "praline-output-v1"


def execute(binary: str | Path, size: int, seed: int, *, mode: str = "validate",
            threads: int = 1, target: str = "cpu", timeout: float = 30) -> dict:
    env = {"OMP_NUM_THREADS":str(threads), "OMP_DYNAMIC":"FALSE"}
    if target == "gpu":
        env["OMP_TARGET_OFFLOAD"] = "MANDATORY"
    process = run([str(Path(binary).resolve()), str(size), str(seed), mode], env=env, timeout=timeout)
    if process["status"] != "ok":
        return {"status":process["status"], "process":process, "data":None}
    try:
        data = json.loads(process["stdout"])
        if not isinstance(data, dict) or data.get("protocol") != PROTOCOL:
            raise ValueError("Expected praline-output-v1 JSON protocol")
        if data.get("size") != size or data.get("seed") != seed:
            raise ValueError("Program echoed a different size or seed")
        if mode in ("validate", "reference"):
            outputs = data.get("outputs")
            if not isinstance(outputs, list) or len(outputs) != size:
                raise ValueError("Validation requires every output element")
            if any(type(x) not in (int, float) for x in outputs):
                raise ValueError("Outputs must be numeric")
        timing = data.get("kernel_seconds")
        if type(timing) not in (int, float) or not math.isfinite(timing) or timing < 0:
            raise ValueError("kernel_seconds must be finite and nonnegative")
    except (ValueError, TypeError) as exc:
        return {"status":"protocol_error", "reason":str(exc), "process":process, "data":None}
    return {"status":"ok", "data":data, "process":process}


def compare(reference: list, actual: list, *, atol: float = 0, rtol: float = 0,
            numeric: str = "integer") -> dict:
    if numeric not in ("integer", "float") or not all(math.isfinite(v) and v >= 0 for v in (atol, rtol)):
        raise ValueError("Invalid comparison mode or tolerance")
    if len(reference) != len(actual):
        return {"status":"mismatch", "reason":"Output lengths differ", "mismatches":None}
    mismatches, samples, max_error = 0, [], 0.0
    for index, (expected, observed) in enumerate(zip(reference, actual)):
        if numeric == "integer":
            equal = type(expected) is int and type(observed) is int and expected == observed
            error = abs(expected-observed)
        else:
            # NaN never compares equal, including NaN against NaN. Equal signed
            # infinities compare equal; opposite infinities do not.
            equal = (not math.isnan(expected) and not math.isnan(observed) and
                     (expected == observed or (math.isfinite(expected) and math.isfinite(observed)
                      and abs(observed-expected) <= atol + rtol*abs(expected))))
            error = abs(expected-observed) if math.isfinite(expected) and math.isfinite(observed) else None
        if error is not None:
            max_error = max(max_error, error)
        if not equal:
            mismatches += 1
            if len(samples) < 10:
                samples.append({"index":index,"reference":expected if math.isfinite(expected) else str(expected),
                                "actual":observed if math.isfinite(observed) else str(observed)})
    return {"status":"passed" if not mismatches else "mismatch", "elements":len(reference),
            "mismatches":mismatches, "samples":samples, "max_absolute_error":max_error,
            "numeric":numeric, "atol":atol, "rtol":rtol}


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps({"outputs":data["outputs"], "observables":data.get("observables")},
                                    sort_keys=True).encode()).hexdigest()


def validate_pair(compilation: dict, *, sizes: list[int], seeds: list[int], threads: int = 2,
                  target: str = "cpu", timeout: float = 30, numeric: str = "integer",
                  atol: float = 0, rtol: float = 0, independent_reference: bool = True) -> dict:
    evidence = dict(timestamp=datetime.now(timezone.utc).isoformat(), status="unavailable", cases=[], sizes=sizes, seeds=seeds, threads=threads,
                    numeric=numeric, atol=atol, rtol=rtol, compilation=compilation,
                    independent_reference=independent_reference,
                    limitation="Tested inputs establish observed equivalence, not a proof for arbitrary inputs")
    if any(compilation[v]["status"] != "ok" for v in ("sequential","generated")):
        evidence["reason"] = "Both programs must compile before validation"
        return evidence
    if not sizes or not seeds or any(n < 0 for n in sizes):
        raise ValueError("At least one nonnegative size and seed is required")
    for size in sizes:
        for seed in seeds:
            serial = execute(compilation["sequential"]["output"], size, seed, timeout=timeout, target="sequential")
            generated = execute(compilation["generated"]["output"], size, seed, threads=threads, target=target, timeout=timeout)
            reference = execute(compilation["sequential"]["output"], size, seed, mode="reference", target="sequential", timeout=timeout) if independent_reference else serial
            case = dict(size=size, seed=seed, threads=threads, status="failed", executions={})
            for name, outcome in (("sequential",serial),("generated",generated),("reference",reference)):
                case["executions"][name] = {"status":outcome["status"],
                    "process":{k:v for k,v in outcome["process"].items() if k != "stdout"},
                    "output_hash":_digest(outcome["data"]) if outcome["data"] else None,
                    "reason":outcome.get("reason")}
            if all(v["status"] == "ok" for v in (serial,generated,reference)):
                case["comparison"] = compare(serial["data"]["outputs"], generated["data"]["outputs"], numeric=numeric, atol=atol, rtol=rtol)
                case["reference_comparison"] = compare(reference["data"]["outputs"], serial["data"]["outputs"], numeric=numeric, atol=atol, rtol=rtol)
                observables_ok = serial["data"].get("observables") == generated["data"].get("observables") == reference["data"].get("observables")
                case["observables_equal"] = observables_ok
                device_ok = target != "gpu" or generated["data"].get("device",{}).get("initial_device") is False
                case["device_verified"] = generated["data"].get("device") if target == "gpu" else None
                if case["comparison"]["status"] == case["reference_comparison"]["status"] == "passed" and observables_ok and device_ok:
                    case["status"] = "passed"
                else:
                    case["status"] = "mismatch" if device_ok else "device_unverified"
            case["passed"] = case["status"] == "passed"
            case["commands"] = {name:value["process"]["command"] for name,value in case["executions"].items()}
            case["returncodes"] = {name:value["process"]["returncode"] for name,value in case["executions"].items()}
            case["source_hashes"] = {name:compilation[name]["source_hash"] for name in ("sequential","generated")}
            case["stdout_omitted_reason"] = "Full arrays compared in memory. Content hashes retained rather than repeating large vectors. Stderr retained in executions."
            evidence["cases"].append(case)
    evidence["status"] = "passed" if all(c["status"] == "passed" for c in evidence["cases"]) else "failed"
    return evidence
