# Harness decisions

This log records durable package-level choices. Cross-package architecture and
development-process decisions belong in the repository
[decision log](../../docs/decisions/README.md). Current implementation detail
belongs in [architecture](architecture.md) or [operations](operations.md).

## Harness remains a separate process client of Core

Harness and Core are independent Python distributions. Harness invokes
`litman-core` and consumes only the repository-owned
[public CLI contract](../../docs/contracts.md); it does not import Core or
consume internal run files. This keeps deployment and internal evolution
independent while giving the process boundary an explicit compatibility policy.

## Drive access uses each employee's personal OAuth account

Harness opens a dossier by folder ID with the `drive` scope. It does not reuse
Core's service-account publisher, and secrets never cross CLI/MCP inputs or
dossier state. This preserves the person's Drive permissions and avoids a
second authorization model. The narrower `drive.file` scope was rejected
because it cannot open by ID a dossier created outside the app.

## Resource membership is established by ancestry

The membership adapter follows parent IDs within the connected Drive until it
reaches the dossier root. It never uses a global search. This makes every read
and write depend on structural membership rather than a name or a potentially
ambiguous query.

## Mutations use preview, explicit acceptance, and resumable local plans

Every business mutation is first represented by an account-bound local plan.
An apply call accepts the exact `plan_id`; created resources carry operation and
action markers. The result is a visible acceptance boundary plus deterministic
recovery after interruption, without storing private plans in the dossier.

## Drive v2 ETags guard shared state

An authorized 2026-10-15 smoke test established that Drive API v2 media updates
honor `If-Match` with strong ETags. Harness uses that capability for manifest
and context writes because Drive v3 does not expose the required ETag. Drive
`version` was rejected: harmless opening and server-side processing changed it
and caused false stale-plan results. Content SHA-256 protects manifest previews,
while original files use `md5Checksum` as their content identity.

## External context edits are preserved

`contexto.md` is derived from the manifest, but people may edit it. A mismatch
therefore completes the underlying business mutation while returning the
proposed deterministic content as `context_conflict`. Replacement requires a
new, explicit `overwrite_context: true` preview and still uses optimistic
concurrency.

## Provider choice is installation configuration

Harness validates and stores one Core provider and optional model through
`setup`, then snapshots the choice in each analysis plan. This avoids hidden
provider changes between preview and execution and leaves provider execution
inside Core.

## Publication is part of analysis execution

An accepted analysis plan includes its publication actions. Harness validates
Core's public artifacts into a closed local catalog before any upload, then
publishes without asking for a second acceptance. Failed publication remains
recoverable and does not rerun Core or duplicate confirmed uploads.

## Procurement summaries require human acceptance and cited sources

Harness has no LLM. A chat assistant or constrained read-only reader proposes a
fixed-shape summary; a person accepts it. Each substantive value cites a
registered dossier resource, and Harness checks format and provenance rather
than claiming to verify meaning. This keeps generation outside the deterministic
runtime and acceptance explicit.

## Product agents are separate from development agents

Files under `harness/agent/` are installed product behavior. Repository skills
and instructions under `.agents/`, `.claude/skills/`, and `AGENTS.md` govern
development. Keeping these systems separate prevents Factory tooling from
silently changing the user's LitMan assistant, or vice versa.
