"""聊天界面 Web 入口（Week3）：Python 标准库 http.server，零额外依赖。

    python -m ui.app                 # http://127.0.0.1:8765
    SHOPAGENT_UI_PORT=9000 python -m ui.app

接口（JSON）：
    GET  /              单页聊天界面（ui/static/index.html）
    GET  /api/health    {"ok": true, "payment_mode": "stub"}
    POST /api/run       {"instruction": "..."}            → run 视图模型
    POST /api/resume    {"run_id": "...", "action": "approve|confirm|cancel",
                         "new_budget": 123.4?}            → run 视图模型

业务逻辑全在 ui/service.py（可单测）；本文件只做 HTTP 解析/序列化。
支付为离线桩（pay.stub），页面与接口都会如实标注 stub。
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from ui.service import ChatService

_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_service: Optional[ChatService] = None


def get_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service


def _read_json(body: bytes) -> Dict[str, Any]:
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def handle(method: str, path: str, payload: Dict[str, Any],
             service: ChatService) -> Tuple[int, str, bytes]:
    """纯函数路由（可单测）：返回 (status, content_type, body_bytes)。"""
    if method == "GET" and path in ("/", "/index.html"):
        with open(os.path.join(_STATIC, "index.html"), "rb") as fh:
            return 200, "text/html; charset=utf-8", fh.read()
    if method == "GET" and path == "/api/health":
        return _json(200, {"ok": True, "payment_mode": "stub"})
    if method == "POST" and path == "/api/run":
        try:
            view = service.start_run(payload.get("instruction", ""))
            return _json(200, view)
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
    if method == "POST" and path == "/api/resume":
        try:
            view = service.act(
                payload.get("run_id", ""),
                payload.get("action", ""),
                new_budget=payload.get("new_budget"),
            )
            return _json(200, view)
        except (ValueError, FileNotFoundError) as exc:
            return _json(400, {"error": str(exc)})
    return _json(404, {"error": f"no route: {method} {path}"})


def _json(status: int, obj: Dict[str, Any]) -> Tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(
        obj, ensure_ascii=False).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def _dispatch(self, method: str) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = _read_json(body) if method == "POST" else {}
        except (ValueError, UnicodeDecodeError):
            status, ctype, data = _json(400, {"error": "请求体不是合法 JSON"})
            return self._send(status, ctype, data)
        path = self.path.split("?", 1)[0]
        status, ctype, data = handle(method, path, payload, get_service())
        self._send(status, ctype, data)

    def _send(self, status: int, ctype: str, data: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (http.server 约定)
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def log_message(self, *args: Any) -> None:  # 关掉默认 stderr 噪声
        pass


def main() -> None:
    port = int(os.environ.get("SHOPAGENT_UI_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"ShopAgent UI → http://127.0.0.1:{port}  "
          f"（离线演示：支付为 stub 桩，非真实 PayPal）")
    server.serve_forever()


if __name__ == "__main__":
    main()
