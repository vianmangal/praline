"""Conservative unit-affine independence and explicit alias proofs."""
from __future__ import annotations

import ast
import re

from praline.model import reason


def constant(expr):
    if expr.kind == "literal":
        try:
            return int(expr.value)
        except ValueError:
            return None
    if expr.kind == "unary" and expr.value in {"+", "-"}:
        value = constant(expr.args[0])
        return None if value is None else value if expr.value == "+" else -value
    if expr.kind == "binary" and expr.value in {"+", "-", "*"}:
        a, b = (constant(x) for x in expr.args)
        if a is not None and b is not None:
            return a + b if expr.value == "+" else a - b if expr.value == "-" else a * b
    return None


def affine(expr, iterator):
    """Only exact integer arithmetic i + c. Casts and non-unit maps stay unknown."""
    value = constant(expr)
    if value is not None:
        return 0, value
    if expr.kind == "ref" and expr.declaration_id == iterator:
        return 1, 0
    if expr.kind == "binary" and expr.value in {"+", "-"}:
        left, right = (affine(a, iterator) for a in expr.args)
        if left is not None and right is not None:
            sign = 1 if expr.value == "+" else -1
            return left[0] + sign * right[0], left[1] + sign * right[1]
    if expr.kind == "unary" and expr.value in {"+", "-"}:
        inner = affine(expr.args[0], iterator)
        if inner:
            return inner if expr.value == "+" else (-inner[0], -inner[1])
    return None


def array_extent(decl):
    # The type string is supplied by Clang; this is not source parsing.
    match = re.fullmatch(r"[^\[\]*]+\[([0-9]+)\]", decl.ctype)
    return int(match.group(1)) if match else None


def parse_extent(text, visible):
    """Explicit configuration is restricted to integer literals or visible scalars.

    Do not interpolate arbitrary user C into generated pragma expressions.
    """
    text = str(text).strip()
    try:
        tree = ast.parse(text, mode="eval").body
    except (ValueError, SyntaxError):
        return None
    if isinstance(tree, ast.Constant) and type(tree.value) is int and 0 < tree.value <= 2**63 - 1:
        return str(tree.value)
    if isinstance(tree, ast.Name) and tree.id in visible:
        d = visible[tree.id]
        integer_type = re.sub(r"\bconst\b", "", d.ctype).strip()
        if (not d.pointer and d.storage != "global" and
            re.fullmatch(r"(unsigned |signed )?(char|short|int|long|long long|_Bool)", integer_type)):
            return tree.id
    return None


def check_dependencies(tu, effects, iterator, locals_, lower, upper, config, span, addressed=(), rebound=()):
    unsafe, unknown, assumptions = [], [], []
    memories = []
    scalar_reads = set()
    for effect in effects:
        decl = tu.declarations.get(effect.base.declaration_id)
        if decl is None:
            unknown.append(reason("UNSUPPORTED_ACCESS", "Access has no known declaration", effect.span, effect.chain))
            continue
        if decl.storage == "global":
            issue = reason("GLOBAL_WRITE" if effect.kind == "write" else "UNSUPPORTED_ACCESS",
                           f"Helper/loop {'writes' if effect.kind == 'write' else 'reads'} shared global {decl.name}",
                           effect.span, effect.chain)
            (unsafe if effect.kind == "write" else unknown).append(issue)
        if effect.kind == "escape":
            unknown.append(reason("UNSUPPORTED_ACCESS", "Pointer escape prevents independence analysis", effect.span, effect.chain))
        if effect.index is None:
            if effect.kind == "write" and decl.id not in locals_:
                unsafe.append(reason("SHARED_WRITE", f"Shared scalar {decl.name} is modified by iterations", effect.span, effect.chain))
            if effect.kind == "write" and decl.id == iterator:
                unknown.append(reason("UNSUPPORTED_LOOP", "Loop body modifies its induction variable", effect.span, effect.chain))
            if effect.kind == "read" and not decl.pointer and decl.id not in locals_:
                scalar_reads.add(decl.id)
            continue
        if decl.id in locals_:
            unknown.append(reason("UNSUPPORTED_ACCESS", "Local buffer accesses are outside the supported map subset", effect.span, effect.chain))
            continue
        memories.append(effect)
    # Reading an addressed local scalar can alias an otherwise unique pointer store.
    if scalar_reads.intersection(addressed) and any(e.kind == "write" for e in memories):
        unknown.append(reason("ALIAS_UNRESOLVED", "An address-taken shared scalar may alias a written buffer", span))
    writes = [e for e in memories if e.kind == "write"]
    if not writes:
        unknown.append(reason("UNSUPPORTED_LOOP", "No supported array output in this loop", span))
    nlower, nupper = constant(lower), constant(upper)
    for effect in memories:
        mapping = affine(effect.index, iterator)
        decl = tu.declarations[effect.base.declaration_id]
        if effect.kind == "write":
            if mapping and mapping[0] == 0:
                unsafe.append(reason("WRITE_COLLISION", f"Iterations write the same {decl.name} element", effect.span, effect.chain))
            elif effect.index.kind == "binary" and effect.index.value == "%":
                unsafe.append(reason("WRITE_COLLISION", f"Modulo/scatter output {decl.name} is prohibited", effect.span, effect.chain))
            elif mapping is None or mapping[0] != 1:
                unknown.append(reason("UNSUPPORTED_ACCESS", f"Cannot prove injective output index {effect.index.render()}", effect.span, effect.chain))
        if mapping is None or mapping[0] not in {0, 1}:
            unknown.append(reason("UNSUPPORTED_ACCESS", f"Unsupported index {effect.index.render()}", effect.span, effect.chain))
            continue
        # Offset accesses need explicit/static extents and numeric bounds. Straight
        # maps rely on the serial program's defined in-bounds execution precondition.
        extent = array_extent(decl)
        cfg = str(config.extents.get(decl.name, ""))
        if extent is None and cfg.isdecimal():
            extent = int(cfg)
        if mapping[1] != 0 or mapping[0] == 0:
            if extent is None or nlower is None or nupper is None:
                unknown.append(reason("EXTENT_UNKNOWN", f"Bounds for offset access {decl.name}[{effect.index.render()}] are unproved", effect.span, effect.chain))
            elif mapping[0] * nlower + mapping[1] < 0 or (
                nupper > nlower and mapping[0] * (nupper - 1) + mapping[1] >= extent):
                unknown.append(reason("UNSUPPORTED_ACCESS", f"Access exceeds established bounds of {decl.name}", effect.span, effect.chain))
        elif extent is not None and nupper is not None and nupper > extent:
            unknown.append(reason("UNSUPPORTED_ACCESS", f"Loop exceeds extent of {decl.name}", effect.span, effect.chain))
    buffers = {e.base.declaration_id: tu.declarations[e.base.declaration_id] for e in memories}
    for i, left in enumerate(memories):
        for right in memories[i:]:
            if left.kind != "write" and right.kind != "write":
                continue
            ldecl, rdecl = buffers[left.base.declaration_id], buffers[right.base.declaration_id]
            if ldecl.id != rdecl.id:
                if array_extent(ldecl) is not None and array_extent(rdecl) is not None:
                    assumptions.append(f"Distinct declared array objects {ldecl.name} and {rdecl.name} do not overlap")
                elif (ldecl.storage == rdecl.storage == "parameter" and
                      ldecl.id not in rebound and rdecl.id not in rebound and
                      ldecl.id not in addressed and rdecl.id not in addressed and
                      ("restrict" in ldecl.ctype or "restrict" in rdecl.ctype)):
                    assumptions.append(f"The C restrict contract for {ldecl.name}/{rdecl.name} is respected by callers")
                elif any(set(pair) == {ldecl.name, rdecl.name} for pair in config.assume_disjoint):
                    assumptions.append(f"User assumes {ldecl.name} and {rdecl.name} are disjoint buffers")
                else:
                    unknown.append(reason("ALIAS_UNRESOLVED", f"{ldecl.name} and {rdecl.name} may overlap; different names do not prove separation", left.span, left.chain))
                continue
            a, b = affine(left.index, iterator), affine(right.index, iterator)
            if a is not None and b is not None and a != b:
                unsafe.append(reason("CROSS_ITERATION_DEPENDENCE",
                    f"{ldecl.name}[{left.index.render()}] and {rdecl.name}[{right.index.render()}] can overlap across iterations",
                    left.span, left.chain))
    return unsafe, unknown, sorted(set(assumptions)), memories
