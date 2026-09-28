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


def test_install_refuses_a_checkout_without_node_modules(home):
    tmp_path, env = home
    main = tmp_path / "main"
    (main / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, main / "scripts" / "lab-agents.sh")
    subprocess.run(["git", "init", "-b", "main", str(main)],
                   check=True, capture_output=True)
    got = run(main / "scripts" / "lab-agents.sh", "install", env)
    assert got.returncode == 1
    assert "npm ci" in got.stderr
    assert not (tmp_path / "agents").exists()


def test_an_unknown_verb_is_an_error(home):
    _tmp_path, env = home
    got = run(SCRIPT, "frobnicate", env)
    assert got.returncode == 1
    assert "no such command: frobnicate" in got.stderr
