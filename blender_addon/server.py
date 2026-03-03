"""
Blender 内本地 HTTP 服务（MVP 骨架）。

- GET /health
- GET /tools
- POST /tool  {"tool": "...", "args": {...}}
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bpy

from .tools import execute_whitelisted_tool, list_whitelist_tools


class BlenderToolHttpServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None
        self.running = False

    def start(self):
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.path == "/health":
                    self._reply(200, {"ok": True, "data": {"status": "running"}})
                    return
                if self.path == "/tools":
                    self._reply(200, {"ok": True, "data": list_whitelist_tools()})
                    return
                self._reply(404, {"ok": False, "error": f"unknown path: {self.path}"})

            def do_POST(self):  # noqa: N802
                if self.path != "/tool":
                    self._reply(404, {"ok": False, "error": f"unknown path: {self.path}"})
                    return
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
                    req = json.loads(raw.decode("utf-8"))
                    tool = req.get("tool")
                    args = req.get("args") or {}
                    result = parent._execute_in_main_thread(tool, args)
                    self._reply(200 if result.get("ok") else 400, result)
                except Exception as e:
                    self._reply(500, {"ok": False, "error": str(e), "logs": ["server_exception"]})

            def log_message(self, format, *args):
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.running = True
        self._thread = threading.Thread(target=self._serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None

    def _serve_forever(self):
        if self._httpd:
            self._httpd.serve_forever(poll_interval=0.5)

    def _execute_in_main_thread(self, tool: str, args: dict) -> dict:
        if not tool:
            return {"ok": False, "success": False, "error": "missing tool", "logs": ["missing_tool"]}

        import queue

        result_queue = queue.Queue()

        def _do_action():
            try:
                result_queue.put(execute_whitelisted_tool(tool, args))
            except Exception as e:
                result_queue.put({"ok": False, "success": False, "error": str(e), "logs": ["exec_exception"]})
            return None

        bpy.app.timers.register(_do_action)
        try:
            return result_queue.get(timeout=30.0)
        except Exception:
            return {"ok": False, "success": False, "error": "timeout", "logs": ["timeout"]}
