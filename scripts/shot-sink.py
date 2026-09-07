#!/usr/bin/env python3
"""Serve the LDraw library to the shot page, drive it headless, and take back
the PNGs it renders.

    .venv/bin/python scripts/shot-sink.py --parts 3001,3030 --out out/ortho

The shot page (`lab/shot.html`) is a browser, so it cannot read the library off
disk or write a render to one. This gives it both ends over HTTP: `/ldraw/...`
is the vendored library, `/work.json` is the list of parts to draw, and a POST
to `/shot/<part>.png` lands the render in `--out`.

One browser renders the whole list in one WebGL context; a page load per part
costs more than the render does.

**It serves the page too, out of `lab/dist`, and launches its own headless
Chrome.** A bake of 24,591 parts cannot need a person to open a tab, and it
must not need the vite dev server either -- that is a second process to keep
alive on a fleet node for no gain. `npm run build` in `lab/` refreshes the
page; `--page` overrides the URL if you want the dev server after all, and
`--no-browser` goes back to opening it by hand.

Headless Chrome has no GPU, so WebGL comes from SwiftShader and the flags
below are what turn it on. Without them the page loads and renders nothing.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LDRAW = ROOT / "vendor" / "ldraw"
DIST = ROOT / "lab" / "dist"

TYPES = {".dat": "text/plain", ".ldr": "text/plain", ".txt": "text/plain",
         ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
         ".json": "application/json", ".svg": "image/svg+xml"}

CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium")

# SwiftShader is the whole point: --headless has no GPU, and WebGL is off
# without an explicit software rasterizer. --enable-unsafe-swiftshader is
# required from Chrome 131 on, where the fallback stopped being automatic.
CHROME_FLAGS = ("--headless=new", "--disable-gpu", "--use-gl=angle",
                "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                "--no-first-run", "--no-default-browser-check",
                "--disable-dev-shm-usage", "--mute-audio",
                "--window-size=1280,1024")


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
        # the built page and its assets, so no dev server is needed
        rel = path.lstrip("/") or "shot.html"
        target = (DIST / rel).resolve()
        if str(target).startswith(str(DIST.resolve())) and target.is_file():
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
    ap.add_argument("--page", help="page URL; default is the sink's own copy "
                                   "of lab/dist/shot.html")
    ap.add_argument("--chrome", help="browser binary; default is the first of "
                                     "Chrome or Chromium that exists")
    ap.add_argument("--no-browser", dest="browser", action="store_false",
                    help="serve and wait for a page opened by hand")
    ap.add_argument("--timeout", type=float, default=0,
                    help="seconds to wait for the page; 0 waits forever")
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
    print(f"onto: plan 0/{len(parts)}", flush=True)

    url = args.page or f"http://127.0.0.1:{args.port}/shot.html"
    url += f"?sink=http://127.0.0.1:{args.port}"
    proc = profile = None
    if args.browser:
        exe = args.chrome or next((c for c in CHROME if Path(c).is_file()), None)
        if exe is None:
            print("no Chrome or Chromium found; pass --chrome or --no-browser",
                  file=sys.stderr)
            return 2
        if not (DIST / "shot.html").is_file() and not args.page:
            print(f"{DIST / 'shot.html'} is missing; run `npm run build` in "
                  f"lab/, or pass --page", file=sys.stderr)
            return 2
        # A throwaway profile: Chrome refuses a second headless run against a
        # profile the user's own window already holds.
        profile = tempfile.mkdtemp(prefix="shot-chrome-")
        proc = subprocess.Popen(
            [exe, *CHROME_FLAGS, f"--user-data-dir={profile}", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"chrome {proc.pid} on {url}", flush=True)
    else:
        print(f"open {url}", flush=True)

    try:
        ok = Sink.done.wait(args.timeout or None)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if profile:
            shutil.rmtree(profile, ignore_errors=True)
        server.shutdown()
    if not ok:
        print(f"timed out after {args.timeout}s with "
              f"{Sink.received}/{len(parts)}", file=sys.stderr)
    print(f"done: {Sink.received}/{len(parts)}", flush=True)
    return 0 if Sink.received == len(parts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
