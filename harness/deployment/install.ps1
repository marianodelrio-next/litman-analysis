# Instala o actualiza LitMan en este equipo (Windows). Idempotente: se puede
# volver a ejecutar para actualizar. Nunca instala Git, uv, la CLI del
# proveedor (Codex o Claude Code) ni un navegador por su cuenta: si falta
# algo, se detiene y explica exactamente qué ejecutar o descargar. No eleva
# privilegios de administrador.
$ErrorActionPreference = 'Stop'

if (-not $env:LITMAN_APP) {
    Write-Error "Falta LITMAN_APP. Indique la aplicacion con la que va a trabajar, por ejemplo:`n  `$env:LITMAN_APP='codex'; irm <url de este script> | iex`n  `$env:LITMAN_APP='claude'; irm <url de este script> | iex"
    exit 1
}
if ($env:LITMAN_APP -ne 'codex' -and $env:LITMAN_APP -ne 'claude') {
    Write-Error "LITMAN_APP debe ser 'codex' o 'claude' (recibido: $($env:LITMAN_APP))"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Falta Git. Instalelo desde: https://git-scm.com/downloads/win"
    exit 1
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "Falta uv. Ejecute usted mismo:`n  irm https://astral.sh/uv/install.ps1 | iex`nDocumentacion: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

if ($env:LITMAN_APP -eq 'codex') {
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        Write-Error "Falta la CLI de Codex. Instalela siguiendo:`n  https://github.com/openai/codex"
        exit 1
    }
} else {
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Error "Falta la CLI de Claude Code. Instalela siguiendo:`n  https://docs.claude.com/en/docs/claude-code/setup"
        exit 1
    }
}

$Src = if ($env:LITMAN_SRC_DIR) { $env:LITMAN_SRC_DIR } else { "$env:LOCALAPPDATA\LitMan\src" }
$Repo = if ($env:LITMAN_REPO) { $env:LITMAN_REPO } else { "https://github.com/marianodelrio-next/litman-analysis.git" }

if (Test-Path "$Src\.git") {
    git -C $Src fetch --tags --quiet
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Src) | Out-Null
    git clone --quiet $Repo $Src
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$LatestTag = git -C $Src tag -l 'v*' --sort=-v:refname | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } | Select-Object -First 1
if (-not $LatestTag) {
    Write-Error "No existe una versión publicada de LitMan para instalar."
    exit 1
}
git -C $Src checkout --quiet --detach $LatestTag
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv tool install --force --python 3.11 "$Src\harness" --with "$Src\core"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# uv escribe UTF-8; sin esto PowerShell lo decodifica con la pagina de codigos
# de la consola y rompe rutas con acentos (por ejemplo, el perfil de usuario).
# Sin consola no se puede cambiar: se sigue con la codificacion actual.
$PreviousEncoding = [Console]::OutputEncoding
$EncodingChanged = $false
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $EncodingChanged = $true } catch { }
try {
    $ToolDir = uv tool dir
} finally {
    if ($EncodingChanged) { [Console]::OutputEncoding = $PreviousEncoding }
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# La CLI se ejecuta con el python.exe del entorno de la herramienta, no con el
# lanzador litman de uv: Smart App Control puede bloquear esos lanzadores.
$Python = Join-Path $ToolDir 'litman-harness\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Error "No se encuentra el interprete de LitMan en: $Python"
    exit 1
}
& $Python -m litman_harness.interfaces.cli install --app $env:LITMAN_APP --source $Src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Instalacion completa. Para terminar:"
Write-Host "  1. Cierre y vuelva a abrir la aplicacion."
Write-Host "  2. Abra la carpeta LitMan (`$env:USERPROFILE\LitMan)."
Write-Host "  3. Escriba: prepara mi equipo"
