"""The spot worker's service command: what onto runs after every roll."""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "spot-worker.sh"


def _tree(tmp_path, ldraw=True):
    """A copy of the script in a tree with a fake uv and a fake python that
    record how they were called."""
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, tree / "scripts" / "spot-worker.sh")
    if ldraw:
        (tree / "vendor" / "ldraw" / "parts").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    uv = home / ".local" / "bin" / "uv"
    uv.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/uv\n")
    uv.chmod(0o755)
    py = tree / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/python\n")
    py.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"}
    return tree, env


def test_it_syncs_the_environment_then_starts_the_worker(tmp_path):
    tree, env = _tree(tmp_path)
    got = subprocess.run(["bash", str(tree / "scripts" / "spot-worker.sh")],
                         env=env, capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
    assert (tmp_path / "uv").read_text().split() == [
        "sync", "--frozen", "--extra", "occt", "--extra", "census",
        "--extra", "lab"]
    assert (tmp_path / "python").read_text().split() == [
        "-m", "brick_icons.spot_worker"]
    assert got.stdout == ""


def test_a_tree_without_the_parts_library_is_refused(tmp_path):
    tree, env = _tree(tmp_path, ldraw=False)
    got = subprocess.run(["bash", str(tree / "scripts" / "spot-worker.sh")],
                         env=env, capture_output=True, text=True)
    assert got.returncode == 1
    assert "vendor/ldraw" in got.stderr
    assert not (tmp_path / "python").exists()
