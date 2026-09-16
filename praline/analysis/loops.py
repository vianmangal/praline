"""Public report construction and supported canonical-loop analysis."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import uuid

from praline.frontend.clang_ast import parse_source, children, expression, walk
from praline.model import AnalysisConfig, PralineError, reason
from .effects import EffectAnalyzer, Summary
from .dependencies import array_extent, check_dependencies, constant, parse_extent


LIMITATIONS = [
    "C11, one translation unit, canonical unit-increment loops and direct acyclic helpers only.",
    "Safe decisions assume defined serial C execution, valid in-bounds buffers and respected recorded restrict/user contracts.",
    "No reductions, nested loops, pointer casts, indirect calls, volatile/atomic accesses, or macro-expanded kernels.",
    "GPU extents require static array bounds or explicit configuration; generated does not mean device-verified.",
    "No runtime validation, benchmarking or profitability calibration is performed by analysis.",
]


def recommendation(safe=True):
    return {"target": "insufficient_evidence" if safe else "sequential", "confidence": "low" if safe else "high",
            "reason": "Safety is separate from profitability; no calibration or measured timings" if safe else
            "Only statically safe loops can be transformed"}


def new_report(path, config):
    path = Path(path).resolve()
    try:
        data = path.read_bytes()
        text, digest = data.decode("utf-8"), hashlib.sha256(data).hexdigest()
    except (OSError, UnicodeError):
        text, digest = None, None
    return {"schema_version": 1, "run_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(), "status": "analyzed",
            "source": {"path": str(path), "sha256": digest, "text": text},
            "compiler": {"executable": config.clang, "version": None,
                         "command": [config.clang, "-std=c11", *config.clang_args, "-Xclang", "-fopenmp",
                                     "-Xclang", "-ast-dump=json", "-fsyntax-only", str(path)]},
            "loops": [], "functions": [], "assumptions": [], "recommendation": recommendation(),
            "artifacts": {"analysis": "analysis.json", "generated": None, "diff": None,
                          "validation": None, "benchmark": None, "report": None},
            "validation": {"status": "not_run", "reason": "Analysis does not execute programs", "results": None},
            "benchmark": {"status": "not_run", "reason": "No timing trials performed", "results": None},
            "gpu": {"status": "unavailable", "reason": "GPU capability and device execution have not been checked",
                    "device": None, "mandatory_offload": None, "is_initial_device": None, "compile_command": None},
            "errors": [], "limitations": list(LIMITATIONS)}


def canonical(tu, node):
    parts = node.get("inner", [])
    if len(parts) != 5 or parts[1].get("kind"):
        return None
    init, _, condition, step, body = parts
    if init.get("kind") != "DeclStmt" or len(children(init)) != 1:
        return None
    var = children(init)[0]
    if var.get("kind") != "VarDecl" or len(children(var)) != 1:
        return None
    ctype = var.get("type", {}).get("desugaredQualType", var.get("type", {}).get("qualType", ""))
    if not re.fullmatch(r"(unsigned |signed )?(int|long|long long|short)", ctype):
        return None
    lower = expression(children(var)[0])
    cond = expression(condition)
    increment = expression(step)
    if constant(lower) is None or constant(lower) < 0:
        return None
    if cond.kind != "binary" or cond.value != "<" or cond.args[0].kind != "ref" or cond.args[0].declaration_id != var["id"]:
        return None
    upper = cond.args[1]
    if upper.kind not in {"literal", "ref"}:
        return None
    if upper.kind == "ref":
        if upper.declaration_id == var["id"]:
            return None
        decl = tu.declarations.get(upper.declaration_id)
        if not decl or decl.pointer or decl.storage == "global" or "volatile" in decl.ctype or "_Atomic" in decl.ctype:
            return None
    elif constant(upper) is None or constant(upper) < 0:
        return None
    if increment.kind != "unary" or increment.value != "++" or increment.args[0].kind != "ref" or increment.args[0].declaration_id != var["id"]:
        return None
    return var, lower, upper, body


def dedup(items):
    result, keys = [], set()
    for item in items:
        key = (item["code"], item["message"], str(item.get("span")), tuple(item.get("helper_chain", [])))
        if key not in keys:
            keys.add(key)
            result.append(item)
    return result


def analyze_loop(tu, function, node, engine, config, parents):
    span = tu.span(node)
    record = {"id": f"loop-{span['start'] if span else node['id']}", "function": function["name"],
              "span": span, "source": tu.text(node), "decision": "unknown", "reasons": [], "assumptions": [],
              "iterator": None, "lower_bound": None, "upper_bound": None, "trip_count": None,
              "effects": [], "calls": [], "mappings": [], "eligible_targets": [],
              "recommendation": recommendation(False), "helper_ids": [], "shared_variables": [],
              "firstprivate_variables": [], "generation_reasons": []}
    issues = []
    if span is None or any(tu.span(n) is None for n in walk(node) if n.get("kind") and n.get("range")):
        issues.append(reason("MACRO_EXPANSION", "Loop contains a macro or ambiguous source range", span))
    if any(p.get("kind", "").startswith("OMP") for p in parents) or re.search(
            rb"(?m)^\s*#\s*pragma\s+omp\b|\b_Pragma\s*\(", tu.data):
        issues.append(reason("EXISTING_OPENMP", "Existing OpenMP/pragma regions are not rewritten", span))
    if any(p.get("kind") in {"ForStmt", "WhileStmt", "DoStmt"} for p in parents):
        issues.append(reason("UNSUPPORTED_LOOP", "Nested candidates are not transformed", span))
    shape = canonical(tu, node)
    if shape is None:
        record["reasons"] = issues + [reason("UNSUPPORTED_LOOP", "Require a declared integer iterator, nonnegative constant start, i < invariant bound, and ++i", span)]
        return record
    iterator, lower, upper, body = shape
    record.update(iterator=iterator["name"], lower_bound=lower.render(), upper_bound=upper.render(),
                  trip_count=str(max(0, constant(upper) - constant(lower))) if constant(upper) is not None else
                  f"max(0, {upper.render()} - {lower.render()})")
    out = Summary(function, [])
    engine.collect(body, out, (record["id"],))
    # Loop condition is evaluated repeatedly and must not hide shared effects.
    engine.collect(node["inner"][2], out, (record["id"],))
    locals_ = {n["id"] for n in walk(body) if n.get("kind") == "VarDecl" and tu.declarations[n["id"]].storage == "local"}
    locals_.add(iterator["id"])
    addressed = set()
    rebound = set()
    for n in walk(function):
        if n.get("kind") == "UnaryOperator" and n.get("opcode") == "&":
            addressed.update(expression(children(n)[0]).references())
        if (n.get("kind") == "BinaryOperator" and n.get("opcode") == "=" or
            n.get("kind") == "CompoundAssignOperator" or
            n.get("kind") == "UnaryOperator" and n.get("opcode") in {"++", "--"}):
            lhs = expression(children(n)[0])
            if lhs.kind == "ref":
                rebound.add(lhs.declaration_id)
    unsafe, unknown, assumptions, memories = check_dependencies(
        tu, out.effects, iterator["id"], locals_, lower, upper, config, span, addressed, rebound)
    issues.extend(out.unknown)
    issues.extend(unknown)
    # One-dimensional numeric element types only (no shallow mapping of pointers).
    for e in memories:
        d = tu.declarations[e.base.declaration_id]
        clean = re.sub(r"\b(const|restrict|volatile)\b", "", d.ctype)
        clean = " ".join(clean.split())
        if not re.fullmatch(r"(?:(?:unsigned|signed) )?(?:char|short|int|long|long long|float|double|_Bool)\s*(?:\*|\[\d+\])", clean):
            issues.append(reason("UNSUPPORTED_ACCESS", f"Unsupported buffer element type: {d.ctype}", e.span, e.chain))
    # No loop-local addresses escape; no shared writes => all external scalar
    # captures are stable for the duration of a defined serial execution.
    captured = {e.base.declaration_id for e in out.effects if e.base.declaration_id not in locals_ and
                e.base.declaration_id in tu.declarations}
    visible = {tu.declarations[x].name: tu.declarations[x] for x in captured}
    for d in tu.declarations.values():
        if d.function == function["id"] and d.storage == "parameter":
            visible[d.name] = d
    by_buffer = {}
    for e in memories:
        by_buffer.setdefault(e.base.declaration_id, []).append(e)
    for decl_id, effects in sorted(by_buffer.items(), key=lambda kv: tu.declarations[kv[0]].name):
        d = tu.declarations[decl_id]
        fixed = array_extent(d)
        configured = config.extents.get(d.name)
        extent = str(fixed) if fixed is not None else parse_extent(configured, visible) if configured is not None else None
        source = "declared array bound" if fixed is not None else "explicit user configuration" if extent else None
        direction = "tofrom" if any(e.kind == "write" for e in effects) else "to"
        # Always preserve untouched output, including conditional/partial writes.
        record["mappings"].append({"name": d.name, "declaration_id": decl_id,
                                   "direction": direction, "extent": extent, "extent_source": source})
        if configured is not None and fixed is None and extent:
            assumptions.append(f"User extent: {d.name}[0:{extent}] is a valid contiguous buffer covering all loop accesses")
        if extent is None:
            record["generation_reasons"].append(reason("EXTENT_UNKNOWN", f"GPU mapping extent for {d.name} is not established", span))
        if extent and not extent.isdecimal():
            captured.add(visible[extent].id)
    # Read/read aliasing is harmless for CPU independence but overlapping GPU
    # map sections require a separate layout proof. Restrict alone does not
    # separate two buffers that are only read.
    read_only = [m for m in record["mappings"] if m["direction"] == "to"]
    for index, left in enumerate(read_only):
        for right in read_only[index + 1:]:
            ld = tu.declarations[left["declaration_id"]]
            rd = tu.declarations[right["declaration_id"]]
            distinct_arrays = array_extent(ld) is not None and array_extent(rd) is not None
            assumed = any(set(p) == {ld.name, rd.name} for p in config.assume_disjoint)
            if not distinct_arrays and not assumed:
                record["generation_reasons"].append(reason("ALIAS_UNRESOLVED",
                    f"GPU read-only mappings {ld.name}/{rd.name} need an explicit disjointness contract", span))
            elif assumed:
                assumptions.append(f"User assumes {ld.name} and {rd.name} are disjoint buffers for GPU mapping")
    captured_decls = [tu.declarations[x] for x in captured if tu.declarations[x].storage != "global"]
    record["shared_variables"] = sorted({d.name for d in captured_decls})
    record["firstprivate_variables"] = sorted({d.name for d in captured_decls if d.id not in by_buffer})
    record["helper_ids"] = sorted(tu.functions[x]["id"] for x in out.helper_ids)
    record["effects"] = [e.to_dict(tu.declarations) for e in out.effects]
    record["calls"] = sorted(out.calls)
    record["assumptions"] = sorted(set(assumptions + [
        "The original serial program has defined behavior and every executed access is within a valid live object"
    ]))
    record["decision"] = "unsafe" if unsafe else "unknown" if issues else "safe"
    record["reasons"] = dedup(unsafe + issues) or [reason("INDEPENDENT_MAP",
        "Every output index is injective; accesses to each written buffer use the same per-iteration index; other buffers are disjoint under the recorded contracts",
        span, (record["id"],))]
    if record["decision"] == "safe":
        record["eligible_targets"] = ["cpu"] + ([] if record["generation_reasons"] else ["gpu"])
    record["recommendation"] = recommendation(record["decision"] == "safe")
    return record


def analyze_source(path, config: AnalysisConfig | None = None) -> dict:
    config = config or AnalysisConfig()
    report = new_report(path, config)
    try:
        tu = parse_source(path, config)
    except PralineError as exc:
        report.update(status="error", errors=[{"code": exc.code, "message": exc.message}])
        return report
    report["source"] = {"path": str(tu.path), "sha256": tu.sha256, "text": tu.data.decode("utf-8")}
    report["compiler"] = tu.compiler
    engine = EffectAnalyzer(tu)
    for function_id, node in tu.functions.items():
        report["functions"].append(engine.summary(function_id).to_dict(tu))
        def visit(current, parents):
            if current.get("kind") in {"ForStmt", "WhileStmt", "DoStmt"}:
                report["loops"].append(analyze_loop(tu, node, current, engine, config, parents))
            for child in children(current):
                visit(child, parents + [current])
        visit(node, [])
    report["assumptions"] = sorted({a for loop in report["loops"] for a in loop["assumptions"]})
    report["recommendation"] = recommendation(any(l["decision"] == "safe" for l in report["loops"]))
    return report
