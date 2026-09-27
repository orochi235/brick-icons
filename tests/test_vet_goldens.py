import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _vg():
    spec = importlib.util.spec_from_file_location(
        "vet_goldens", ROOT / "scripts" / "vet-goldens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_appends_the_side_s_extra_flags_before_out(tmp_path, monkeypatch):
    vg = _vg()
    seen = {}

    class Done:
        returncode, stderr, stdout = 1, "boom", ""

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return Done()
    monkeypatch.setattr(vg.subprocess, "run", fake)
    case = {"id": "3001", "part": "3001", "args": ["--shading", "outline"]}
    png, err, _ = vg.render(case, tmp_path, "occt", tmp_path, 64,
                            extra=["--stud-instancing", "all"])
    assert png is None and err == "boom"
    assert seen["cmd"][-4:-2] == ["--stud-instancing", "all"]
    assert seen["cmd"][-2] == "--out"


def test_after_args_without_a_base_draws_both_sides_from_this_tree(
        tmp_path, monkeypatch):
    vg = _vg()
    seen = []

    def fake(case, tree, engine, dest, width, timeout=None, extra=()):
        seen.append((tree, list(extra)))
        return None, "stubbed", 0.0
    monkeypatch.setattr(vg, "render", fake)
    monkeypatch.setattr(vg, "ROOT", tmp_path)
    monkeypatch.setattr(vg, "VET_DIR", tmp_path / "out" / "vet")
    monkeypatch.setattr(vg, "make_base_tree", lambda *a: 1 / 0)
    monkeypatch.setattr(vg.shutil, "which", lambda name: name)
    assert vg.main(["--here", "--parts", "3001,", "--label", "t",
                    "--after-args=--stud-instancing all"]) == 0
    assert seen == [(tmp_path, []),
                    (tmp_path, ["--stud-instancing", "all"])]
