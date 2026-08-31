"""`python -m brick_icons.lab` — the lab server."""
from __future__ import annotations

import argparse

import uvicorn

from .app import create_app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="brick-icons-lab")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8792)
    p.add_argument("--root", default=".")
    args = p.parse_args(argv)
    print(f"lab on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(create_app(root=args.root), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
