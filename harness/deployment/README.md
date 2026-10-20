# Install LitMan

This page is the canonical installation, maintenance, and uninstallation guide
for LitMan Harness. For contributor setup, use the
[Harness development guide](../docs/development.md).

## Guided installation for a business user

This route is for someone who already has Git and either Codex App or Claude
Desktop. Paste one command into a terminal. The installer is idempotent, so the
same command also reinstalls an existing installation from the latest
published version.

| Component | Windows | Ubuntu |
| --- | --- | --- |
| LitMan folder opened in the app | `%USERPROFILE%\LitMan` | `~/LitMan` |
| Hidden repository checkout, never opened in the app | `%LOCALAPPDATA%\LitMan\src` | `~/.local/share/litman/src` |
| `litman`, `litman-mcp`, and `litman-core` | uv tool with uv-managed Python 3.11 | same |
| Product skills (`conectar-licitacion`, `resumir-licitacion`, `preparar-equipo`, `actualizar-equipo`, `ayuda-litman`) | Codex: `~/.agents/skills`; Claude: `~/.claude/skills` | same |
| `lector-licitacion` reader agent | `~/.codex/agents/*.toml`; `~/.claude/agents/*.md` | same |
| `litman` MCP registration | delimited block in `~/.codex/config.toml`; `~/.claude.json` with user scope | same |
| OAuth client/token, settings, state, install manifest | `%LOCALAPPDATA%\litman-harness` | `~/.config` and `~/.local/state/litman-harness` |

The LitMan folder contains `AGENTS.md`; for Claude it also contains a
`CLAUDE.md` bridge with `@AGENTS.md`, because Claude Desktop does not read
`AGENTS.md` directly. MCP is configured with a two-hour tool timeout.

For Codex:

```sh
LITMAN_APP=codex bash -c "$(curl -fsSL https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.sh)"
```

```powershell
$env:LITMAN_APP='codex'; irm https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.ps1 | iex
```

Set `LITMAN_APP` to `claude` instead when installing for Claude.

Installers use only published stable tags named `vX.Y.Z`. If no such tag
exists, they stop without installing. Run `litman check-update` to check for a
new version; the `actualizar-equipo` skill summarizes the changes and guides
the update. Close and reopen the app after updating. Installations created
before tagged updates were introduced need this install command once to save
the repository location and install the `actualizar-equipo` skill. Afterwards,
ask the app to **“actualiza mi equipo”**. On Linux the skill runs the update;
on Windows it asks you to close the app, run the displayed command in
PowerShell, and reopen the app. Restart the app after every update.

The script clones or updates the repository, installs the tools with
`uv tool install --python 3.11 harness --with core`, then runs
`litman install --app <app> --source <repo>`. That command creates the LitMan
folder, copies the product skills and reader agent, registers the MCP server,
sets `tool_timeout_sec = 7200` for Codex or `MCP_TOOL_TIMEOUT` for Claude Code,
and records an installation manifest.

On Windows, `install.ps1` and `uninstall.ps1` run the Harness CLI as
`python.exe -m litman_harness.interfaces.cli` with the tool environment's
interpreter (`<uv tool dir>\litman-harness\Scripts\python.exe`) instead of
the uv-generated `litman.exe` launcher, because Smart App Control may block uv
launchers. The `litman` command written into the workspace `AGENTS.md` uses
the same form, with the PowerShell call operator:
`& "<scripts dir>\python.exe" -m litman_harness.interfaces.cli`. The scripts
read `uv tool dir` as UTF-8, so user profiles with accented characters are
supported. The MCP server and Core still run through `litman-mcp.exe` and
`litman-core.exe`.

The installer never installs Git, uv, the provider CLI, or a browser by itself.
If one is missing, it stops with an official link or one-step command for the
person to run before repeating the installation command.

The administrator of the Google Cloud project that owns the OAuth client
(`client_secret.json`) must enable the **Google Docs API** once, in APIs &
Services > Library. It uses the existing `drive` scope, so nobody has to log in
again. Until it is enabled, reading, editing, and creating Google Docs return
`docs_api_disabled`, `diagnose` reports `docs_api: "disabled"`, and the rest of
LitMan keeps working.

Reading and editing Google Sheets needs the **Google Sheets API** enabled the
same way. It also uses the existing `drive` scope. Until it is enabled,
`read_file` on a Google Sheet and `preview_sheet_edit`/`apply_sheet_edit`
return `sheets_api_disabled`, `diagnose` reports `sheets_api: "disabled"`,
and other files are unaffected.

When installation finishes, restart the app, open the `LitMan` folder, and
write **“prepara mi equipo”**. The installed product skill guides OAuth client
setup with `litman install --oauth-client`, `litman login`, provider sign-in,
`setup`, and final diagnostics.

### Update, repair, or uninstall

- Update by asking **“actualiza mi equipo”** in the app. The skill checks the
  newest published version, summarizes its changes, and guides the platform's
  update steps. Close and reopen the app after the update.
- Installations created before tagged updates were introduced need the guided
  installation command once to save the source checkout and install the new
  skill. Future updates use **“actualiza mi equipo”**.
- Repair by writing **“prepara mi equipo”** in the app. The skill runs
  diagnostics and addresses only missing setup.
- Uninstall with the script for the current platform:

  ```sh
  bash harness/deployment/uninstall.sh
  ```

  ```powershell
  harness/deployment/uninstall.ps1
  ```

By default uninstallation removes only resources recorded by `litman install`:
product skills, the reader agent, and the MCP block or registration. It keeps
the OAuth client and token, the LitMan folder, and private data.

Set `LITMAN_REMOVE_WORKSPACE=1` to also remove the LitMan folder, but only when
the installer created it. Set `LITMAN_PURGE_DATA=1` to also remove the OAuth
client and token, local settings, plans, and work directory. Uninstallation
never removes Git, uv, the provider CLI, or a browser. If a resource is in use,
it returns `uninstall_incomplete` without uninstalling `litman-harness` or
deleting the local checkout; close the program using it and retry.

### Direct install and uninstall commands

The scripts invoke these CLI-only operations:

```sh
litman install --app codex --source /path/to/repository
litman install --oauth-client /path/client_secret.json [--delete-original]
litman uninstall [--remove-workspace] [--purge-data]
```

They are intentionally absent from MCP `tools/list`. See
`harness/src/litman_harness/installation.py` for deterministic conflict and
idempotency behavior and the installation manifest implementation.

## Advanced installation from wheels

This route is for an IT-managed Python environment. Build or obtain compatible
`litman-core` and `litman-harness` wheels and keep them outside the checkout.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /path/litman_core-0.1.0-py3-none-any.whl /path/litman_harness-0.1.0-py3-none-any.whl
.venv/bin/litman setup --json '{"provider": "codex"}'
.venv/bin/litman diagnose
.venv/bin/litman-mcp
```

Do not use the development `uv.lock` for a release installation: its local
`../core` source applies only to the checkout. Keep OAuth and state directories
outside the checkout. Harness locates `litman-core` in the active environment's
scripts directory (`sysconfig.get_path("scripts")`), not beside the resolved
Python interpreter. `litman setup` validates `litman-core info` and records the
provider and optional model before any analysis.

Harness does not read or write LitMan Core's `config.toml`. It generates a
minimal temporary configuration for each analysis and passes it to
`litman-core run --config`. Core's `config.toml` and `local-secrets/` are needed
only when operating Core independently, as described by the
[Core deployment guide](../../core/deployment/README.md).

The repository [public Core CLI contract](../../docs/contracts.md) owns the
fields Harness sends and consumes. Core's
[internal run documentation](../../core/docs/contracts.md) is informative for
Core contributors but is not the Harness compatibility boundary.

Published results do not remain on local disk. Harness uploads them to a dated
`YYYY-MM-DD <publication_id>` folder under the registered `Analisis inicial` or
`Analisis detallado` Drive folder, according to the analysis type.
