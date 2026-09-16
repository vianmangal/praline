"""Clang JSON adapter. All semantic facts originate in the AST, not C text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from dataclasses import dataclass, field

from praline.model import AnalysisConfig, Declaration, Expr, PralineError


def walk(node):
    yield node
    for child in node.get("inner", []):
        yield from walk(child)


def children(node):
    return [c for c in node.get("inner", []) if c.get("kind")]


def unwrap(node):
    while node.get("kind") in {"ParenExpr", "ConstantExpr"} or (
        node.get("kind") == "ImplicitCastExpr" and node.get("castKind") in {
            "LValueToRValue", "ArrayToPointerDecay", "FunctionToPointerDecay", "NoOp"
        }
    ):
        node = children(node)[0]
    return node


def expression(node) -> Expr:
    node = unwrap(node)
    kind, args = node.get("kind"), children(node)
    typ = node.get("type", {}).get("qualType", "")
    if kind == "DeclRefExpr":
        d = node["referencedDecl"]
        return Expr("ref", d.get("name", ""), declaration_id=d["id"], ctype=typ)
    if kind in {"IntegerLiteral", "FloatingLiteral", "CharacterLiteral"}:
        return Expr("literal", str(node["value"]), ctype=typ)
    if kind == "BinaryOperator":
        return Expr("binary", node["opcode"], tuple(expression(c) for c in args), ctype=typ)
    if kind == "UnaryOperator":
        return Expr("unary", node["opcode"], (expression(args[0]),), ctype=typ)
    if kind == "ArraySubscriptExpr":
        return Expr("index", args=tuple(expression(c) for c in args), ctype=typ)
    if kind in {"ImplicitCastExpr", "CStyleCastExpr"}:
        return Expr("cast", typ, (expression(args[0]),), ctype=typ)
    if kind == "CallExpr":
        callee = expression(args[0])
        return Expr("call", callee.value, tuple(expression(c) for c in args[1:]),
                    callee.declaration_id, typ)
    return Expr("unknown", f"<{kind}>", ctype=typ)


@dataclass
class TranslationUnit:
    path: Path
    data: bytes
    ast: dict
    compiler: dict
    declarations: dict[str, Declaration] = field(default_factory=dict)
    functions: dict[str, dict] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @property
    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()

    def span(self, node):
        r = node.get("range", {})
        b, e = r.get("begin", {}), r.get("end", {})
        if any("spellingLoc" in x or "expansionLoc" in x for x in (b, e)):
            return None
        if "offset" not in b or "offset" not in e:
            return None
        start, end = b["offset"], e["offset"] + e.get("tokLen", 0)
        if not 0 <= start <= end <= len(self.data):
            return None
        for loc in (b, e, node.get("loc", {})):
            if loc.get("includedFrom"):
                return None
            if loc.get("file") and Path(loc["file"]).resolve() != self.path:
                return None
        return {"start": start, "end": end,
                "line": self.data.count(b"\n", 0, start) + 1,
                "column": start - self.data.rfind(b"\n", 0, start),
                "end_line": self.data.count(b"\n", 0, end) + 1}

    def text(self, node):
        s = self.span(node)
        return self.data[s["start"]:s["end"]].decode("utf-8") if s else ""

    def index(self):
        def visit(node, function=None):
            k = node.get("kind")
            if k == "FunctionDecl":
                function = node["id"]
            if k in {"VarDecl", "ParmVarDecl"}:
                storage = "parameter" if k == "ParmVarDecl" else (
                    "global" if function is None or node.get("storageClass") in {"static", "extern"}
                    or node.get("tls") else "local")
                self.declarations[node["id"]] = Declaration(
                    node["id"], node.get("name", ""),
                    node.get("type", {}).get("desugaredQualType", node.get("type", {}).get("qualType", "")),
                    storage, node, function)
            for c in children(node):
                visit(c, function)
        visit(self.ast)
        # Canonical identity follows Clang's declaration chain, never spelling alone.
        declarations = [n for n in children(self.ast) if n.get("kind") == "FunctionDecl"]
        for n in declarations:
            root = self.aliases.get(n.get("previousDecl"), n.get("previousDecl", n["id"]))
            self.aliases[n["id"]] = root
        for n in declarations:
            if any(c.get("kind") == "CompoundStmt" for c in children(n)) and self.span(n):
                root = self.aliases[n["id"]]
                self.functions[root] = n
        return self


def parse_source(path, config: AnalysisConfig | None = None) -> TranslationUnit:
    config = config or AnalysisConfig()
    path = Path(path).resolve()
    try:
        data = path.read_bytes()
        data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PralineError("SOURCE_ERROR", str(exc)) from exc
    command = [config.clang, "-std=c11", *config.clang_args, "-Xclang", "-fopenmp",
               "-Xclang", "-ast-dump=json", "-fsyntax-only", str(path)]
    try:
        version = subprocess.run([config.clang, "--version"], capture_output=True,
                                 text=True, timeout=config.timeout_seconds, check=False)
        process = subprocess.run(command, capture_output=True, text=True,
                                 timeout=config.timeout_seconds, check=False)
    except FileNotFoundError as exc:
        raise PralineError("COMPILER_NOT_FOUND", str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise PralineError("COMPILER_TIMEOUT", f"Clang exceeded {config.timeout_seconds} seconds") from exc
    except OSError as exc:
        raise PralineError("COMPILER_ERROR", str(exc)) from exc
    try:
        unchanged = path.read_bytes() == data
    except OSError:
        unchanged = False
    if not unchanged:
        raise PralineError("SOURCE_CHANGED", "Source changed while Clang was parsing it")
    if process.returncode:
        raise PralineError("PARSE_ERROR", process.stderr.strip())
    try:
        ast = json.loads(process.stdout)
    except (ValueError, TypeError) as exc:
        raise PralineError("AST_ERROR", "Clang did not return a JSON AST") from exc
    return TranslationUnit(path, data, ast,
        {"executable": config.clang, "version": version.stdout.strip() or None,
         "command": command, "diagnostics": process.stderr}).index()
