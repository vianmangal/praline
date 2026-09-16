"""Discover capabilities by compiling and running probes, never by brand name."""
from __future__ import annotations
import os
from pathlib import Path
import platform
import shlex
import shutil
import tempfile
from praline.execution.process import run

CPU_PROBE = '''#include <stdio.h>
#include <omp.h>
int main(void) { int n=0;
#pragma omp parallel reduction(+:n)
 n += 1;
printf("%d\\n", n); return n < 1; }
'''
GPU_PROBE = '''#include <stdio.h>
#include <omp.h>
int main(void) { int initial=1;
#pragma omp target map(from:initial)
 initial=omp_is_initial_device();
printf("%d %d\\n", omp_get_num_devices(), initial);
return initial; }
'''


def candidates(explicit: str | None = None) -> list[str]:
    choices = [explicit or os.environ.get("CC"), "clang", "gcc"]
    choices += ["/opt/homebrew/opt/llvm/bin/clang", "/usr/local/opt/llvm/bin/clang"]
    found = []
    for choice in choices:
        path = shutil.which(choice) if choice else None
        if path and path not in found:
            found.append(path)
    return found


def openmp_flag_candidates(compiler: str) -> list[list[str]]:
    flags = [["-fopenmp"]]
    if platform.system() == "Darwin":
        for root in (Path("/opt/homebrew/opt/libomp"), Path("/usr/local/opt/libomp")):
            if (root / "include/omp.h").exists():
                flags.append(["-Xpreprocessor", "-fopenmp", "-I"+str(root/"include"),
                              "-L"+str(root/"lib"), "-Wl,-rpath,"+str(root/"lib"), "-lomp"])
    return flags


def detect(compiler: str | None = None, *, timeout: float = 30,
           offload_flags: list[str] | None = None) -> dict:
    result = dict(status="unavailable", environment={"system": platform.system(),
                  "release": platform.release(), "machine": platform.machine(),
                  "processor": platform.processor(), "cpu_count": os.cpu_count(),
                  "python": platform.python_version()}, compilers=[], selected=None,
                  cpu_openmp={"status": "unavailable", "reason": "No successful OpenMP probe"},
                  gpu={"status": "unavailable", "reason": "No device-verified offload probe"})
    with tempfile.TemporaryDirectory(prefix="praline-doctor-") as temp:
        root = Path(temp)
        c = root / "probe.c"
        binary = root / "probe"
        for path in candidates(compiler):
            version = run([path, "--version"], timeout=timeout)
            c.write_text("int main(void){return 0;}\n")
            serial = run([path, "-std=c11", "-O2", str(c), "-o", str(binary)], timeout=timeout)
            ast = run([path, "-Xclang", "-ast-dump=json", "-fsyntax-only", str(c)], timeout=timeout)
            entry = dict(path=path, version=version["stdout"].strip(), serial=serial,
                         clang_ast_status=ast["status"], openmp_attempts=[])
            result["compilers"].append(entry)
            if serial["status"] == "ok" and result["selected"] is None:
                result["selected"] = dict(path=path, version=entry["version"], openmp_flags=None)
                result["status"] = "ok"
            c.write_text(CPU_PROBE)
            for flags in openmp_flag_candidates(path):
                compile_result = run([path, "-std=c11", "-O2", str(c), "-o", str(binary), *flags], timeout=timeout)
                executed = run([str(binary)], timeout=timeout, env={"OMP_NUM_THREADS":"2"}) if compile_result["status"] == "ok" else None
                entry["openmp_attempts"].append(dict(flags=flags, compile=compile_result, execution=executed))
                if executed and executed["status"] == "ok" and executed["stdout"].strip() == "2":
                    result["selected"] = dict(path=path, version=entry["version"], openmp_flags=flags)
                    result["cpu_openmp"] = dict(status="verified", threads=2, compile=compile_result, execution=executed)
                    break
            if result["cpu_openmp"]["status"] == "verified":
                break
        selected = result["selected"]
        if selected and selected["openmp_flags"] is not None:
            flags = offload_flags if offload_flags is not None else shlex.split(os.environ.get("PRALINE_OFFLOAD_FLAGS", ""))
            c.write_text(GPU_PROBE)
            compiled = run([selected["path"], "-std=c11", "-O2", str(c), "-o", str(binary),
                            *selected["openmp_flags"], *flags], timeout=timeout)
            executed = run([str(binary)], timeout=timeout, env={"OMP_TARGET_OFFLOAD":"MANDATORY"}) if compiled["status"] == "ok" else None
            verified = False
            if executed and executed["status"] == "ok":
                parts = executed["stdout"].split()
                verified = len(parts) == 2 and parts[0].isdigit() and int(parts[0]) > 0 and parts[1] == "0"
            result["gpu"] = dict(status="device-verified" if verified else "unavailable",
                reason=None if verified else "Mandatory target execution did not establish a non-host device",
                offload_flags=flags, compile=compiled, execution=executed,
                device_metadata={"model":None,"driver":None,"backend":None})
    return result
