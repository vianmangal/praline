"""GPU map directives. Emitting source is not evidence of hardware offload."""
from praline.model import PralineError
from .edits import Edit, statement_end


def loop_edits(loop, data):
    clauses = []
    guards = []
    for mapping in loop["mappings"]:
        if mapping["extent"] is None:
            raise PralineError("EXTENT_UNKNOWN", f"No GPU extent for {mapping['name']}")
        clauses.append(f"map({mapping['direction']}: {mapping['name']}[0:{mapping['extent']}])")
        if not mapping["extent"].isdecimal():
            guards.append(f"({mapping['extent']}) > 0")
    if loop["firstprivate_variables"]:
        clauses.append(f"firstprivate({', '.join(loop['firstprivate_variables'])})")
    directive = "#pragma omp target teams distribute parallel for " + " ".join(clauses)
    # A scope preserves unbraced if/else structure and avoids nonpositive mappings.
    guard = " && ".join(sorted(set(guards))) or "1"
    prefix = f"{{\nif ({guard}) {{\n{directive}\n"
    suffix = "\n}\n}"
    start = loop["span"]["start"]
    end = statement_end(data, loop["span"])
    return [Edit(start, start, prefix.encode()), Edit(end, end, suffix.encode())]


def helper_edits(function):
    span = function["span"]
    if span is None or function["unknown_reasons"]:
        raise PralineError("UNSUPPORTED_HELPER", f"Cannot make {function['name']} device-available")
    return [Edit(span["start"], span["start"], b"\n#pragma omp declare target\n"),
            Edit(span["end"], span["end"], b"\n#pragma omp end declare target\n")]
