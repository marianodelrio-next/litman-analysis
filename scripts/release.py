#!/usr/bin/env python3
"""Scripted release flow for LitMan's single product version.

Subcommands: ``check``, ``prepare`` and ``tag``. See ``docs/releasing.md`` for
the full release flow and the policies around tags and ``CHANGELOG.md``. Uses
only the standard library; run with ``python3`` from the repository root.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"


def version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return (int(major), int(minor), int(patch))


@dataclass(frozen=True)
class VersionSite:
    rel_path: str
    pattern: re.Pattern[str]
    label: str


def _site(rel_path: str, pattern: str, label: str) -> VersionSite:
    return VersionSite(rel_path, re.compile(pattern), label)


# Explicit, maintained list of every place the product version is written.
# `docs/windows-codex-validation.md` records a historical validation output
# and carries a permanent `X.Y.Z` placeholder instead of a version site.
VERSION_SITES: list[VersionSite] = [
    _site("core/pyproject.toml", r'(?m)^version = "([^"]+)"$', "core/pyproject.toml [project] version"),
    _site("harness/pyproject.toml", r'(?m)^version = "([^"]+)"$', "harness/pyproject.toml [project] version"),
    _site("harness/pyproject.toml", r'"litman-core==([^"]+)"', "harness/pyproject.toml litman-core pin"),
    _site("core/src/litman_core/__init__.py", r'__version__ = "([^"]+)"',
          "core/src/litman_core/__init__.py __version__"),
    _site("harness/src/litman_harness/__init__.py", r'__version__ = "([^"]+)"',
          "harness/src/litman_harness/__init__.py __version__"),
    _site("core/uv.lock", r'name = "litman-core"\nversion = "([^"]+)"', "core/uv.lock litman-core version"),
    _site("harness/uv.lock", r'name = "litman-core"\nversion = "([^"]+)"', "harness/uv.lock litman-core version"),
    _site("harness/uv.lock", r'name = "litman-harness"\nversion = "([^"]+)"',
          "harness/uv.lock litman-harness version"),
    _site("docs/contracts.md", r'"version": "([^"]+)"', 'docs/contracts.md `info` example "version"'),
    _site("docs/contracts.md", r'litman-core==([^`]+)', "docs/contracts.md litman-core pin mention"),
    _site("harness/deployment/README.md", r'litman_core-([^-]+)-py3-none-any\.whl',
          "harness/deployment/README.md litman_core wheel example"),
    _site("harness/deployment/README.md", r'litman_harness-([^-]+)-py3-none-any\.whl',
          "harness/deployment/README.md litman_harness wheel example"),
    _site("core/deployment/local-install/README.md", r'litman_core-([^-]+)-py3-none-any\.whl',
          "core/deployment/local-install/README.md litman_core wheel example"),
]


class ReleaseError(Exception):
    """Raised to refuse an operation; the message is printed to stderr."""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def read_versions(root: Path = REPO_ROOT) -> dict[VersionSite, str | None]:
    result: dict[VersionSite, str | None] = {}
    for site in VERSION_SITES:
        path = root / site.rel_path
        if not path.exists():
            result[site] = None
            continue
        match = site.pattern.search(_read(path))
        result[site] = match.group(1) if match else None
    return result


def consensus_version(versions: dict[VersionSite, str | None]) -> str | None:
    counts: dict[str, int] = {}
    for value in versions.values():
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def check_versions(root: Path = REPO_ROOT) -> list[str]:
    """Return a list of mismatch descriptions; empty when every site agrees."""
    versions = read_versions(root)
    target = consensus_version(versions)
    problems: list[str] = []
    if target is None:
        return [f"{site.label} ({site.rel_path}): version not found" for site in versions]
    for site, value in versions.items():
        if value is None:
            problems.append(f"{site.label} ({site.rel_path}): version not found")
        elif value != target:
            problems.append(f"{site.label} ({site.rel_path}): found {value!r}, expected {target!r}")
    return problems


@dataclass(frozen=True)
class ChangelogEntry:
    version: str
    date: str
    start: int
    end: int


def parse_changelog(text: str) -> list[ChangelogEntry]:
    """Parse ``## [Unreleased]`` then descending ``## [X.Y.Z] - YYYY-MM-DD`` sections.

    Raises ``ReleaseError`` if the file does not follow this structure. Returns
    the version sections (not Unreleased), oldest first.
    """
    heading_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(text))
    if not headings:
        raise ReleaseError("CHANGELOG.md has no `## ` sections")
    if headings[0].group(1).strip() != "[Unreleased]":
        raise ReleaseError("CHANGELOG.md's first `## ` section must be `## [Unreleased]`")

    version_heading = re.compile(r"^\[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$")
    entries: list[ChangelogEntry] = []
    for index, heading in enumerate(headings[1:], start=1):
        body = heading.group(1).strip()
        match = version_heading.match(body)
        if not match:
            raise ReleaseError(f"CHANGELOG.md section {body!r} does not match `[X.Y.Z] - YYYY-MM-DD`")
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        entries.append(ChangelogEntry(version=match.group(1), date=match.group(2), start=start, end=end))

    for earlier, later in zip(entries, entries[1:]):
        if version_tuple(earlier.version) <= version_tuple(later.version):
            raise ReleaseError(
                f"CHANGELOG.md sections are not in descending order: "
                f"[{earlier.version}] is not newer than [{later.version}]"
            )
    return entries


def unreleased_body(text: str) -> str:
    heading_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(text))
    start = headings[0].end()
    end = headings[1].start() if len(headings) > 1 else len(text)
    return text[start:end]


def has_unreleased_content(text: str) -> bool:
    body = unreleased_body(text)
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("###"):
            return True
    return False


def git(*args: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=check,
    )


def is_tree_clean(cwd: Path = REPO_ROOT) -> bool:
    result = git("status", "--porcelain", cwd=cwd)
    return result.stdout.strip() == ""


def current_branch(cwd: Path = REPO_ROOT) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip()


def local_release_tags(cwd: Path = REPO_ROOT) -> list[tuple[int, int, int]]:
    result = git("tag", "-l", "v*", cwd=cwd)
    tags: list[tuple[int, int, int]] = []
    for line in result.stdout.splitlines():
        match = TAG_PATTERN.match(line.strip())
        if match:
            tags.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return tags


def newest_release_tag(cwd: Path = REPO_ROOT) -> tuple[int, int, int] | None:
    tags = local_release_tags(cwd)
    return max(tags) if tags else None


def cmd_check(args: argparse.Namespace) -> int:
    problems = check_versions(REPO_ROOT)
    changelog_path = CHANGELOG_PATH
    if not changelog_path.exists():
        problems.append("CHANGELOG.md: file not found")
    else:
        try:
            parse_changelog(_read(changelog_path))
        except ReleaseError as exc:
            problems.append(str(exc))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("check: every version site and CHANGELOG.md agree")
    return 0


def _substitute_site(site: VersionSite, root: Path, new_version: str) -> None:
    path = root / site.rel_path
    text = _read(path)
    match = site.pattern.search(text)
    if not match:
        raise ReleaseError(f"{site.label} ({site.rel_path}): version not found")
    start, end = match.span(1)
    _write(path, text[:start] + new_version + text[end:])


def rewrite_changelog(text: str, version: str, release_date: str) -> str:
    heading_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(text))
    unreleased_start = headings[0].end()
    insertion_point = headings[1].start() if len(headings) > 1 else len(text)
    body = text[unreleased_start:insertion_point]
    new_section = f"\n## [{version}] - {release_date}\n{body.lstrip(chr(10))}"
    if not new_section.endswith("\n"):
        new_section += "\n"
    return text[:unreleased_start] + "\n" + new_section + text[insertion_point:]


def cmd_prepare(args: argparse.Namespace) -> int:
    version = args.version
    if not VERSION_PATTERN.match(version):
        print(f"prepare: {version!r} does not match X.Y.Z", file=sys.stderr)
        return 1

    if not is_tree_clean():
        print("prepare: the working tree is dirty", file=sys.stderr)
        return 1

    versions = read_versions()
    current = consensus_version(versions)
    if current is None:
        print("prepare: no existing version could be determined", file=sys.stderr)
        return 1
    target = version_tuple(version)
    newest_tag = newest_release_tag()
    if newest_tag is not None and target <= newest_tag:
        print(f"prepare: {version} is not greater than the newest tag v{'.'.join(map(str, newest_tag))}",
              file=sys.stderr)
        return 1
    if target < version_tuple(current):
        print(f"prepare: {version} is lower than the current version {current}", file=sys.stderr)
        return 1

    if not CHANGELOG_PATH.exists():
        print("prepare: CHANGELOG.md not found", file=sys.stderr)
        return 1
    changelog_text = _read(CHANGELOG_PATH)
    try:
        parse_changelog(changelog_text)
    except ReleaseError as exc:
        print(f"prepare: {exc}", file=sys.stderr)
        return 1
    if not has_unreleased_content(changelog_text):
        print("prepare: CHANGELOG.md's [Unreleased] section is empty", file=sys.stderr)
        return 1

    release_date = args.date or date.today().isoformat()
    try:
        for site in VERSION_SITES:
            _substitute_site(site, REPO_ROOT, version)
    except ReleaseError as exc:
        print(f"prepare: {exc}", file=sys.stderr)
        return 1
    _write(CHANGELOG_PATH, rewrite_changelog(changelog_text, version, release_date))

    print(f"prepare: rewrote every version site and CHANGELOG.md to {version}")

    if not args.no_tests:
        env = {**os.environ, "UV_CACHE_DIR": "/tmp/licitaBot-uv-cache"}
        for package in ("core", "harness"):
            lock_check = subprocess.run(["uv", "lock", "--check"], cwd=REPO_ROOT / package, env=env)
            if lock_check.returncode != 0:
                print(f"prepare: `uv lock --check` failed in {package}/", file=sys.stderr)
                return 1
            tests = subprocess.run(["uv", "run", "--locked", "pytest", "-q"], cwd=REPO_ROOT / package, env=env)
            if tests.returncode != 0:
                print(f"prepare: tests failed in {package}/", file=sys.stderr)
                return 1
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    branch = current_branch()
    if branch != "master":
        print(f"tag: current branch is {branch!r}, not 'master'", file=sys.stderr)
        return 1
    if not is_tree_clean():
        print("tag: the working tree is dirty", file=sys.stderr)
        return 1

    fetch = git("fetch", "origin", check=False)
    if fetch.returncode != 0:
        print(f"tag: `git fetch origin` failed: {fetch.stderr.strip()}", file=sys.stderr)
        return 1
    head = git("rev-parse", "HEAD").stdout.strip()
    remote_master = git("rev-parse", "origin/master", check=False)
    if remote_master.returncode != 0 or remote_master.stdout.strip() != head:
        print("tag: HEAD differs from origin/master", file=sys.stderr)
        return 1

    problems = check_versions()
    changelog_text = _read(CHANGELOG_PATH) if CHANGELOG_PATH.exists() else ""
    if not CHANGELOG_PATH.exists():
        problems.append("CHANGELOG.md: file not found")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1

    try:
        entries = parse_changelog(changelog_text)
    except ReleaseError as exc:
        print(f"tag: {exc}", file=sys.stderr)
        return 1
    if not entries:
        print("tag: CHANGELOG.md has no version section", file=sys.stderr)
        return 1

    version = consensus_version(read_versions())
    assert version is not None
    newest_entry = max(entries, key=lambda entry: version_tuple(entry.version))
    if newest_entry.version != version:
        print(
            f"tag: CHANGELOG.md's newest section is [{newest_entry.version}], expected [{version}]",
            file=sys.stderr,
        )
        return 1

    tag_name = f"v{version}"
    if version_tuple(version) in local_release_tags():
        print(f"tag: {tag_name} already exists locally", file=sys.stderr)
        return 1
    ls_remote = git("ls-remote", "--tags", "origin", tag_name, check=False)
    if ls_remote.stdout.strip():
        print(f"tag: {tag_name} already exists on origin", file=sys.stderr)
        return 1

    git("tag", "-a", tag_name, "-m", f"LitMan {version}", "HEAD")
    print(f"tag: created annotated tag {tag_name} on {head}")
    print(f"tag: push it with `git push origin {tag_name}`")

    if args.push:
        push = git("push", "origin", tag_name, check=False)
        if push.returncode != 0:
            print(f"tag: `git push origin {tag_name}` failed: {push.stderr.strip()}", file=sys.stderr)
            return 1
        print(f"tag: pushed {tag_name} to origin")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="verify every version site and CHANGELOG.md agree")
    check_parser.set_defaults(func=cmd_check)

    prepare_parser = subparsers.add_parser("prepare", help="rewrite every version site and the changelog")
    prepare_parser.add_argument("version", help="target version, X.Y.Z")
    prepare_parser.add_argument("--date", default=None, help="release date, YYYY-MM-DD (default: today)")
    prepare_parser.add_argument("--no-tests", action="store_true", help="skip running both test suites")
    prepare_parser.set_defaults(func=cmd_prepare)

    tag_parser = subparsers.add_parser("tag", help="create the annotated release tag on master")
    tag_parser.add_argument("--push", action="store_true", help="also push the tag to origin")
    tag_parser.set_defaults(func=cmd_tag)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
