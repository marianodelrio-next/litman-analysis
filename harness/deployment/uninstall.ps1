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
    $LitmanBin = Join-Path (uv tool dir --bin) "litman.exe"
    if (Test-Path $LitmanBin) {
        & $LitmanBin uninstall @UninstallArgs
    }
    uv tool uninstall litman-harness 2>$null
}

if (Test-Path $Src) {
    Remove-Item -Recurse -Force $Src
}

Write-Host "LitMan desinstalado."
