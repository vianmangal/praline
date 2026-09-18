"""Bounded subprocess execution with auditable commands and timeout states."""
from __future__ import annotations
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import threading

MAX_OUTPUT = 32 * 1024 * 1024


def run(command: list[str], *, timeout: float = 30, env: dict | None = None,
        cwd: str | Path | None = None) -> dict:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be positive and finite")
    started = time.perf_counter()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                       cwd=cwd, env={**os.environ, **(env or {})},
                                       start_new_session=True)
        except OSError as exc:
            return dict(status="unavailable", command=command, returncode=None,
                        stdout="", stderr=str(exc), elapsed_seconds=time.perf_counter()-started)
        finished = threading.Event()
        stopped = []
        def watchdog():
            while not finished.is_set():
                remaining = timeout - (time.perf_counter() - started)
                too_large = os.fstat(stdout.fileno()).st_size > MAX_OUTPUT or os.fstat(stderr.fileno()).st_size > MAX_OUTPUT
                if remaining <= 0 or too_large:
                    stopped.append("output_limit" if too_large else "timeout")
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    return
                finished.wait(min(.02, remaining))
        watcher = threading.Thread(target=watchdog, daemon=True)
        watcher.start()
        # Blocking wait uses the OS completion notification. Popen.wait(timeout)
        # polls with backoff on POSIX and would inflate short end-to-end trials.
        process.wait()
        finished.set()
        elapsed = time.perf_counter() - started
        watcher.join()
        status = stopped[0] if stopped else "ok"
        stdout.seek(0)
        stderr.seek(0)
        output, errors = stdout.read(MAX_OUTPUT + 1), stderr.read(MAX_OUTPUT + 1)
        if len(output) > MAX_OUTPUT or len(errors) > MAX_OUTPUT:
            status = "output_limit"
        elif status == "ok" and process.returncode:
            status = "failed"
        return dict(status=status, command=command, returncode=process.returncode,
                    stdout=output[:MAX_OUTPUT].decode("utf-8", errors="replace"),
                    stderr=errors[:MAX_OUTPUT].decode("utf-8", errors="replace"),
                    elapsed_seconds=elapsed, environment=env or {})
