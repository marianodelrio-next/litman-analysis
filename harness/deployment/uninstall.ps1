# Desinstala LitMan de este equipo (Windows). Quita solo lo que registro
# `litman install` (skills, subagente, MCP) y, salvo que se indique lo
# contrario, conserva el token, el cliente OAuth y la carpeta LitMan. Nunca
# desinstala Git, uv, la CLI del proveedor ni un navegador. No eleva
# privilegios de administrador.
$ErrorActionPreference = 'Stop'

$Src = if ($env:LITMAN_SRC_DIR) { $env:LITMAN_SRC_DIR } else { "$env:LOCALAPPDATA\LitMan\src" }

$UninstallArgs = @()
if ($env:LITMAN_REMOVE_WORKSPACE -eq '1') { $UninstallArgs += '--remove-workspace' }
if ($env:LITMAN_PURGE_DATA -eq '1') { $UninstallArgs += '--purge-data' }

if (Get-Command uv -ErrorAction SilentlyContinue) {
    # uv escribe UTF-8: se lee asi para no romper rutas con acentos. La CLI se
    # ejecuta con el python.exe de la herramienta, no con el lanzador litman de
    # uv, que Smart App Control puede bloquear.
    $PreviousEncoding = [Console]::OutputEncoding
    $EncodingChanged = $false
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $EncodingChanged = $true } catch { }
    try {
        $ToolDir = uv tool dir
    } finally {
        if ($EncodingChanged) { [Console]::OutputEncoding = $PreviousEncoding }
    }
    $Python = Join-Path $ToolDir 'litman-harness\Scripts\python.exe'
    if (Test-Path $Python) {
        & $Python -m litman_harness.interfaces.cli uninstall @UninstallArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    uv tool uninstall litman-harness 2>$null
}

if (Test-Path $Src) {
    Remove-Item -Recurse -Force $Src
}

Write-Host "LitMan desinstalado."
