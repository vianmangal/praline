"""Frozen public transformation API; no compilation/execution claims."""
from __future__ import annotations

from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path

from praline.model import PralineError
from .edits import Edit, apply_edits
from . import cpu, gpu


def transform_source(path, analysis: dict, target: str = "cpu", output_dir=None,
                     loop_ids=None) -> dict:
    if target not in {"cpu", "gpu"}:
        raise PralineError("INVALID_TARGET", f"Unsupported target {target!r}")
    if analysis.get("schema_version") != 1 or analysis.get("status") == "error":
        raise PralineError("INVALID_ANALYSIS", "A successful schema-v1 analysis is required")
    path = Path(path).resolve()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PralineError("SOURCE_ERROR", str(exc)) from exc
    if hashlib.sha256(data).hexdigest() != analysis["source"]["sha256"]:
        raise PralineError("STALE_SOURCE", "Source hash differs from the analyzed file")
    if loop_ids is None:
        selected = [l for l in analysis["loops"] if l["decision"] == "safe"]
    else:
        requested = set(loop_ids)
        selected = [l for l in analysis["loops"] if l["id"] in requested]
        if len(selected) != len(requested):
            raise PralineError("INVALID_SELECTION", "Unknown loop ID in selection")
        if any(l["decision"] != "safe" for l in selected):
            raise PralineError("UNSAFE_SELECTION", "Only safe loops can be transformed")
    if not selected:
        raise PralineError("NO_SAFE_LOOPS", "No statically safe loops were selected")
    if any(target not in l["eligible_targets"] for l in selected):
        raise PralineError("TARGET_UNSUPPORTED", "Selected loops lack the required target evidence (check generation_reasons)")
    selected.sort(key=lambda l: l["span"]["start"])
    for left, right in zip(selected, selected[1:]):
        if left["span"]["end"] > right["span"]["start"]:
            raise PralineError("OVERLAPPING_LOOPS", "Nested/overlapping candidates cannot both be transformed")
    edits = []
    for loop in selected:
        edits.extend([cpu.loop_edit(loop)] if target == "cpu" else gpu.loop_edits(loop, data))
    if target == "gpu":
        functions = {f["id"]: f for f in analysis["functions"]}
        helpers = {h for l in selected for h in l["helper_ids"]}
        for helper in sorted(helpers, key=lambda h: (functions.get(h, {}).get("span") or {}).get("start", -1)):
            if helper not in functions:
                raise PralineError("UNSUPPORTED_HELPER", "Missing helper definition")
            edits.extend(gpu.helper_edits(functions[helper]))
    # Adjacent statements/functions can share an insertion boundary. Preserve
    # end-before-start ordering while presenting one edit per byte position.
    insertions = {}
    for edit in edits:
        insertions.setdefault(edit.start, []).append(edit.replacement)
    edits = [Edit(position, position, b"".join(parts)) for position, parts in insertions.items()]
    source = apply_edits(data, edits, analysis["source"]["sha256"]).decode("utf-8")
    diff = "".join(difflib.unified_diff(data.decode("utf-8").splitlines(keepends=True),
                                     source.splitlines(keepends=True), fromfile=str(path), tofile="generated.c"))
    report = deepcopy(analysis)
    report["status"] = "generated"
    report["transformation"] = {"target": target, "loop_ids": [l["id"] for l in selected],
                                 "generated_sha256": hashlib.sha256(source.encode()).hexdigest()}
    if target == "gpu":
        report["gpu"].update(status="generated", reason="OpenMP target source generated; not compiled or device-verified",
                             device=None, mandatory_offload=None, is_initial_device=None, compile_command=None)
    if output_dir is not None:
        directory = Path(output_dir).resolve()
        destinations = [directory / n for n in ("generated.c", "patch.diff", "analysis.json")]
        if any(p.resolve() == path for p in destinations):
            raise PralineError("SOURCE_OVERWRITE", "Output paths would overwrite the input file")
        directory.mkdir(parents=True, exist_ok=True)
        report["artifacts"].update(generated="generated.c", diff="patch.diff", analysis="analysis.json")
        for destination, content in zip(destinations, [source, diff, json.dumps(report, indent=2) + "\n"]):
            destination.write_text(content, encoding="utf-8")
    return {"target": target, "source": source, "diff": diff,
            "transformed_loop_ids": [l["id"] for l in selected], "report": report}


__all__ = ["transform_source"]
