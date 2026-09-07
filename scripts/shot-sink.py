#!/usr/bin/env python3
"""Serve the LDraw library to the shot page and take back the PNGs it renders.

    .venv/bin/python scripts/shot-sink.py --parts 3001,3030 --out out/ortho

The shot page (`lab/shot.html`) is a browser, so it cannot read the library off
disk or write a render to one. This gives it both ends over HTTP: `/ldraw/...`
is the vendored library, `/work.json` is the list of parts to draw, and a POST
to `/shot/<part>.png` lands the render in `--out`.

One browser renders the whole list in one WebGL context; a page load per part
costs more than the render does.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LDRAW = ROOT / "vendor" / "ldraw"

TYPES = {".dat": "text/plain", ".ldr": "text/plain", ".txt": "text/plain"}


class Sink(BaseHTTPRequestHandler):
    parts: list[str] = []
    out: Path = Path(".")
    px: int = 512
    angle: str = "iso"
    done: threading.Event = threading.Event()
    received = 0

    def log_message(self, *a):  # the render loop prints its own progress
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/work.json":
            body = json.dumps({"parts": Sink.parts, "px": Sink.px,
                               "angle": Sink.angle}).encode()
            return self._send(200, body, "application/json")
        if path.startswith("/ldraw/"):
            # `resolve` under LDRAW is the containment check: a part name comes
            # from the page, and the page is not a trusted input.
            target = (LDRAW / path[len("/ldraw/"):]).resolve()
            if not str(target).startswith(str(LDRAW.resolve())) or not target.is_file():
                return self._send(404, b"no", "text/plain")
            ctype = TYPES.get(target.suffix.lower(), "application/octet-stream")
            return self._send(200, target.read_bytes(), ctype)
        self._send(404, b"no", "text/plain")

    def do_OPTIONS(self) -> None:
        self._send(204, b"", "text/plain")

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/done":
            Sink.done.set()
            return self._send(200, b"ok", "text/plain")
        if not path.startswith("/shot/"):
            return self._send(404, b"no", "text/plain")
        name = Path(path[len("/shot/"):]).name
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode()
        png = base64.b64decode(raw.split(",", 1)[1] if "," in raw else raw)
        Sink.out.mkdir(parents=True, exist_ok=True)
        (Sink.out / name).write_bytes(png)
        Sink.received += 1
        print(f"  {Sink.received}/{len(Sink.parts)} {name} {len(png)}b", flush=True)
        self._send(200, b"ok", "text/plain")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", help="comma-separated part ids")
    ap.add_argument("--list", help="file with one part per line")
    ap.add_argument("--out", default="out/ortho")
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--port", type=int, default=8801)
    args = ap.parse_args()

    if args.list:
        parts = [s for ln in Path(args.list).read_text().splitlines()
                 if (s := ln.split("#")[0].strip())]
    elif args.parts:
        parts = [p.strip() for p in args.parts.split(",") if p.strip()]
    else:
        print("need --parts or --list", file=sys.stderr)
        return 2

    Sink.parts, Sink.out = parts, Path(args.out)
    Sink.px, Sink.angle = args.px, args.angle
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Sink)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"sink on :{args.port}, {len(parts)} parts -> {Sink.out}", flush=True)
    Sink.done.wait()
    server.shutdown()
    print(f"done: {Sink.received}/{len(parts)}", flush=True)
    return 0 if Sink.received == len(parts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
