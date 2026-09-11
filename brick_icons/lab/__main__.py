"""`python -m brick_icons.lab` — the lab server."""
from __future__ import annotations

import argparse
import os

import uvicorn

from .app import create_app

#: Where `_factory` reads its root from. Reloading re-imports this module in a
#: fresh process, which never sees the parsed arguments, so the one thing the
#: factory needs travels in the environment.
ROOT_ENV = "BRICK_ICONS_LAB_ROOT"


def _factory():
    return create_app(root=os.environ.get(ROOT_ENV, "."))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="brick-icons-lab")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8792)
    p.add_argument("--root", default=".")
    # Without this the server serves whatever the code said when it started,
    # for as long as it runs -- and the page in front of it does not, because
    # vite reloads on every edit. The dashboard crashed on a `cost` row that
    # had gained a field hours earlier: current markup, a server from before
    # the field existed. Off by default because a reloader watches the tree
    # and several sessions share this checkout.
    p.add_argument("--reload", action="store_true",
                   help="restart when brick_icons/ changes")
    args = p.parse_args(argv)
    print(f"lab on http://{args.host}:{args.port}"
          f"{' (reloading)' if args.reload else ''}", flush=True)
    if args.reload:
        os.environ[ROOT_ENV] = args.root
        # The qualified path, not `__name__`: under `python -m` that is
        # "__main__", and the reloader's subprocess would re-import uvicorn's
        # entry point under that name rather than this module.
        uvicorn.run("brick_icons.lab.__main__:_factory", factory=True, reload=True,
                    reload_dirs=["brick_icons"], host=args.host, port=args.port)
    else:
        uvicorn.run(create_app(root=args.root), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
