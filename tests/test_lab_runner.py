"""A lab render is the CLI's render: same parser, same Config, same
process_one. Anything else and the app drifts from the command line."""
import pytest

from brick_icons.lab import runner


def test_runs_and_writes_an_svg(tmp_path, ldraw_dir):
    result = runner.render(["3005", "--format", "svg", "--shading", "outline"],
                           root=tmp_path)
    assert result["ok"]
    assert "3005.svg" in {a["name"] for a in result["artifacts"]}
    assert result["seconds"] > 0


def test_reports_the_argv_it_actually_ran(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    result = runner.render(argv, root=tmp_path)
    assert result["argv"] == argv
    assert result["command"].startswith("brick-icons 3005 ")


def test_second_run_is_served_from_cache(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    first = runner.render(argv, root=tmp_path)
    second = runner.render(argv, root=tmp_path)
    assert first["cached"] is False
    assert second["cached"] is True


def test_force_reruns_a_cached_render(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    runner.render(argv, root=tmp_path)
    again = runner.render(argv, root=tmp_path, force=True)
    assert again["cached"] is False


def test_a_bad_flag_is_an_error_not_a_crash(tmp_path):
    result = runner.render(["3005", "--nonsense"], root=tmp_path)
    assert result["ok"] is False
    assert "nonsense" in result["error"]


def test_a_missing_part_is_an_error(tmp_path, ldraw_dir):
    result = runner.render(["definitely-not-a-part"], root=tmp_path)
    assert result["ok"] is False
    assert result["error"]
