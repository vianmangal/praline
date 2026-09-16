"""Compile original and generated programs with comparable optimization flags."""
from __future__ import annotations
import hashlib
from pathlib import Path
from praline.execution.process import run


def source_hash(source: str | Path) -> str:
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def compile_program(source: str | Path, output: str | Path, toolchain: dict, *,
                    target: str = "sequential", extra_flags: list[str] | None = None,
                    timeout: float = 60, include_dirs: list[str] | None = None) -> dict:
    if target not in ("sequential", "cpu", "gpu"):
        raise ValueError("Invalid execution target")
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("Compiler output must not overwrite source")
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = toolchain.get("selected")
    evidence = dict(source=str(source), source_hash=source_hash(source), output=str(output), target=target)
    if not selected:
        return {**evidence, "status":"unavailable", "reason":"No C compiler detected"}
    flags = ["-std=c11", "-O2"]
    if target != "sequential":
        omp = selected.get("openmp_flags")
        if omp is None:
            return {**evidence, "status":"unavailable", "reason":"CPU OpenMP probe failed"}
        flags += omp
    if target == "gpu":
        flags += toolchain.get("gpu", {}).get("offload_flags", [])
    flags += extra_flags or []
    for directory in include_dirs or []:
        flags += ["-I", str(Path(directory).resolve())]
    evidence["dependencies"] = {str(header):source_hash(header) for directory in include_dirs or []
        for header in [Path(directory).resolve()/"runtime.h"] if header.exists()}
    outcome = run([selected["path"], *flags, str(source), "-o", str(output)], timeout=timeout)
    return {**evidence, **outcome, "compiler":selected, "optimization":"-O2"}


def compile_pair(original: str | Path, generated: str | Path, out: str | Path,
                 toolchain: dict, *, target: str = "cpu", **kwargs) -> dict:
    root = Path(out)
    include_dirs = [str(Path(original).resolve().parent)]
    return {"sequential":compile_program(original, root/"sequential", toolchain,
                                         include_dirs=include_dirs, **kwargs),
            "generated":compile_program(generated, root/"generated", toolchain,
                                        target=target, include_dirs=include_dirs, **kwargs)}
