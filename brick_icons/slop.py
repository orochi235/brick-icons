"""Put renders on the slopboard wall and read a verdict back.

A sweep of sixty parts is sixty questions, and sixty cards on the wall would
bury every other zone on it. So a review goes up as a **run**: one card holding
a take per render, which the wall opens as a carousel with the verdicts as chips
under each picture. `slop --run <id>` is the whole of that protocol; see
slopboard's `DESIGN.md` under "Runs: many pictures, one card".

Nothing here writes a verdict anywhere. `review` hands back what the wall was
told and the caller decides -- deliberately, because this repo already has a
review pipeline with a home for one (`review.record_judged`, whose `verdict` and
`note` are this module's `choice` and `text`, and whose vocabulary is these five
under one different name: `worse` is its `regression`). Wiring the two together
is a rename rather than a redesign, and it is not this module's call to make.

Not `review.py`: that name is taken by the displacement queue the lab's /review
page reads.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

#: What the wall offers for a render being compared against an earlier one.
#: Named outcomes drawn in this order, not points on a scale: nothing ranks
#: them, nothing averages them, and the caller branches on the exact string.
VERDICTS = ("no change", "worse", "neutral", "better", "fixed")

#: For a first look, where there is nothing to compare against and so no
#: "no change" to report.
FIRST_LOOK = ("keep", "redo")

#: What the wall holds. A `.svg` is not on it, so a run of traced outlines has
#: nothing to show -- which the caller is told rather than left to wonder about.
#: slopboard's `server/kind.ts` is the list this mirrors.
HELD = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".tiff",
        ".mp4", ".m4v", ".mov", ".webm", ".glb", ".stl", ".html", ".htm"}

#: Where a run's takes are written down, so a verdict collected an hour later
#: still knows which part it is about. Bounded by `_prune`: the manifests are a
#: convenience, and an unbounded directory of them is a slow leak.
RUNS_DIR = Path(".cache") / "slop-runs"
RUNS_KEPT = 10


def slop_bin() -> Path:
    """The `slop` to shell. `SLOP_BIN` first so a test can stand in for it."""
    env = os.environ.get("SLOP_BIN")
    if env:
        return Path(env)
    found = shutil.which("slop")
    if found:
        return Path(found)
    return Path.home() / "src" / "slopboard" / "bin" / "slop"


def answers_dir() -> Path:
    return Path(os.environ.get("SLOP_ROOT", Path.home() / "slop")) / "answers"


def run_id(prefix: str = "review") -> str:
    """A name for one run. The date is in it so a manifest left behind says
    when it was made without being opened."""
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


@dataclass(frozen=True)
class Sent:
    """A take on the wall: the file it was made from, and the copy in the inbox
    whose name the answer will be filed under."""
    path: Path
    dest: Path
    #: What the caller is reviewing -- a part id, usually. Carried so a verdict
    #: can be reported against the thing rather than against a UUID.
    about: str


@dataclass(frozen=True)
class Verdict:
    """What the wall was told. `choice` is the chip and `text` the comment box;
    a take dropped without a verdict has neither and `status` says so."""
    about: str
    path: Path
    status: str
    choice: str | None
    text: str

    @property
    def answered(self) -> bool:
        return self.status == "answered"


def holdable(path: Path) -> bool:
    return path.suffix.lower() in HELD


def send(path: Path | str, *, about: str | None = None, run: str | None = None,
         question: str | None = None, choices=VERDICTS, why: str | None = None,
         of: int | None = None, label: str | None = None, zone: str | None = None,
         apps=(), links=(), attention: str | None = None,
         caption: str | None = None) -> Sent:
    """Puts one file on the wall and returns where it landed, without waiting.

    `why` is the placeholder for the comment box beside the chips; None offers
    no box. `apps` are `"Name"` or `"Name=path"` and `links` are `"url"` or
    `"label=url"`, both as `bin/slop` takes them.
    """
    path = Path(path)
    if not holdable(path):
        raise ValueError(f"the wall does not hold {path.suffix}: {path}")
    argv: list[str] = [str(slop_bin())]
    if zone:
        argv += ["--zone", zone]
    if run:
        argv += ["--run", run]
    if label:
        argv += ["--run-label", label]
    if of is not None:
        argv += ["--of", str(of)]
    if caption:
        argv += ["--caption", caption]
    if attention:
        argv += ["--attention", attention]
    if question:
        argv += ["--ask", question]
        for choice in choices or ():
            argv += ["--choice", choice]
        if why is not None:
            argv += ["--why", why]
        # The wall answers per take and this returns rather than blocking, so
        # the caller collects on its own schedule -- which is what lets a sweep
        # keep rendering while the first takes are being looked at.
        argv += ["--no-wait"]
    for app in apps:
        argv += ["--app", app]
    for link in links:
        argv += ["--link", link]
    argv += [str(path)]
    out = subprocess.run(argv, capture_output=True, text=True, check=True)
    dest = out.stdout.strip().splitlines()
    if not dest:
        raise RuntimeError(f"slop said nothing about {path}: {out.stderr}")
    return Sent(path=path, dest=Path(dest[-1]), about=about or path.stem)


def _parse_answer(blob: str) -> tuple[str, str | None, str]:
    """The answer file: the status, then the chip, then the text from line 3.
    A blank second line is what keeps a free-text answer's first line from
    being read as a choice."""
    lines = blob.split("\n")
    status = lines[0].strip() if lines else ""
    choice = lines[1].strip() if len(lines) > 1 else ""
    return status, choice or None, "\n".join(lines[2:])


def collect(sent: Sent, *, timeout: float | None = None,
            poll: float = 0.5) -> Verdict | None:
    """Waits for one take's verdict. None on timeout, so a caller that gave up
    can say which takes were never looked at rather than hanging on them.

    The answer file is read and removed, which is also what bounds the answers
    directory -- nothing else ever cleans it.
    """
    answer = answers_dir() / sent.dest.name
    deadline = None if timeout is None else time.monotonic() + timeout
    while not answer.exists():
        if deadline is not None and time.monotonic() > deadline:
            return None
        time.sleep(poll)
    blob = answer.read_text()
    answer.unlink(missing_ok=True)
    status, choice, text = _parse_answer(blob)
    return Verdict(about=sent.about, path=sent.path, status=status,
                   choice=choice, text=text)


def review(path: Path | str, *, question: str, about: str | None = None,
           choices=VERDICTS, why: str | None = None, run: str | None = None,
           timeout: float | None = None, **kw) -> Verdict | None:
    """One render, one verdict, blocking until it comes back.

    For a caller that wants to stop at the first bad one. A sweep wants
    `review_many`, which sends every take before waiting on any of them.
    """
    sent = send(path, about=about, run=run or run_id(), question=question,
                choices=choices, why=why, **kw)
    return collect(sent, timeout=timeout)


def review_many(paths, *, question: str, about=None, choices=VERDICTS,
                why: str | None = None, run: str | None = None,
                label: str | None = None, timeout: float | None = None,
                root: Path | str = ".", **kw) -> list[Verdict]:
    """A whole sweep as one run: every take goes up, then the verdicts come
    back as they are given.

    `about` is a name per path, in the same order, for reporting a verdict
    against the part rather than the file. `root` is where the manifest goes,
    and it defaults to the working directory rather than being derived: a
    caller that renders into someone else's tree must not leave a manifest in
    this one.
    """
    paths = [Path(p) for p in paths]
    names = list(about or [p.stem for p in paths])
    run = run or run_id()
    sent = [
        send(p, about=n, run=run, question=question, choices=choices, why=why,
             of=len(paths), label=label, **kw)
        for p, n in zip(paths, names)
    ]
    write_manifest(run, sent, root=root)
    print(f"{len(sent)} on the wall as {run}; waiting on verdicts", flush=True)
    out = []
    for n, one in enumerate(sent, 1):
        verdict = collect(one, timeout=timeout)
        if verdict is None:
            print(f"[{n}/{len(sent)}] {one.about}: not looked at", flush=True)
            continue
        said = verdict.choice or verdict.status
        note = f" -- {verdict.text}" if verdict.text else ""
        print(f"[{n}/{len(sent)}] {one.about}: {said}{note}", flush=True)
        out.append(verdict)
    return out


def write_manifest(run: str, sent: list[Sent], root: Path | str = ".") -> Path:
    """Records what a run's takes are about, for a verdict collected later.

    Pruning on write is what bounds the directory: the manifests exist so that
    `collect_run` has something to resolve against, and one per sweep forever
    is a leak nobody would notice until the disk did.
    """
    out = Path(root) / RUNS_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{run}.json"
    path.write_text(json.dumps({
        "run": run,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "takes": [{"about": s.about, "path": str(s.path), "dest": str(s.dest)}
                  for s in sent],
    }, indent=1) + "\n")
    _prune(out)
    return path


def _prune(dir: Path, keep: int = RUNS_KEPT) -> list[Path]:
    """Drops all but the newest `keep` manifests. Returns what went."""
    held = sorted(dir.glob("*.json"), key=lambda p: p.stat().st_mtime,
                  reverse=True)
    gone = held[keep:]
    for path in gone:
        path.unlink(missing_ok=True)
    return gone


def load_manifest(run: str, root: Path | str = ".") -> list[Sent]:
    blob = json.loads((Path(root) / RUNS_DIR / f"{run}.json").read_text())
    return [Sent(path=Path(t["path"]), dest=Path(t["dest"]), about=t["about"])
            for t in blob["takes"]]


def collect_run(run: str, root: Path | str = ".",
                timeout: float | None = 0) -> list[Verdict]:
    """The verdicts a run has been given so far.

    The default timeout is zero rather than None: a run collected after the
    fact is being asked what has been answered, not asked to wait for the rest.
    """
    out = []
    takes = load_manifest(run, root)
    for n, one in enumerate(takes, 1):
        verdict = collect(one, timeout=timeout)
        state = "not looked at" if verdict is None else (verdict.choice or verdict.status)
        print(f"[{n}/{len(takes)}] {one.about}: {state}", flush=True)
        if verdict is not None:
            out.append(verdict)
    return out


def runs(root: Path | str = ".") -> list[str]:
    """The runs with a manifest still on disk, newest first."""
    dir = Path(root) / RUNS_DIR
    if not dir.is_dir():
        return []
    return [p.stem for p in sorted(dir.glob("*.json"),
                                   key=lambda p: p.stat().st_mtime,
                                   reverse=True)]
