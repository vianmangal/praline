"""UTF-8 byte edits with explicit overlap and source-integrity guards."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from praline.model import PralineError


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: bytes


def apply_edits(data: bytes, edits: list[Edit], expected_sha256: str) -> bytes:
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise PralineError("STALE_SOURCE", "Source hash differs from the analyzed file")
    ordered = sorted(edits, key=lambda e: (e.start, e.end))
    previous_end = -1
    previous_start = -1
    for edit in ordered:
        if not 0 <= edit.start <= edit.end <= len(data):
            raise PralineError("INVALID_SPAN", "Source edit falls outside the file")
        if edit.start < previous_end or edit.start == previous_start:
            raise PralineError("OVERLAPPING_EDITS", "Ambiguous or overlapping source edits")
        previous_start, previous_end = edit.start, edit.end
    for edit in reversed(ordered):
        data = data[:edit.start] + edit.replacement + data[edit.end:]
    return data


def statement_end(data, span):
    """Clang excludes a simple statement's semicolon from its source range."""
    end = span["end"]
    # Compound bodies already include their closing brace.
    if data[end - 1:end] == b"}":
        return end
    cursor = end
    while cursor < len(data):
        if data[cursor:cursor + 1].isspace():
            cursor += 1
        elif data[cursor:cursor + 2] == b"/*":
            close = data.find(b"*/", cursor + 2)
            if close == -1:
                break
            cursor = close + 2
        elif data[cursor:cursor + 2] == b"//":
            close = data.find(b"\n", cursor + 2)
            if close == -1:
                break
            cursor = close + 1
        else:
            break
    if data[cursor:cursor + 1] != b";":
        raise PralineError("INVALID_SPAN", "Cannot find complete loop statement terminator")
    return cursor + 1
