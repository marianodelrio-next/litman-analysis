# 0002 — Tagged releases, a single product version, and the changelog

Status: accepted
Date: 2026-10-20
Change: CHG-0008

## Context

No `v*` tag has ever existed, so the install and update scripts fall back to
whatever is on `master`. The version `0.1.0` is written by hand in several
places across both packages and has never been bumped. There is no changelog,
so neither a person nor an update skill can tell a user what changed.

## Options considered

- Independent versions for Core and Harness, released separately.
- A single product version, shared by both packages, released through
  annotated `vX.Y.Z` tags.
- GitHub Releases instead of, or in addition to, Git tags.

## Decision

LitMan is published as a single product version `X.Y.Z`, shared by Core and
Harness: both packages, the Harness pin on Core, both lockfiles, and the
documentation examples carry the same version. The tag `vX.Y.Z` is the LitMan
version. Independent package versions were rejected: users see one product,
and the changelog and tag map one to one.

Tags are never test or pre-release tags. A published tag is never moved or
deleted; a bad release is fixed by publishing the next version. Installers
and update checks only ever consider the newest `vX.Y.Z` tag, never a branch.

`CHANGELOG.md` at the repository root follows Keep a Changelog 1.1.0, in
English, describing user-visible behaviour in plain language so it can be
summarized for a non-technical audience. A Spanish "NOVEDADES" file was
rejected: one changelog, translated at the point of use, is simpler to keep
consistent than two maintained files.

`scripts/release.py` (`check`, `prepare`, `tag`) owns the explicit list of
version sites and the changelog format, so they cannot drift independently.
It never commits, tags, or pushes except the tag itself, and only with
`--push`; the release commit goes through the normal pull-request workflow.
GitHub Releases were left out of scope: Git tags are sufficient for the
installers and the update check, and adding a second source of truth was not
justified.

## Consequences

- Release steps are scripted and documented in
  [docs/releasing.md](../releasing.md), so an agent can cut a release when
  asked.
- Every user-visible change requires a changelog entry, recorded in
  [AGENTS.md](../../AGENTS.md).
- Installers and the update check (CHG-0008-02) depend on the tag policy
  established here: a missing tag is an error, not a reason to fall back to a
  branch.
- Existing installations, made before any tag exists, need a one-time manual
  reinstall once the first tag is published; this is documented with the
  installer changes (CHG-0008-02).
