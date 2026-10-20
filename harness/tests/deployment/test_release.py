"""Tests for `scripts/release.py`: `check`, `prepare`, and `tag`.

Never pushes to a real remote: `tag --push` is only exercised against a local
bare repository used as `origin`.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).parents[3]
RELEASE_PY = REPO_ROOT / "scripts" / "release.py"

VERSION_FILES = {
    "core/pyproject.toml": '[project]\nname = "litman-core"\nversion = "{v}"\nrequires-python = ">=3.11"\n',
    "harness/pyproject.toml": (
        '[project]\nname = "litman-harness"\nversion = "{v}"\n'
        'dependencies = [\n  "litman-core=={v}",\n]\n'
    ),
    "core/src/litman_core/__init__.py": '__version__ = "{v}"\n',
    "harness/src/litman_harness/__init__.py": '__version__ = "{v}"\n',
    "core/uv.lock": '[[package]]\nname = "litman-core"\nversion = "{v}"\nsource = {{ editable = "." }}\n',
    "harness/uv.lock": (
        '[[package]]\nname = "litman-core"\nversion = "{v}"\nsource = {{ directory = "../core" }}\n\n'
        '[[package]]\nname = "litman-harness"\nversion = "{v}"\nsource = {{ editable = "." }}\n'
    ),
    "docs/contracts.md": (
        '```json\n{{"contract": 1, "version": "{v}"}}\n```\n\n'
        "Harness pins `litman-core=={v}`; the `contract` check protects it.\n"
    ),
    "harness/deployment/README.md": (
        "```sh\nuv pip install --python .venv/bin/python "
        "/path/litman_core-{v}-py3-none-any.whl /path/litman_harness-{v}-py3-none-any.whl\n```\n"
    ),
    "core/deployment/local-install/README.md": (
        "```sh\nuv pip install --python .venv/bin/python /path/litman_core-{v}-py3-none-any.whl\n```\n"
    ),
}

CHANGELOG_EMPTY_UNRELEASED = "# Changelog\n\n## [Unreleased]\n"
CHANGELOG_WITH_UNRELEASED_ENTRY = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Something.\n"


def _write_version_sites(root: Path, version: str) -> None:
    for rel_path, template in VERSION_FILES.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.format(v=version), encoding="utf-8")


def _build_fixture_repo(tmp_path: Path, *, version: str, changelog: str) -> Path:
    root = tmp_path / "fixture-repo"
    root.mkdir()
    (root / "scripts").mkdir()
    shutil.copy2(RELEASE_PY, root / "scripts" / "release.py")
    _write_version_sites(root, version)
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return root


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def _git_init(root: Path) -> None:
    _git(root, "init", "--quiet", "--initial-branch=master")
    _git(root, "config", "user.email", "test@example.test")
    _git(root, "config", "user.name", "Test")


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", message)


def _run_release(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "release.py"), *args],
        cwd=root, capture_output=True, text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = _build_fixture_repo(tmp_path, version="0.1.0", changelog=CHANGELOG_WITH_UNRELEASED_ENTRY)
    _git_init(root)
    _commit_all(root, "snapshot")
    return root


# -- check --------------------------------------------------------------


def test_check_passes_on_the_real_repository():
    result = subprocess.run(
        [sys.executable, str(RELEASE_PY), "check"], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_passes_on_a_consistent_fixture(repo: Path):
    result = _run_release(repo, "check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_reports_every_mismatch(repo: Path):
    (repo / "core" / "pyproject.toml").write_text(
        VERSION_FILES["core/pyproject.toml"].format(v="9.9.9"), encoding="utf-8",
    )
    (repo / "docs" / "contracts.md").write_text(
        VERSION_FILES["docs/contracts.md"].format(v="8.8.8"), encoding="utf-8",
    )
    result = _run_release(repo, "check")
    assert result.returncode != 0
    assert "core/pyproject.toml" in result.stderr
    assert "docs/contracts.md" in result.stderr
    assert "harness/pyproject.toml" not in result.stderr


def test_check_fails_when_unreleased_is_not_the_first_section(repo: Path):
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0] - 2026-10-20\n", encoding="utf-8")
    result = _run_release(repo, "check")
    assert result.returncode != 0
    assert "Unreleased" in result.stderr


def test_check_fails_when_versions_are_out_of_order(repo: Path):
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-10-20\n\n## [0.2.0] - 2026-10-19\n",
        encoding="utf-8",
    )
    result = _run_release(repo, "check")
    assert result.returncode != 0
    assert "descending order" in result.stderr


def test_check_passes_with_only_unreleased_before_the_first_release(repo: Path):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_EMPTY_UNRELEASED, encoding="utf-8")
    result = _run_release(repo, "check")
    assert result.returncode == 0, result.stdout + result.stderr


# -- prepare --------------------------------------------------------------


def test_prepare_rewrites_every_version_site_and_the_changelog(repo: Path):
    result = _run_release(repo, "prepare", "0.2.0", "--date", "2026-10-21", "--no-tests")
    assert result.returncode == 0, result.stdout + result.stderr
    for rel_path in VERSION_FILES:
        assert "0.2.0" in (repo / rel_path).read_text(encoding="utf-8")
        assert "0.1.0" not in (repo / rel_path).read_text(encoding="utf-8")
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.2.0] - 2026-10-21" in changelog
    assert "- Something." in changelog
    unreleased = changelog.split("## [0.2.0]")[0]
    assert "- Something." not in unreleased


def test_prepare_defaults_the_date_to_today(repo: Path):
    from datetime import date

    result = _run_release(repo, "prepare", "0.2.0", "--no-tests")
    assert result.returncode == 0, result.stdout + result.stderr
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [0.2.0] - {date.today().isoformat()}" in changelog


def test_prepare_allows_the_first_release_at_the_current_version(repo: Path):
    result = _run_release(repo, "prepare", "0.1.0", "--date", "2026-10-20", "--no-tests")
    assert result.returncode == 0, result.stdout + result.stderr


def test_prepare_refuses_a_malformed_version(repo: Path):
    result = _run_release(repo, "prepare", "1.0", "--no-tests")
    assert result.returncode != 0
    assert "X.Y.Z" in result.stderr
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


def test_prepare_refuses_a_dirty_tree(repo: Path):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_WITH_UNRELEASED_ENTRY + "x", encoding="utf-8")
    result = _run_release(repo, "prepare", "0.2.0", "--no-tests")
    assert result.returncode != 0
    assert "dirty" in result.stderr


def test_prepare_refuses_a_version_not_greater_than_the_newest_tag(repo: Path):
    _git(repo, "tag", "-a", "v0.5.0", "-m", "LitMan 0.5.0")
    result = _run_release(repo, "prepare", "0.2.0", "--no-tests")
    assert result.returncode != 0
    assert "newest tag" in result.stderr
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


def test_prepare_refuses_a_version_lower_than_the_current_one(repo: Path):
    result = _run_release(repo, "prepare", "0.0.1", "--no-tests")
    assert result.returncode != 0
    assert "lower than the current version" in result.stderr
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


def test_prepare_leaves_no_file_changed_when_a_later_site_does_not_match(repo: Path):
    # harness/uv.lock is rewritten after core/pyproject.toml in VERSION_SITES;
    # breaking it must not leave core/pyproject.toml (or any other site)
    # rewritten to the new version.
    (repo / "harness" / "uv.lock").write_text("no version marker here\n", encoding="utf-8")
    _commit_all(repo, "break a later version site")
    result = _run_release(repo, "prepare", "0.2.0", "--no-tests")
    assert result.returncode != 0
    assert "harness/uv.lock" in result.stderr
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""
    assert "0.1.0" in (repo / "core" / "pyproject.toml").read_text(encoding="utf-8")


def test_prepare_refuses_an_empty_unreleased_section(repo: Path):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_EMPTY_UNRELEASED, encoding="utf-8")
    _commit_all(repo, "empty unreleased")
    result = _run_release(repo, "prepare", "0.2.0", "--no-tests")
    assert result.returncode != 0
    assert "empty" in result.stderr
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


# -- tag --------------------------------------------------------------


@pytest.fixture
def repo_with_origin(repo: Path, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--quiet", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "--quiet", "-u", "origin", "master")
    return repo


def _prepare_and_commit(repo: Path, version: str, date_str: str) -> None:
    result = _run_release(repo, "prepare", version, "--date", date_str, "--no-tests")
    assert result.returncode == 0, result.stdout + result.stderr
    _commit_all(repo, f"prepare {version}")


def test_tag_creates_the_annotated_tag_and_prints_the_push_command(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "git push origin v0.1.0" in result.stdout
    tags = _git(repo_with_origin, "tag", "-l").stdout.split()
    assert tags == ["v0.1.0"]
    message = _git(repo_with_origin, "tag", "-l", "-n1", "v0.1.0").stdout
    assert "LitMan 0.1.0" in message


def test_tag_push_pushes_to_the_origin_remote(repo_with_origin: Path, tmp_path: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    result = _run_release(repo_with_origin, "tag", "--push")
    assert result.returncode == 0, result.stdout + result.stderr
    origin = tmp_path / "origin.git"
    assert "v0.1.0" in _git(origin, "tag", "-l").stdout


def test_tag_refuses_off_master(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    _git(repo_with_origin, "checkout", "--quiet", "-b", "feature")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "master" in result.stderr
    assert not _git(repo_with_origin, "tag", "-l").stdout.strip()


def test_tag_refuses_a_dirty_tree(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    (repo_with_origin / "CHANGELOG.md").write_text("dirty", encoding="utf-8")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "dirty" in result.stderr


def test_tag_refuses_when_head_differs_from_origin_master(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    # HEAD is never pushed, so origin/master still points at the initial snapshot.
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "origin/master" in result.stderr


def test_tag_refuses_when_check_fails(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    (repo_with_origin / "core" / "pyproject.toml").write_text(
        VERSION_FILES["core/pyproject.toml"].format(v="9.9.9"), encoding="utf-8",
    )
    _commit_all(repo_with_origin, "break a version site")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "core/pyproject.toml" in result.stderr


def test_tag_refuses_when_the_changelog_section_does_not_match_the_version(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    changelog = (repo_with_origin / "CHANGELOG.md").read_text(encoding="utf-8")
    (repo_with_origin / "CHANGELOG.md").write_text(
        changelog.replace("## [0.1.0] - 2026-10-20", "## [0.1.0] - 2026-10-20\n\n## [0.2.0] - 2026-10-21"),
        encoding="utf-8",
    )
    _commit_all(repo_with_origin, "mismatched changelog")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "0.2.0" in result.stderr


def test_tag_refuses_an_existing_local_tag(repo_with_origin: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    _git(repo_with_origin, "tag", "-a", "v0.1.0", "-m", "already here")
    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr


def test_tag_refuses_an_existing_remote_tag(repo_with_origin: Path, tmp_path: Path):
    _prepare_and_commit(repo_with_origin, "0.1.0", "2026-10-20")
    _git(repo_with_origin, "push", "--quiet", "origin", "master")
    origin = tmp_path / "origin.git"

    # Tag an unrelated commit (not reachable from master) directly in a second
    # clone, so the local repo's `git fetch origin` does not auto-follow it:
    # git only auto-fetches tags pointing at objects it has just transferred.
    other_clone = tmp_path / "other-clone"
    _git(tmp_path, "clone", "--quiet", str(origin), str(other_clone))
    _git(other_clone, "config", "user.email", "test@example.test")
    _git(other_clone, "config", "user.name", "Test")
    _git(other_clone, "checkout", "--quiet", "--orphan", "unrelated")
    (other_clone / "marker.txt").write_text("unrelated\n", encoding="utf-8")
    _git(other_clone, "add", "-A")
    _git(other_clone, "commit", "--quiet", "-m", "unrelated commit")
    _git(other_clone, "tag", "-a", "v0.1.0", "-m", "pushed from elsewhere")
    _git(other_clone, "push", "--quiet", "origin", "v0.1.0")

    result = _run_release(repo_with_origin, "tag")
    assert result.returncode != 0
    assert "already exists on origin" in result.stderr
    assert not _git(repo_with_origin, "tag", "-l").stdout.strip()
