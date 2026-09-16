"""Stable public configuration and small declaration-based compiler IR."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PralineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class AnalysisConfig:
    clang: str = "clang"
    clang_args: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    extents: dict[str, str] = field(default_factory=dict)
    assume_disjoint: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Expr:
    kind: str
    value: str = ""
    args: tuple[Expr, ...] = ()
    declaration_id: str = ""
    ctype: str = ""

    def render(self) -> str:
        if self.kind in {"ref", "literal", "unknown"}:
            return self.value
        if self.kind == "binary":
            return f"({self.args[0].render()} {self.value} {self.args[1].render()})"
        if self.kind == "unary":
            return f"({self.value}{self.args[0].render()})"
        if self.kind == "index":
            return f"{self.args[0].render()}[{self.args[1].render()}]"
        if self.kind == "cast":
            return f"(({self.value}){self.args[0].render()})"
        if self.kind == "call":
            return f"{self.value}({', '.join(a.render() for a in self.args)})"
        return "<?>"

    def substitute(self, bindings: dict[str, Expr]) -> Expr:
        if self.kind == "ref" and self.declaration_id in bindings:
            return bindings[self.declaration_id]
        return Expr(self.kind, self.value, tuple(a.substitute(bindings) for a in self.args),
                    self.declaration_id, self.ctype)

    def references(self) -> set[str]:
        refs = {self.declaration_id} if self.kind == "ref" else set()
        for a in self.args:
            refs.update(a.references())
        return refs


def literal(value: int) -> Expr:
    return Expr("literal", str(value), ctype="int")


def add(left: Expr, right: Expr) -> Expr:
    if right == literal(0):
        return left
    if left == literal(0):
        return right
    return Expr("binary", "+", (left, right), ctype="int")


@dataclass
class Declaration:
    id: str
    name: str
    ctype: str
    storage: str
    node: dict[str, Any]
    function: str | None = None

    @property
    def pointer(self) -> bool:
        return "*" in self.ctype or "[" in self.ctype


@dataclass
class Effect:
    kind: str
    base: Expr
    index: Expr | None
    span: dict | None
    chain: tuple[str, ...] = ()

    def to_dict(self, declarations: dict[str, Declaration]) -> dict:
        decl = declarations.get(self.base.declaration_id)
        return {"kind": self.kind, "declaration_id": self.base.declaration_id,
                "name": self.base.value, "storage": decl.storage if decl else "unknown",
                "index": self.index.render() if self.index is not None else None,
                "span": self.span, "helper_chain": list(self.chain)}


def reason(code: str, message: str, span: dict | None = None,
           chain: tuple[str, ...] = ()) -> dict:
    return {"code": code, "message": message, "span": span, "helper_chain": list(chain)}
