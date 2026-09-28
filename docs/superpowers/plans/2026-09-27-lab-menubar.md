# Lab Menu Bar Item Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: not started.** Spec: `docs/superpowers/specs/2026-09-27-lab-menubar-design.md`.
`menubar.yaml` and `menubar.schema.json` already exist at the repo root, uncommitted.

**Goal:** Run the lab's two processes under launchd, and give them a menu bar item that says whether they are up, opens the lab's pages, and starts and stops them.

**Architecture:** `scripts/lab-agents.sh` writes two launchd agents and drives them, and is linked onto PATH as `brick-lab`. The lab API gains a cheap `/api/health` route and a `--quiet` flag. `menubar.yaml` is compiled by perch (a generator that turns that file into a macOS status-bar app) into Swift under `menubar/Generated/`, which is committed.

**Tech Stack:** POSIX sh and launchd, FastAPI and uvicorn, pytest, perch.

**Running tests.** From the main checkout: `.venv/bin/python -m pytest <file> -q`. A linked worktree has no `.venv` and would import the main checkout's code, so there use:

```bash
PYTHONPATH=$PWD /Users/mike/src/brick-icons/.venv/bin/python -m pytest <file> -q -p no:cacheprovider
```

Every `pytest` command below is written the first way.

## Files

| File | Responsibility |
|---|---|
| `brick_icons/lab/app.py` | Modify: add `GET /api/health` |
| `brick_icons/lab/__main__.py` | Modify: add `--quiet` |
| `tests/test_lab_app.py` | Modify: health route tests |
| `tests/test_lab_main.py` | Create: `--quiet` tests |
| `scripts/lab-agents.sh` | Create: the agents, and the verbs that drive them |
| `tests/test_lab_agents.py` | Create: what the script writes, and what it refuses |
| `menubar.yaml`, `menubar.schema.json` | Exist: commit |
| `menubar/Generated/*.swift` | Create: emitted by `perch build`, committed |
| `DEVELOPING.md` | Modify: "The lab" says how it runs under launchd |

---

### Task 1: `GET /api/health`

**Files:**
- Modify: `brick_icons/lab/app.py` (inside `create_app`, directly above `@app.get("/api/schema")`)
- Test: `tests/test_lab_app.py`

- [ ] **Step 1: Write the failing tests**

Add after `test_unknown_route_is_404` in `tests/test_lab_app.py`:

```python
def test_health_names_the_build_the_server_loaded(client):
    import brick_icons
    assert client.get("/api/health").json() == {
        "ok": True, "build": brick_icons.build()}


def test_health_answers_without_a_corpus_database(tmp_path):
    absent = tmp_path / "absent.db"
    client = TestClient(lab_app.create_app(cache_root=tmp_path,
                                           corpus_db=absent))
    assert client.get("/api/health").status_code == 200
    assert not absent.exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lab_app.py -q -k health`
Expected: 2 failed, each with a 404 (`KeyError` or `assert 404 == 200`).

- [ ] **Step 3: Add the route**

In `brick_icons/lab/app.py`, directly above `@app.get("/api/schema")`. `build` is already imported at the top of the file (`from .. import build`):

```python
    @app.get("/api/health")
    def get_health():
        return {"ok": True, "build": build()}

```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_app.py -q -k health`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "add /api/health to the lab, naming the build the server loaded"
```

---

### Task 2: `--quiet`

**Files:**
- Modify: `brick_icons/lab/__main__.py`
- Test: `tests/test_lab_main.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_main.py`:

```python
import pytest

from brick_icons.lab import __main__ as lab_main


@pytest.fixture
def ran(monkeypatch):
    """What `main` handed uvicorn, with no server started."""
    seen = {}
    monkeypatch.setattr(lab_main.uvicorn, "run",
                        lambda *a, **k: seen.update(k))
    monkeypatch.setattr(lab_main, "create_app", lambda root: object())
    return seen


def test_requests_are_logged_by_default(ran):
    assert lab_main.main([]) == 0
    assert ran["access_log"] is True


def test_quiet_leaves_requests_out_of_the_log(ran):
    assert lab_main.main(["--quiet"]) == 0
    assert ran["access_log"] is False


def test_quiet_holds_under_reload(ran):
    assert lab_main.main(["--reload", "--quiet"]) == 0
    assert ran["access_log"] is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lab_main.py -q`
Expected: 3 failed. The first with `KeyError: 'access_log'`, the other two with `SystemExit: 2` (unrecognized argument).

- [ ] **Step 3: Add the flag**

In `brick_icons/lab/__main__.py`, add after the `--reload` argument:

```python
    p.add_argument("--quiet", action="store_true",
                   help="leave requests out of the log")
```

and pass `access_log=not args.quiet` to both `uvicorn.run` calls:

```python
        uvicorn.run("brick_icons.lab.__main__:_factory", factory=True, reload=True,
                    reload_dirs=["brick_icons"], host=args.host, port=args.port,
                    access_log=not args.quiet,
                    timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
    else:
        uvicorn.run(create_app(root=args.root), host=args.host, port=args.port,
                    access_log=not args.quiet,
                    timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_main.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/__main__.py tests/test_lab_main.py
git commit -m "add --quiet to the lab server, which leaves requests out of the log"
```

---

### Task 3: `scripts/lab-agents.sh`

Every directory the script writes to can be moved by an environment variable, which is what lets a test run it without touching the real `~/Library/LaunchAgents`. `plists` writes the agents and calls `launchctl` for nothing, so it is the verb the tests use.

**Files:**
- Create: `scripts/lab-agents.sh`
- Test: `tests/test_lab_agents.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lab_agents.py`:

```python
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "lab-agents.sh"
API = "tech.michaelbaker.brick-icons.lab-api"
FRONT = "tech.michaelbaker.brick-icons.lab-front"


@pytest.fixture
def home(tmp_path):
    """Somewhere for the script to write, and a `node` for it to find."""
    fake = tmp_path / "nodebin"
    fake.mkdir()
    (fake / "node").write_text("#!/bin/sh\n")
    (fake / "node").chmod(0o755)
    env = {**os.environ,
           "BRICK_LAB_STATE": str(tmp_path / "state"),
           "BRICK_LAB_AGENTS": str(tmp_path / "agents"),
           "BRICK_LAB_BIN": str(tmp_path / "bin"),
           "PATH": f"{fake}:/usr/bin:/bin"}
    return tmp_path, env


def run(script, verb, env):
    return subprocess.run(["sh", str(script), verb], env=env,
                          capture_output=True, text=True)


def agent(tmp_path, label):
    return plistlib.loads((tmp_path / "agents" / f"{label}.plist").read_bytes())


def test_plists_writes_the_api_agent(home):
    tmp_path, env = home
    assert run(SCRIPT, "plists", env).returncode == 0
    api = agent(tmp_path, API)
    assert api["Label"] == API
    assert api["ProgramArguments"] == [
        str(REPO / ".venv" / "bin" / "python"), "-m", "brick_icons.lab",
        "--reload", "--quiet"]
    assert api["WorkingDirectory"] == str(REPO)
    assert api["KeepAlive"] is True and api["RunAtLoad"] is True
    assert api["StandardOutPath"] == str(tmp_path / "state" / "lab-api.log")


def test_plists_writes_the_front_agent_with_node_on_its_path(home):
    tmp_path, env = home
    assert run(SCRIPT, "plists", env).returncode == 0
    front = agent(tmp_path, FRONT)
    assert front["ProgramArguments"] == [
        str(REPO / "lab" / "node_modules" / ".bin" / "vite")]
    assert front["WorkingDirectory"] == str(REPO / "lab")
    assert front["EnvironmentVariables"]["PATH"].startswith(
        str(tmp_path / "nodebin") + ":")


def test_the_repo_is_found_through_the_link_the_menu_runs(home):
    tmp_path, env = home
    link = tmp_path / "bin" / "brick-lab"
    link.parent.mkdir()
    link.symlink_to(SCRIPT)
    assert run(link, "plists", env).returncode == 0
    assert agent(tmp_path, API)["WorkingDirectory"] == str(REPO)


def test_install_refuses_a_linked_worktree(home):
    tmp_path, env = home
    main = tmp_path / "main"
    (main / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, main / "scripts" / "lab-agents.sh")

    def git(*args):
        subprocess.run(["git", "-C", str(main), "-c", "user.name=t",
                        "-c", "user.email=t@example.com", *args],
                       check=True, capture_output=True)

    git("init", "-b", "main")
    git("add", ".")
    git("commit", "-m", "the script")
    git("worktree", "add", str(tmp_path / "linked"))
    got = run(tmp_path / "linked" / "scripts" / "lab-agents.sh", "install", env)
    assert got.returncode == 1
    assert "worktree" in got.stderr
    assert not (tmp_path / "agents").exists()


def test_an_unknown_verb_is_an_error(home):
    _tmp_path, env = home
    got = run(SCRIPT, "frobnicate", env)
    assert got.returncode == 1
    assert "no such command: frobnicate" in got.stderr
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lab_agents.py -q`
Expected: 5 failed. `sh` cannot open `scripts/lab-agents.sh`, so every `returncode` is 127 or 2 and `test_install_refuses_a_linked_worktree` fails inside `shutil.copy` with `FileNotFoundError`.

- [ ] **Step 3: Write the script**

Create `scripts/lab-agents.sh`. The plist body is indented with tabs:

```sh
#!/bin/sh
# Run the lab as a pair of launchd agents, so it outlives the terminal.
# `install` links this onto PATH as `brick-lab`, the name menubar.yaml runs.
#
#   brick-lab install           write both agents, link this script, start them
#   brick-lab up | down | cycle start, stop or restart them
#   brick-lab stat              what launchd thinks, and whether each answers
#   brick-lab log               open the log directory
#   brick-lab plists            write the agents and start nothing
set -eu

# $0 is the link in ~/.local/bin when the menu bar runs this.
self=$0
while [ -L "$self" ]; do
  target=$(readlink "$self")
  case $target in
    /*) self=$target ;;
    *) self=$(dirname -- "$self")/$target ;;
  esac
done
repo=$(CDPATH= cd -- "$(dirname -- "$self")/.." && pwd)

state=${BRICK_LAB_STATE:-$HOME/.local/state/brick-icons}
agents=${BRICK_LAB_AGENTS:-$HOME/Library/LaunchAgents}
bin=${BRICK_LAB_BIN:-$HOME/.local/bin}
domain="gui/$(id -u)"
base=tech.michaelbaker.brick-icons
# The defaults in brick_icons/lab/__main__.py and lab/vite.config.ts, which a
# shell script cannot import.
api_port=8792
front_port=5178

plist() { # label, working directory, program arguments, log
  cat > "$agents/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$1</string>
	<key>ProgramArguments</key>
	<array>
$3
	</array>
	<key>WorkingDirectory</key>
	<string>$2</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>$nodedir:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
	</dict>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>StandardOutPath</key>
	<string>$state/$4.log</string>
	<key>StandardErrorPath</key>
	<string>$state/$4.log</string>
</dict>
</plist>
PLIST
}

write() {
  # launchd starts with almost no PATH, and vite is a node shebang.
  node=$(command -v node) || {
    echo "brick-lab: node is not on PATH, and vite needs it" >&2
    exit 1
  }
  nodedir=$(dirname -- "$node")
  mkdir -p "$state" "$agents"
  plist "$base.lab-api" "$repo" "		<string>$repo/.venv/bin/python</string>
		<string>-m</string>
		<string>brick_icons.lab</string>
		<string>--reload</string>
		<string>--quiet</string>" lab-api
  plist "$base.lab-front" "$repo/lab" \
    "		<string>$repo/lab/node_modules/.bin/vite</string>" lab-front
}

linked() {
  [ "$(git -C "$repo" rev-parse --git-dir)" != \
    "$(git -C "$repo" rev-parse --git-common-dir)" ]
}

fresh() {
  mkdir -p "$state"
  : > "$state/lab-api.log"
  : > "$state/lab-front.log"
}

free() { # port
  pids=$(lsof -ti "tcp:$1" 2>/dev/null || true)
  # shellcheck disable=SC2086
  [ -z "$pids" ] || kill $pids 2>/dev/null || true
}

each() { for label in "$base.lab-api" "$base.lab-front"; do "$1" "$label"; done; }
boot() { launchctl bootstrap "$domain" "$agents/$1.plist" 2>/dev/null || true; }
# bootout returns before launchd has let go of the label, and a bootstrap in
# that window fails and leaves nothing loaded.
unboot() {
  launchctl bootout "$domain/$1" 2>/dev/null || true
  tries=0
  while launchctl print "$domain/$1" >/dev/null 2>&1 && [ $tries -lt 50 ]; do
    sleep 0.1
    tries=$((tries + 1))
  done
}
kick() { launchctl kickstart -k "$domain/$1" >/dev/null 2>&1 || true; }

answers() { # url
  curl -s -m 2 -o /dev/null -w '%{http_code}' "$1" || echo no
}

case "${1:-stat}" in
  install)
    if linked; then
      echo "brick-lab: $repo is a linked worktree; install from the main checkout, or the agents die with the worktree" >&2
      exit 1
    fi
    write
    mkdir -p "$bin"
    ln -sf "$repo/scripts/lab-agents.sh" "$bin/brick-lab"
    each unboot
    # A lab started by hand holds the port, the agent exits on start, and
    # KeepAlive turns that into a restart loop rather than an error.
    free "$api_port"
    free "$front_port"
    fresh
    each boot
    echo "installed: $base.lab-api, $base.lab-front"
    ;;
  plists) write ;;
  up)     fresh; each boot ;;
  down)   each unboot ;;
  cycle)  fresh; each kick ;;
  log)    open "$state" ;;
  stat)
    for label in "$base.lab-api" "$base.lab-front"; do
      printf '%-45s %s\n' "$label" \
        "$(launchctl print "$domain/$label" 2>/dev/null | awk '/^\tstate = /{print $3; found=1; exit} END{if (!found) print "not loaded"}')"
    done
    printf '%-45s %s\n' 'api answers' "$(answers "http://127.0.0.1:$api_port/api/health")"
    printf '%-45s %s\n' 'front answers' "$(answers "http://localhost:$front_port/")"
    ;;
  *) echo "brick-lab: no such command: $1" >&2; exit 1 ;;
esac
```

Then make it executable:

```bash
chmod +x scripts/lab-agents.sh
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lab_agents.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/lab-agents.sh tests/test_lab_agents.py
git commit -m "add lab-agents.sh, which runs the lab's API and front end under launchd"
```

---

### Task 4: Emit the menu bar app's Swift

`menubar.yaml` reads `/api/health` (Task 1) and runs `brick-lab` (Task 3), so it goes in after both.

**Files:**
- Commit: `menubar.yaml`, `menubar.schema.json`
- Create: `menubar/Generated/main.swift`, `Render.swift`, `Runtime.swift`, `Shapes.swift`

- [ ] **Step 1: Build**

Run: `perch build`
Expected:

```
  menubar/Generated/Runtime.swift
  menubar/Generated/Shapes.swift
  menubar/Generated/Render.swift
  menubar/Generated/main.swift
built brick-icons
```

A bad condition or a field the `shape:` does not declare fails here, naming the line in `menubar.yaml`.

- [ ] **Step 2: Confirm nothing else was written**

Run: `git status --short`
Expected: only `menubar.yaml`, `menubar.schema.json` and `menubar/` are untracked.

- [ ] **Step 3: Commit**

```bash
git add menubar.yaml menubar.schema.json menubar/Generated
git commit -m "add the lab's menu bar item: menubar.yaml and the Swift perch emits from it"
```

---

### Task 5: Say how the lab runs now

**Files:**
- Modify: `DEVELOPING.md`, section "The lab"

- [ ] **Step 1: Add the launchd path**

In `DEVELOPING.md`, directly after the block ending `cd lab && npm run dev          # :5178`, add:

````markdown
Or hand both to launchd, which keeps them up and restarts the API when
`brick_icons/` changes:

    scripts/lab-agents.sh install     # from the main checkout, once
    brick-lab stat | up | down | cycle | log

`perch install` adds the menu bar item that drives the same verbs, from
`menubar.yaml`. Logs are in `~/.local/state/brick-icons/` and are emptied on
every `up`, `cycle` and `install`. A lab started by hand on 8792 or 5178 is
stopped by `install`; a worktree that wants its own lab still starts one by
hand on another port.
````

- [ ] **Step 2: Commit**

```bash
git add DEVELOPING.md
git commit -m "say in DEVELOPING.md how the lab runs under launchd"
```

---

### Task 6: Install and look at it

This task runs **from the main checkout, after the branch is merged**: `install` refuses a linked worktree.

- [ ] **Step 1: Install the agents**

Run: `scripts/lab-agents.sh install`
Expected: `installed: tech.michaelbaker.brick-icons.lab-api, tech.michaelbaker.brick-icons.lab-front`

- [ ] **Step 2: Check both are up**

Run: `brick-lab stat` (wait about ten seconds after install; the API imports OCCT)
Expected:

```
tech.michaelbaker.brick-icons.lab-api         running
tech.michaelbaker.brick-icons.lab-front       running
api answers                                   200
front answers                                 200
```

If `api answers` is `000`, read `~/.local/state/brick-icons/lab-api.log`.

- [ ] **Step 3: Read the menu in each state**

Run: `perch run`, and click the item. Expected: the top row reads `lab up at <build>` and the six page links are present.

Then, in another terminal, `brick-lab down`. Within five seconds the icon becomes a warning triangle, the top row reads `lab not loaded`, the page links are gone and `Start the lab` replaces `Stop the lab`. `brick-lab up` brings it back. Stop `perch run` with Ctrl-C.

- [ ] **Step 4: Install the menu bar item**

Run: `perch install`
Expected: the item appears in the menu bar and survives closing the terminal.

- [ ] **Step 5: Run the full suite on the fleet**

Run: `onto test > /tmp/lab-menubar-suite.txt 2>&1; echo $?`
Expected: the two failures already recorded in `HANDOFF.md` (`test_lab_review` and `test_occt`'s sticker test) and no others.

---

### Task 7: Close out

- [ ] **Step 1: Mark the spec built**

In `docs/superpowers/specs/2026-09-27-lab-menubar-design.md`, replace the `**Status: not built.**` paragraph with:

```markdown
**Status: built.** `scripts/lab-agents.sh`, `menubar.yaml`, and
`/api/health` in `brick_icons/lab/app.py`.
```

- [ ] **Step 2: Update the projects index**

In `~/src/PROJECTS.md`, in the **brick-icons** entry, add: `The lab runs under launchd (scripts/lab-agents.sh, on PATH as brick-lab) with a menu bar item generated by perch from menubar.yaml.` In the **perch** entry, change `Consumed by onto, transom and brainhouse` to `Consumed by onto, transom, brainhouse and brick-icons`.

- [ ] **Step 3: Delete this plan and commit**

```bash
git rm docs/superpowers/plans/2026-09-27-lab-menubar.md
git add docs/superpowers/specs/2026-09-27-lab-menubar-design.md
git commit -m "mark the lab menu bar item built, and drop its plan"
```
