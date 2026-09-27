import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "stud_ab_timing", ROOT / "scripts" / "stud-ab-timing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rows_are_medians_of_interleaved_draws(tmp_path, monkeypatch):
    mod = _mod()
    calls = []

    def fake(part, mode, a, out):
        calls.append(mode)
        return (2.0 if mode == "off" else 1.0), {"studs_clear": 8, "faces_healed": 1}
    monkeypatch.setattr(mod, "draw", fake)
    sink = tmp_path / "t.jsonl"
    assert mod.main(["3001", "--reps", "1", "--jsonl", str(sink)]) == 0
    assert calls == ["off", "off", "all", "all", "off"]      # warm-up, then ABBA
    row = json.loads(sink.read_text())
    assert (row["off"], row["all"], row["ratio"]) == (2.0, 1.0, 0.5)
    assert row["counts"] == {"studs_clear": 8}


def test_a_zero_off_time_prints_a_row_without_a_ratio(tmp_path, monkeypatch, capsys):
    mod = _mod()
    monkeypatch.setattr(mod, "draw", lambda part, mode, a, out: (0.0, {}))
    sink = tmp_path / "t.jsonl"
    assert mod.main(["3001", "--reps", "1", "--jsonl", str(sink)]) == 0
    assert json.loads(sink.read_text())["ratio"] is None
    header, line = capsys.readouterr().out.splitlines()
    assert len(line.rstrip()) == len(header.rstrip()) - len("  studs")
