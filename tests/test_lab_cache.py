from brick_icons.lab import cache


def test_same_argv_gives_the_same_key():
    a = cache.key(["3001", "--engine", "occt"])
    b = cache.key(["3001", "--engine", "occt"])
    assert a == b


def test_different_argv_gives_a_different_key():
    assert cache.key(["3001"]) != cache.key(["3002"])
    assert cache.key(["3001"]) != cache.key(["3001", "--engine", "occt"])


def test_key_is_order_insensitive_across_flags():
    """`--engine occt --shading outline` and the reverse are one render."""
    a = cache.key(["3001", "--engine", "occt", "--shading", "outline"])
    b = cache.key(["3001", "--shading", "outline", "--engine", "occt"])
    assert a == b


def test_key_is_filesystem_safe():
    k = cache.key(["3001", "--angle", "30,25"])
    assert k.isalnum() and len(k) == 16


def test_dir_for_is_under_the_root(tmp_path):
    d = cache.dir_for(["3001"], root=tmp_path)
    assert tmp_path in d.parents


def test_artifacts_lists_what_a_render_wrote(tmp_path):
    d = cache.dir_for(["3001"], root=tmp_path)
    d.mkdir(parents=True)
    (d / "3001.svg").write_text("<svg/>")
    (d / "3001.gray.png").write_bytes(b"")
    names = {a["name"] for a in cache.artifacts(d)}
    assert names == {"3001.svg", "3001.gray.png"}


def test_artifacts_is_empty_for_a_missing_dir(tmp_path):
    assert cache.artifacts(tmp_path / "nope") == []
