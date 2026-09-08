"""How a part is built, from its .dat and the subfiles it resolves to."""
import numpy as np
import pytest

from brick_icons import features


def write(tmp_path, name, body):
    path = tmp_path / "p" / f"{name}.dat"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def extract(tmp_path, name, body):
    write(tmp_path, name, body)
    ex = features.Extractor([tmp_path / "p", tmp_path / "parts"])
    return ex.extract(tmp_path / "p" / f"{name}.dat")


#: `x y z` then the 3x3 row by row -- twelve numbers, not nine.
IDENTITY = "0 0 0  1 0 0  0 1 0  0 0 1"


def test_a_fraction_prefix_is_what_separates_a_cone_from_a_connector():
    assert features.family("4-4con3.dat") == "cone"
    assert features.family("connect.dat") is None
    assert features.family("confric.dat") is None
    assert features.family("p/48/4-4cyli.dat") == "cylinder"
    assert features.family("t04o1234.dat") == "torus"
    assert features.family("3001.dat") is None


def test_a_part_reports_the_families_below_it_not_just_its_own_line(tmp_path):
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    write(tmp_path, "stud", f"0 Stud\n1 16 {IDENTITY} 4-4cyli.dat\n")
    got = extract(tmp_path, "brick", f"0 Brick\n1 16 {IDENTITY} stud.dat\n")
    assert "cylinder" in got and "stud" in got and "round" in got


def test_a_turned_cylinder_is_off_axis_and_a_squared_one_is_not(tmp_path):
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    upright = extract(tmp_path, "a", f"0 A\n1 16 {IDENTITY} 4-4cyli.dat\n")
    assert "off-axis" not in upright
    # Lying on its side: still a world axis, so still not off-axis.
    lying = extract(tmp_path, "b",
                    "0 B\n1 16 0 0 0  0 1 0  -1 0 0  0 0 1 4-4cyli.dat\n")
    assert "off-axis" not in lying
    tilted = extract(tmp_path, "c",
                     "0 C\n1 16 0 0 0  1 0 0  0 0.7 0.7  0 -0.7 0.7 4-4cyli.dat\n")
    assert "off-axis" in tilted


def test_an_unevenly_scaled_circle_is_elliptical(tmp_path):
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    round_ = extract(tmp_path, "a",
                     "0 A\n1 16 0 0 0  3 0 0  0 1 0  0 0 3 4-4cyli.dat\n")
    assert "elliptical" not in round_
    squashed = extract(tmp_path, "b",
                       "0 B\n1 16 0 0 0  3 0 0  0 1 0  0 0 1 4-4cyli.dat\n")
    assert "elliptical" in squashed


def test_scale_reaches_a_primitive_through_its_parent(tmp_path):
    """The composed matrix decides, not the reference that names the file: a
    stud drawn round is elliptical if whatever holds it is squashed."""
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    write(tmp_path, "stud", f"0 Stud\n1 16 {IDENTITY} 4-4cyli.dat\n")
    got = extract(tmp_path, "brick",
                  "0 Brick\n1 16 0 0 0  3 0 0  0 1 0  0 0 1 stud.dat\n")
    assert "elliptical" in got


def test_an_axis_column_out_of_the_circles_plane_is_measured_in_degrees(tmp_path):
    write(tmp_path, "4-4ring2", "0 Ring\n")
    square = extract(tmp_path, "a", f"0 A\n1 16 {IDENTITY} 4-4ring2.dat\n")
    assert square["skew-deg"] == 0.0
    # Columns, not rows: x and z stay the unit circle's own axes and the y
    # column is tipped 15 degrees out of their plane.
    leaned = extract(
        tmp_path, "b",
        "0 B\n1 16 0 0 0  1 0.2588 0  0 0.9659 0  0 0 1 4-4ring2.dat\n")
    assert leaned["skew-deg"] == pytest.approx(15.0, abs=0.05)


def test_translation_does_not_make_two_identical_studs_two_entries(tmp_path):
    """Forty-eight studs on a baseplate differ only in where they sit, and
    every ancestor would otherwise re-multiply all forty-eight."""
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    body = "0 A\n" + "".join(
        f"1 16 {x} 0 0 1 0 0 0 1 0 0 0 1 4-4cyli.dat\n" for x in range(48))
    write(tmp_path, "a", body)
    ex = features.Extractor([tmp_path / "p"])
    assert len(ex._roll(tmp_path / "p" / "a.dat")["round"]) == 1


def test_counts_are_summed_over_the_whole_subtree(tmp_path):
    write(tmp_path, "leaf",
          "0 Leaf\n3 16 0 0 0 1 0 0 0 1 0\n5 24 0 0 0 1 0 0 0 1 0 1 1 1\n")
    got = extract(tmp_path, "top",
                  f"0 Top\n1 16 {IDENTITY} leaf.dat\n"
                  f"1 16 {IDENTITY} leaf.dat\n4 16 0 0 0 1 0 0 1 1 0 0 1 0\n")
    assert got["tris"] == 2 and got["condlines"] == 2 and got["quads"] == 1
    assert got["subfiles"] == 1 and got["depth"] == 1


def test_a_winding_declared_deep_in_the_tree_reaches_the_part(tmp_path):
    write(tmp_path, "sub", "0 Sub\n0 BFC NOCLIP\n")
    got = extract(tmp_path, "a", f"0 A\n1 16 {IDENTITY} sub.dat\n")
    assert "bfc-noclip" in got


def test_a_reference_to_a_file_that_is_not_there_is_not_fatal(tmp_path):
    """Half the library's defects are missing geometry; a missing subfile is
    the same kind of thing and must not stop the other 24,590 parts."""
    got = extract(tmp_path, "a", f"0 A\n1 16 {IDENTITY} nosuchfile.dat\n")
    assert got["tris"] == 0


def test_a_file_referencing_itself_terminates(tmp_path):
    got = extract(tmp_path, "loop", f"0 Loop\n1 16 {IDENTITY} loop.dat\n")
    assert got["depth"] == 0


def test_every_flag_and_measure_is_named_in_the_vocabulary(tmp_path):
    write(tmp_path, "4-4cyli", "0 Cylinder\n")
    got = extract(tmp_path, "a",
                  "0 A\n0 BFC CERTIFY CW\n"
                  "1 16 0 0 0  3 0 0  0 0.7 0.7  0 0 1 4-4cyli.dat\n")
    known = set(features.FLAGS) | set(features.MEASURES)
    assert set(got) <= known, sorted(set(got) - known)
    assert "bfc-cw" in got
