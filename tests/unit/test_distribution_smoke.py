import os
import subprocess


def _run(command, *, cwd=None):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, check=True)


def test_installed_wheel_runs_outside_checkout(tmp_path):
    wheelhouse = tmp_path / "wheelhouse"
    result = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(wheelhouse)], capture_output=True, text=True)
    if result.returncode:
        import pytest
        external_markers = (
            "Temporary failure in name resolution",
            "Name or service not known",
            "Could not resolve host",
            "Failed to download",
            "Download interrupted",
            "download was interrupted",
            "Could not connect to",
            "Failed to connect to",
            "Connection refused",
            "Connection reset",
            "Network is unreachable",
        )
        if any(marker.lower() in result.stderr.lower() for marker in external_markers):
            pytest.skip(f"wheel prerequisites unavailable: {result.stderr[-400:]}")
        raise AssertionError(result.stderr)
    wheels = list(wheelhouse.glob("litman_core-*.whl"))
    assert wheels

    environment = tmp_path / "venv"
    _run(["uv", "venv", "--python", "3.11", str(environment)])
    _run(["uv", "pip", "install", "--python", str(environment / "bin/python"), str(wheels[0])])

    outside_checkout = tmp_path / "outside-checkout"
    outside_checkout.mkdir()
    version = _run([str(environment / "bin/litman-core"), "--version"], cwd=outside_checkout)
    assert version.stdout.strip()

    check_resource = (
        "import litman_core, pathlib; "
        "from litman_core.resource_paths import resource_path; "
        "module = pathlib.Path(litman_core.__file__).resolve(); "
        "resource = resource_path('schemas', 'job.schema.json').resolve(); "
        "assert 'site-packages' in str(module); "
        "assert 'site-packages' in str(resource); "
        "assert resource.read_text(encoding='utf-8').startswith('{')"
    )
    _run([str(environment / "bin/python"), "-c", check_resource], cwd=outside_checkout)
