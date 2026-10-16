#!/bin/sh
# Desinstala LitMan de este equipo (Ubuntu/Linux). Quita sólo lo que registró
# `litman install` (skills, subagente, MCP) y, salvo que se indique lo
# contrario, conserva el token, el cliente OAuth y la carpeta LitMan. Nunca
# desinstala Git, uv, la CLI del proveedor ni un navegador.
set -eu

SRC="${LITMAN_SRC_DIR:-$HOME/.local/share/litman/src}"

UNINSTALL_ARGS=""
if [ "${LITMAN_REMOVE_WORKSPACE:-0}" = "1" ]; then
    UNINSTALL_ARGS="$UNINSTALL_ARGS --remove-workspace"
fi
if [ "${LITMAN_PURGE_DATA:-0}" = "1" ]; then
    UNINSTALL_ARGS="$UNINSTALL_ARGS --purge-data"
fi

if command -v uv >/dev/null 2>&1; then
    LITMAN_BIN="$(uv tool dir --bin)/litman"
    if [ -x "$LITMAN_BIN" ]; then
        "$LITMAN_BIN" uninstall $UNINSTALL_ARGS
    fi
    uv tool uninstall litman-harness || true
fi

rm -rf "$SRC"

echo "LitMan desinstalado."
