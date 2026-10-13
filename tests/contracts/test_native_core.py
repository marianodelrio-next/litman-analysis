import importlib.util
import inspect
from pathlib import Path


def test_core_namespace_exposes_canonical_runner() -> None:
    from litman_core import JobRunner
    from litman_core.execution.job_runner import JobRunner as ExecutionJobRunner

    assert JobRunner is ExecutionJobRunner


def test_legacy_python_package_is_removed() -> None:
    root = Path(__file__).resolve().parents[2]

    legacy_package = "litman" + "_analysis"
    assert not (root / "src" / legacy_package).exists()
    assert importlib.util.find_spec(legacy_package) is None


def test_core_namespace_resolves_packaged_resources() -> None:
    from litman_core.resource_paths import resource_path

    schema = resource_path("schemas", "job.schema.json")
    assert schema == Path(schema)
    assert schema.is_file()


def test_core_runner_does_not_depend_on_container_launcher() -> None:
    from litman_core import JobRunner

    source = inspect.getsource(JobRunner)
    assert "ContainerJobLauncher" not in source
    assert "docker" not in source.lower()


def test_cli_uses_the_same_core_runner() -> None:
    import litman_core.cli as cli
    from litman_core import JobRunner

    assert cli.JobRunner is JobRunner
    assert not (Path(__file__).resolve().parents[2] / "src/litman_core/worker.py").exists()
    assert not (Path(__file__).resolve().parents[2] / "src/litman_core/execution/container_launcher.py").exists()


def test_all_product_python_imports_use_core_namespace() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "litman_core"

    legacy_package = "litman" + "_analysis"
    offenders = [path for path in root.rglob("*.py") if legacy_package in path.read_text(encoding="utf-8")]
    assert offenders == []
