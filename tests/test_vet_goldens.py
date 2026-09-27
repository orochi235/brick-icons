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
