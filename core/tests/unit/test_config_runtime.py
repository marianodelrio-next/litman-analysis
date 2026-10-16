from pathlib import Path

from litman_core import config, runtime


def test_windows_defaults_use_local_temp_and_user_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path / "profile"))
    monkeypatch.delenv("LITMAN_CORE_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    settings = config.Settings()
    assert settings.workspace_root == tmp_path / "temp" / "litman-core"
    assert settings.home_dir == tmp_path / "profile"


def test_runtime_skips_posix_chmod_on_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    calls: list[Path] = []
    monkeypatch.setattr(Path, "chmod", lambda self, mode: calls.append(self))
    runtime.initialize_runtime(home=tmp_path / "home", codex_home=tmp_path / "codex", workspace=tmp_path / "work", runs=tmp_path / "runs")
    assert calls == []


def test_posix_runtime_keeps_private_directory_permissions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    runtime.initialize_runtime(home=tmp_path / "home", codex_home=tmp_path / "codex", workspace=tmp_path / "work", runs=tmp_path / "runs")
    assert (tmp_path / "home").stat().st_mode & 0o777 == 0o700
