# A menu bar item that runs the lab

**Status: built and installed.** `scripts/lab-agents.sh`, `menubar.yaml`, and
`/api/health` in `brick_icons/lab/app.py`.

For whoever implements or reviews the change: how the lab comes to run under
launchd, and what the menu bar item shows and does.

## Why

The lab is two processes started by hand in two terminals: the API
(`python -m brick_icons.lab`, port 8792) and the front end (`vite`, port 5178).
Nothing restarts either, and nothing says whether they are up.

perch is the generator that turns a `menubar.yaml` into a macOS status-bar app.
A perch action is a subprocess perch waits on, so a menu item cannot hold a
server open. The lab therefore needs launchd agents first, and the menu drives
those. transom, the render wall, is built the same way and is the model here.

## What changes

### 1. `scripts/lab-agents.sh`

Verbs: `install`, `up`, `down`, `cycle`, `stat`, `log`, and `plists`, which
writes the agents and starts nothing.

| Label | Runs | In | Port |
|---|---|---|---:|
| `tech.michaelbaker.brick-icons.lab-api` | `.venv/bin/python -m brick_icons.lab --reload --quiet` | repo root | 8792 |
| `tech.michaelbaker.brick-icons.lab-front` | `node_modules/.bin/vite` | `lab/` | 5178 |

Both agents set `RunAtLoad` and `KeepAlive`. `PATH` in each plist starts with
the directory of the `node` that ran `install`, because launchd starts with
almost no `PATH` and `vite` is a node shebang.

- `install` writes both plists, links the script into `~/.local/bin` as
  `brick-lab`, then boots out and bootstraps each agent. It waits for launchd
  to release a label before bootstrapping it again; a bootstrap inside that
  window fails and leaves nothing loaded.
- `install` refuses to run from a linked worktree. The plists carry an
  absolute repo path, and an agent pointed at a worktree dies when the
  worktree is removed.
- `install` stops a lab already holding either port. A stray server makes the
  agent exit on start, and `KeepAlive` turns that into a restart loop.
- `log` opens the log directory in Finder.

**The API runs with `--reload`.** The front end reloads on every edit, and a
server that does not has already crashed the dashboard once: current markup
against a server started before a field existed.

**Logs** go to `~/.local/state/brick-icons/lab-api.log` and `lab-front.log`.
The API runs with `--quiet`, a new flag that turns uvicorn's access log off,
and `install`, `up` and `cycle` truncate both files, so neither grows without
bound.

### 2. `GET /api/health`

Returns `{"ok": true, "build": "<count>.<short sha>"}`, where `build` is
`brick_icons.build()`, the stamp census rows already carry, as of when the
server started. It reads no database. Every
existing route reads `corpus.db` or builds a listing, which is too heavy to
poll every five seconds.

### 3. `menubar.yaml`

At the repo root, with `menubar.schema.json` beside it (from `perch schema`)
and the emitted Swift committed under `menubar/Generated/`.

It watches both agents, the health route and the front end's root page. The
state is the first of these that holds:

| State | Holds when | Icon |
|---|---|---|
| `uninstalled` | the API agent has no plist | warning triangle |
| `stopped` | the API agent is not loaded | warning triangle |
| `wedged` | the API agent is loaded and the health route does not answer | warning triangle |
| `up` | none of the above | `batteryblock.stack`, dimmed if the front end does not answer |

The menu, top to bottom:

- One row naming the state. When up it reads `lab up at <build>`.
- A row saying the front end is not answering, when it is not.
- A link to each page: the lab, Review, Wall, Corpus, Stats, Ingest. Shown
  only while the front end answers.
- Restart the API, Cycle the lab, Start or Stop the lab, Open the log.
- Quit.

Restart the API uses perch's own agent restart, which boots the agent out and
back in. The others run `brick-lab`.

## Left out

- **A count of pending reviews on the icon.** `/api/review` builds an entry
  for every row in the review table on each call. It needs a cheap count route
  first.
- **Fleet and census state.** onto's menu bar item shows jobs.

## Checks

- A pytest for `/api/health`: the shape, and that it answers with no
  `corpus.db` present.
- `perch build`, which type-checks what it emits with `swiftc`.
- By hand: `scripts/lab-agents.sh install`, then `stat` shows both agents
  running and both ports answering; `perch run` to read the menu in each
  state (stop the API to see `wedged`); then `perch install`.
