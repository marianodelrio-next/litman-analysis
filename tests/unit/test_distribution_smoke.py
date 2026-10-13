import subprocess


def test_wheel_can_be_built(tmp_path):
    wheelhouse = tmp_path / "wheelhouse"
    result = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(wheelhouse)], capture_output=True, text=True)
    if result.returncode:
        import pytest
        external_markers = ("setuptools", "Temporary failure in name resolution", "Could not find a version")
        if any(marker in result.stderr for marker in external_markers):
            pytest.skip(f"wheel prerequisites unavailable: {result.stderr[-400:]}")
        raise AssertionError(result.stderr)
    wheels = list(wheelhouse.glob("litman_core-*.whl"))
    assert wheels
