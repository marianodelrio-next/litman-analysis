# Changelog

All notable, user-visible changes to LitMan are documented in this file. Entries
describe behaviour, in plain language, not implementation details.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
LitMan is published as a single product version, shared by Core and Harness; see
[the release flow](docs/releasing.md) and
[the tagged-releases decision](docs/decisions/0002-tagged-releases.md).

## [Unreleased]

### Added

- Dossier status reports changes to registered originals and published files,
  unavailable references, edited context, and incomplete candidate scans.

## [0.4.0] - 2026-10-26
### Fixed

- Initial and detailed analyses run with Claude Code on Windows no longer fail
  validation because Claude could not open the normalized documents.

## [0.3.0] - 2026-10-26
### Added

- A Windows installation and first-trial guide for Claude Desktop's local Code
  tab, with native Claude Code running the analyses and a validation checklist.

### Fixed

- Analyses run with Claude Code no longer fail with a schema error on Claude
  Code versions that check output schemas strictly, as seen on Windows.

## [0.2.0] - 2026-10-21
### Changed

- Explain planned dossier folders before incorporation and summarize confirmed
  folder and context outcomes after it.
- New comments on dossier Google Docs are attached to an exact phrase or
  section title and appear on that text in Google Docs; general comments are no
  longer created, and new comments on other file types are refused. Creating
  them requires edit access to the document. A comment is reported as created
  only once LitMan can see it in the document; if that cannot be confirmed,
  LitMan says so and never sends it twice. Existing comments remain readable
  and can still be replied to and resolved, and a previously accepted plan that
  adds a general comment must be prepared again.

### Added

- Highlight text in dossier Google Docs with a chosen color, change the color
  or remove it, and add, change or remove a web link on existing text, through
  the same preview and acceptance as other format changes. The preview shows
  the current highlight or link and the complete new address; Google Docs
  gives links their usual appearance. A link change must cover a whole
  existing link.

### Fixed

- A format change whose confirmation was lost is no longer sent again over
  someone else's later format change: LitMan completes it when the requested
  format is visible and otherwise asks you to check the document.

## [0.1.0] - 2026-10-20
### Added

- Local procurement analysis with LitMan Core, usable on its own or through
  Harness.
- Dossier management in Harness: connect a personal Google Drive folder,
  generate deliverables, and publish them with your own account's
  authorization.
- Guided installation and setup for Codex and Claude Code, including the
  product skills that drive dossier work from the chat.
- Guided updates that summarize new versions and explain how to install them
  on Windows or Linux.
