"""Declaration-bound effects with transitive, call-site argument substitution."""
from __future__ import annotations

from dataclasses import dataclass, field

from praline.frontend.clang_ast import children, expression, unwrap, walk
from praline.model import Effect, Expr, add, literal, reason


def pointer_parts(expr):
    """Resolve a supported pointer expression to (declaration, element offset)."""
    if expr.kind == "ref" and ("*" in expr.ctype or "[" in expr.ctype):
        return expr, literal(0)
    if expr.kind == "binary" and expr.value in {"+", "-"}:
        base = pointer_parts(expr.args[0])
        offset = expr.args[1]
        if base and not ("*" in offset.ctype or "[" in offset.ctype):
            if expr.value == "-":
                offset = Expr("unary", "-", (offset,))
            return base[0], add(base[1], offset)
        if expr.value == "+":
            base = pointer_parts(expr.args[1])
            if base and not ("*" in expr.args[0].ctype or "[" in expr.args[0].ctype):
                return base[0], add(base[1], expr.args[0])
    if expr.kind == "unary" and expr.value == "&":
        target = expr.args[0]
        if target.kind == "index":
            base = pointer_parts(target.args[0])
            if base:
                return base[0], add(base[1], target.args[1])
    return None


@dataclass
class Summary:
    node: dict
    parameters: list[dict]
    effects: list[Effect] = field(default_factory=list)
    unknown: list[dict] = field(default_factory=list)
    calls: set[str] = field(default_factory=set)
    helper_ids: set[str] = field(default_factory=set)
    return_expression: str | None = None

    def to_dict(self, tu):
        observable = [e for e in self.effects if not (
            (d := tu.declarations.get(e.base.declaration_id)) and d.storage == "local")]
        pure = not self.unknown and not any(
            e.kind in {"write", "escape"} or
            tu.declarations.get(e.base.declaration_id) and
            tu.declarations[e.base.declaration_id].storage == "global"
            for e in observable)
        return {"id": self.node["id"], "name": self.node["name"],
                "span": tu.span(self.node),
                "parameters": [{"id": p["id"], "name": p.get("name", ""),
                                "type": p["type"]["qualType"]} for p in self.parameters],
                "effects": [e.to_dict(tu.declarations) for e in self.effects],
                "calls": sorted(self.calls), "unknown_reasons": self.unknown,
                "pure": pure, "return_expression": self.return_expression,
                "return_expression_reason": None if self.return_expression is not None else
                    "Function has no single supported return expression"}


class EffectAnalyzer:
    def __init__(self, tu):
        self.tu = tu
        self.cache = {}
        self.active = set()

    def summary(self, function_id):
        function_id = self.tu.aliases.get(function_id, function_id)
        if function_id in self.cache:
            return self.cache[function_id]
        node = self.tu.functions[function_id]
        params = [n for n in children(node) if n.get("kind") == "ParmVarDecl"]
        out = Summary(node, params)
        if function_id in self.active:
            out.unknown.append(reason("RECURSION", "Recursive helper effects are unsupported",
                                      self.tu.span(node), (node["name"],)))
            return out
        self.active.add(function_id)
        body = next(n for n in children(node) if n.get("kind") == "CompoundStmt")
        self.collect(body, out, (node["name"],), allow_return=True)
        if any("expansionLoc" in loc or "spellingLoc" in loc
               for n in walk(body) for loc in n.get("range", {}).values()):
            out.unknown.append(reason("MACRO_EXPANSION", "Helper contains macro-expanded source",
                                      self.tu.span(node), (node["name"],)))
        for p in params:
            if any(e.kind == "write" and e.index is None and e.base.declaration_id == p["id"] for e in out.effects):
                out.unknown.append(reason("UNSUPPORTED_SYNTAX", "Modified by-value parameters cannot be substituted",
                                          self.tu.span(p), (node["name"],)))
        # Helper-private locals never escape into the caller's shared effects.
        # Their use as an index remains symbolic and fails dependency checking.
        out.effects = [e for e in out.effects if not (
            (d := self.tu.declarations.get(e.base.declaration_id)) and d.storage == "local")]
        returns = [n for n in walk(body) if n.get("kind") == "ReturnStmt"]
        if len(returns) == 1 and children(returns[0]):
            expr = expression(children(returns[0])[0])
            if expr.kind != "unknown":
                out.return_expression = expr.render()
        self.active.remove(function_id)
        self.cache[function_id] = out
        return out

    def collect(self, node, out, chain=(), allow_return=False):
        kind = node.get("kind")
        args = children(node)
        span = self.tu.span(node)

        def unknown(code, message):
            out.unknown.append(reason(code, message, span, chain))

        if not kind:
            return
        if any("expansionLoc" in loc or "spellingLoc" in loc
               for loc in node.get("range", {}).values()):
            unknown("MACRO_EXPANSION", "Macro-expanded semantics/ranges are not supported")
        typ = node.get("type", {}).get("qualType", "")
        if "volatile" in typ or "_Atomic" in typ or kind == "AtomicExpr":
            unknown("VOLATILE_OR_ATOMIC", "Volatile and atomic accesses require ordering analysis")
        if kind in {"CompoundStmt", "DeclStmt", "ParenExpr", "ConstantExpr"}:
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind in {"ImplicitCastExpr", "CStyleCastExpr"}:
            if kind == "CStyleCastExpr" and ("*" in typ or any(
                "*" in c.get("type", {}).get("qualType", "") for c in args)):
                unknown("UNSUPPORTED_ACCESS", "Pointer casts/address-derived values are not analyzed")
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind == "VarDecl":
            d = self.tu.declarations[node["id"]]
            if d.storage == "global":
                unknown("UNSUPPORTED_SYNTAX", "Static/thread-local declarations in a region are unsupported")
            if d.pointer:
                unknown("UNSUPPORTED_ACCESS", "Region-local pointer/array declarations are unsupported")
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind == "DeclRefExpr":
            ref = expression(node)
            if node["referencedDecl"].get("kind") != "FunctionDecl":
                out.effects.append(Effect("read", ref, None, span, chain))
        elif kind in {"IntegerLiteral", "FloatingLiteral", "CharacterLiteral", "NullStmt"}:
            pass
        elif kind == "ArraySubscriptExpr":
            self.access(node, "read", out, chain)
        elif kind == "BinaryOperator" and node.get("opcode") == "=":
            self.access(args[0], "write", out, chain)
            self.collect(args[1], out, chain, allow_return)
            if "*" in args[1].get("type", {}).get("qualType", ""):
                self.escape(args[1], out, chain)
        elif kind == "CompoundAssignOperator":
            self.access(args[0], "read", out, chain)
            self.access(args[0], "write", out, chain)
            self.collect(args[1], out, chain, allow_return)
        elif kind == "UnaryOperator" and node.get("opcode") in {"++", "--"}:
            self.access(args[0], "read", out, chain)
            self.access(args[0], "write", out, chain)
        elif kind == "UnaryOperator" and node.get("opcode") == "*":
            self.access(node, "read", out, chain)
        elif kind == "UnaryOperator" and node.get("opcode") == "&":
            # Only direct call arguments may borrow supported buffer pointers.
            unknown("UNSUPPORTED_ACCESS", "Address escape outside a supported direct call")
            out.effects.append(Effect("escape", expression(args[0]), None, span, chain))
        elif kind == "BinaryOperator" and node.get("opcode") in {
            "+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||", "&", "|", "^", "<<", ">>"
        } or kind == "UnaryOperator" and node.get("opcode") in {"+", "-", "!", "~"}:
            if any("*" in c.get("type", {}).get("qualType", "") for c in args):
                unknown("UNSUPPORTED_ACCESS", "Pointer values outside memory-address expressions are unsupported")
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind in {"IfStmt", "ConditionalOperator"}:
            # Union branch effects; never infer full overwrite from these.
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind == "ReturnStmt" and allow_return:
            if args and ("*" in args[0].get("type", {}).get("qualType", "")):
                unknown("UNSUPPORTED_ACCESS", "Pointer-returning helpers may escape memory")
                self.escape(args[0], out, chain)
            for child in args:
                self.collect(child, out, chain, allow_return)
        elif kind == "CallExpr":
            self.call(node, out, chain, allow_return)
        else:
            unknown("UNSUPPORTED_SYNTAX", f"Unsupported AST node: {kind}")
            # Preserve witnesses for known unsafe effects even in unknown syntax.
            for child in args:
                self.collect(child, out, chain, allow_return)

    def escape(self, node, out, chain):
        expr = expression(node)
        parts = pointer_parts(expr)
        if parts:
            out.effects.append(Effect("escape", parts[0], None, self.tu.span(node), chain))
        else:
            out.unknown.append(reason("UNSUPPORTED_ACCESS", "Unresolved pointer escape", self.tu.span(node), chain))

    def access(self, node, mode, out, chain):
        raw = node
        node = unwrap(node)
        expr = expression(node)
        span = self.tu.span(raw)
        if "volatile" in node.get("type", {}).get("qualType", "") or "_Atomic" in node.get("type", {}).get("qualType", ""):
            out.unknown.append(reason("VOLATILE_OR_ATOMIC", "Ordered memory access", span, chain))
        if expr.kind == "ref":
            out.effects.append(Effect(mode, expr, None, span, chain))
            return
        parts = None
        if expr.kind == "index":
            parts = pointer_parts(expr.args[0])
            if parts:
                parts = parts[0], add(parts[1], expr.args[1])
            # Include memory reads/side effects in indices and pointer arithmetic.
            for child in children(node):
                self.address_inputs(child, out, chain)
        elif expr.kind == "unary" and expr.value == "*":
            parts = pointer_parts(expr.args[0])
            self.address_inputs(children(node)[0], out, chain)
        if parts:
            out.effects.append(Effect(mode, parts[0], parts[1], span, chain))
        else:
            out.unknown.append(reason("UNSUPPORTED_ACCESS", "Cannot resolve memory access to a buffer declaration", span, chain))
            for child in children(node):
                self.collect(child, out, chain)

    def address_inputs(self, node, out, chain):
        expr = expression(node)
        if pointer_parts(expr):
            node = unwrap(node)
            if node.get("kind") == "DeclRefExpr":
                self.collect(node, out, chain)
            elif node.get("kind") == "UnaryOperator" and node.get("opcode") == "&":
                for child in children(children(node)[0]):
                    self.address_inputs(child, out, chain)
            else:
                for child in children(node):
                    self.address_inputs(child, out, chain)
        else:
            self.collect(node, out, chain)

    def call(self, node, out, chain, allow_return):
        args = children(node)
        callee = unwrap(args[0])
        ref = callee.get("referencedDecl", {})
        target = self.tu.aliases.get(ref.get("id"), ref.get("id"))
        name = ref.get("name", "<indirect>")
        out.calls.add(name)
        for arg in args[1:]:
            self.address_inputs(arg, out, chain)
        if ref.get("kind") != "FunctionDecl" or target not in self.tu.functions:
            out.unknown.append(reason("UNKNOWN_CALL", f"No supported body for {name}", self.tu.span(node), chain + (name,)))
            return
        summary = self.summary(target)
        actuals = [expression(a) for a in args[1:]]
        if len(actuals) != len(summary.parameters):
            out.unknown.append(reason("UNKNOWN_CALL", "Variadic/mismatched call", self.tu.span(node), chain + (name,)))
            return
        bindings = {p["id"]: a for p, a in zip(summary.parameters, actuals)}
        out.helper_ids.add(target)
        out.helper_ids.update(summary.helper_ids)
        out.calls.update(summary.calls)
        for issue in summary.unknown:
            out.unknown.append({**issue, "helper_chain": list(chain) + issue["helper_chain"],
                                "call_span": self.tu.span(node)})
        for effect in summary.effects:
            # Scalar by-value argument reads were already evaluated at the call site.
            if effect.base.declaration_id in bindings and effect.index is None and effect.kind != "escape":
                continue
            base = effect.base.substitute(bindings)
            index = effect.index.substitute(bindings) if effect.index is not None else None
            if effect.kind == "escape":
                parts = pointer_parts(base)
                if parts:
                    base = parts[0]
            if index is not None:
                parts = pointer_parts(base)
                if parts is None:
                    out.unknown.append(reason("UNSUPPORTED_ACCESS", "Cannot substitute pointer argument", self.tu.span(node), chain + effect.chain))
                    continue
                base, offset = parts
                index = add(offset, index)
            out.effects.append(Effect(effect.kind, base, index, effect.span, chain + effect.chain))
