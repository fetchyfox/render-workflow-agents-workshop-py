"""Tests for filterDiff — deterministic noise filtering."""

from workshop_agent import filter_diff, Patch


def test_drops_lock_files():
    patches = [
        Patch(file="src/index.ts", diff="+code"),
        Patch(file="package-lock.json", diff="+{}"),
        Patch(file="yarn.lock", diff="+content"),
    ]
    result = filter_diff(patches)
    assert len(result.patches) == 1
    assert result.patches[0].file == "src/index.ts"
    assert set(result.dropped) == {"package-lock.json", "yarn.lock"}


def test_drops_minified():
    patches = [
        Patch(file="dist/app.min.js", diff="+min"),
        Patch(file="src/app.ts", diff="+code"),
    ]
    result = filter_diff(patches)
    assert len(result.patches) == 1
    assert result.patches[0].file == "src/app.ts"


def test_drops_source_maps():
    patches = [
        Patch(file="dist/app.js.map", diff="{}"),
        Patch(file="src/util.ts", diff="+x"),
    ]
    result = filter_diff(patches)
    assert len(result.patches) == 1


def test_keeps_source_files():
    patches = [
        Patch(file="src/users.ts", diff="+export"),
        Patch(file="lib/auth.py", diff="+def"),
    ]
    result = filter_diff(patches)
    assert len(result.patches) == 2
    assert len(result.dropped) == 0


def test_clean_diff_drops_nothing():
    patches = [Patch(file="a.ts", diff="+x"), Patch(file="b.py", diff="+y")]
    result = filter_diff(patches)
    assert len(result.patches) == 2
    assert result.dropped == []
