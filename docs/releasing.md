# Releasing LitMan

LitMan is published as a single product version `X.Y.Z`, shared by Core and
Harness, through annotated `vX.Y.Z` tags on `master`. Users install the newest
tag only; see [the tagged-releases decision](decisions/0002-tagged-releases.md)
for the policy and its rationale. This page is the full flow; follow it exactly
when asked to release or publish a version.

## Tag policy

- Tags are never test or pre-release tags: only `vX.Y.Z` with three numeric
  components.
- A published tag is never moved or deleted. A bad release is fixed by
  publishing the next version, not by rewriting the tag.

## `scripts/release.py`

Run with `python3` from the repository root. It uses only the standard
library and never commits, tags, or pushes except where noted.

- `check` — verifies that every version site (both packages, the Harness pin
  on Core, both lockfiles, and the documentation examples) carries the same
  `X.Y.Z`, and that `CHANGELOG.md` parses. Exits non-zero and names every
  mismatch otherwise.
- `prepare X.Y.Z [--date YYYY-MM-DD] [--no-tests]` — rewrites every version
  site to `X.Y.Z` and moves the `## [Unreleased]` entries into a new
  `## [X.Y.Z] - <date>` section, leaving `[Unreleased]` empty. Refuses, without
  changing any file, a dirty tree, a malformed version, a version that is not
  greater than the newest local `vX.Y.Z` tag, a version lower than the current
  one, or an empty `[Unreleased]` section. Unless `--no-tests` is given, it
  then runs `uv lock --check` and `uv run --locked pytest -q` in `core/` and
  `harness/` (`UV_CACHE_DIR=/tmp/licitaBot-uv-cache`), so a broken lockfile
  rewrite or a regression is caught before the release commit.
- `tag [--push]` — on `master`, with a clean tree and `HEAD` matching
  `origin/master` after `git fetch origin`, with `check` passing and
  `CHANGELOG.md`'s newest section matching the current version, creates the
  annotated tag `vX.Y.Z` (message `LitMan X.Y.Z`) on `HEAD` and prints the push
  command. Only with `--push` does it run `git push origin vX.Y.Z`.

## Flow

1. **Prepare on a branch.** On a branch (not `master`), with a clean tree,
   run `python3 scripts/release.py prepare X.Y.Z`. Review the rewritten files
   and the new `CHANGELOG.md` section, then commit.
2. **Pull request.** Open a pull request for the branch like any other
   change; it is reviewed the same way.
3. **Merge.** Merge the pull request into `master`.
4. **Tag.** On `master`, with the merge pulled, run
   `python3 scripts/release.py tag --push`. This pushes the tag that users'
   update checks and installers look for.
5. **Announce.** Tell the person the release is published; they decide whether
   and how to notify installed users.

## Changelog

`CHANGELOG.md` at the repository root follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/): an
`## [Unreleased]` section, then `## [X.Y.Z] - YYYY-MM-DD` sections in
descending order, each with `### Added` / `### Changed` / `### Fixed`
subsections as needed. It is written in English and describes user-visible
behaviour in plain language, so it can be read directly or summarized for a
non-technical audience. Every user-visible change adds an entry under
`## [Unreleased]` in the same pull request; see [AGENTS.md](../AGENTS.md).

## Version sites

`scripts/release.py` keeps an explicit list of every place the version is
written: `core/pyproject.toml`, `harness/pyproject.toml` (its own version and
the `litman-core==` pin), both packages' `__init__.py`, the `litman-core` /
`litman-harness` entries of both `uv.lock` files, and the documentation
examples in `docs/contracts.md`, `harness/deployment/README.md`, and
`core/deployment/local-install/README.md`. `docs/windows-codex-validation.md`
records a historical validation output and keeps a permanent `X.Y.Z`
placeholder instead of a version site. The list is maintained by hand; it is
not a repository-wide search and replace.
