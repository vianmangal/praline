"""Small localhost UI for the Praline compiler core.

The web layer performs analysis and source transformation only. It deliberately
does not execute uploaded C programs.
"""
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import tempfile
import webbrowser

from praline.execution import core


ASSET_ROOT = Path(__file__).with_name("web_assets")
MAX_REQUEST_BYTES = 1_000_000


def _parse_extents(value) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k).strip(): str(v).strip() for k, v in value.items() if str(k).strip() and str(v).strip()}
    result: dict[str, str] = {}
    for item in str(value or "").split(","):
        name, separator, expression = item.strip().partition("=")
        if separator and name.strip() and expression.strip():
            result[name.strip()] = expression.strip()
    return result


def _parse_disjoint(value) -> list[tuple[str, str]]:
    if isinstance(value, list):
        pairs = value
    else:
        pairs = [item.split(",") for item in str(value or "").split(";") if item.strip()]
    result = []
    for pair in pairs:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            left, right = (str(part).strip() for part in pair)
            if left and right and left != right:
                result.append((left, right))
    return result


def analyze_submission(payload: dict) -> dict:
    """Analyze one browser submission and optionally return transformed source."""
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Paste C source or choose a .c file first.")
    encoded = code.encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("Source is larger than the 1 MB localhost limit.")

    filename = Path(str(payload.get("filename") or "input.c")).name
    if not filename.lower().endswith(".c"):
        raise ValueError("Upload a C source file ending in .c.")
    target = str(payload.get("target") or "cpu")
    if target not in {"cpu", "gpu"}:
        raise ValueError("Target must be cpu or gpu.")
    extents = _parse_extents(payload.get("extents"))
    assume_disjoint = _parse_disjoint(payload.get("assume_disjoint"))
    bundled_clang = Path(__file__).resolve().parents[1] / "vendor" / "bin" / "clang"
    clang = str(bundled_clang) if bundled_clang.is_file() else os.environ.get("PRALINE_CLANG", "clang")

    with tempfile.TemporaryDirectory(prefix="praline-web-") as temporary:
        root = Path(temporary)
        source = root / filename
        source.write_text(code, encoding="utf-8")
        report = core.analyze(
            str(source),
            clang=clang,
            extents=extents,
            assume_disjoint=assume_disjoint,
            timeout=15,
        )

        result = {
            "ok": report.get("status") != "error",
            "filename": filename,
            "target": target,
            "analysis": report,
            "generated": None,
            "diff": None,
            "transformation_error": None,
        }
        safe_loops = [loop for loop in report.get("loops", []) if loop.get("decision") == "safe"]
        if result["ok"] and safe_loops:
            try:
                transformed = core.transform(source, report, target=target, out=root / "output")
                result["generated"] = transformed["source"]
                result["diff"] = transformed["diff"]
            except Exception as exc:  # Praline errors carry user-facing codes.
                result["transformation_error"] = {
                    "code": getattr(exc, "code", "TRANSFORMATION_ERROR"),
                    "message": str(exc),
                }
        return result


class PralineWebHandler(BaseHTTPRequestHandler):
    server_version = "PralineWeb/0.1"

    def log_message(self, format_string: str, *args) -> None:
        print(f"[praline web] {self.address_string()} - {format_string % args}")

    def _send_bytes(self, body: bytes, content_type: str, status=HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, value: dict, status=HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:
        routes = {
            "/": "index.html",
            "/analyze": "analyze.html",
            "/styles.css": "styles.css",
            "/app.js": "app.js",
        }
        asset_name = routes.get(self.path.split("?", 1)[0])
        if asset_name is None:
            self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        path = ASSET_ROOT / asset_name
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self._send_bytes(path.read_bytes(), content_type)

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES + 100_000:
            self._send_json({"ok": False, "error": "Invalid or oversized request."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object.")
            result = analyze_submission(payload)
            self._send_json(result)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def serve(host: str = "127.0.0.1", port: int = 8000, *, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), PralineWebHandler)
    url = f"http://{host}:{server.server_port}"
    print(f"Praline is running at {url}")
    print("Press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Praline.")
    finally:
        server.server_close()


__all__ = ["MAX_REQUEST_BYTES", "PralineWebHandler", "analyze_submission", "serve"]
