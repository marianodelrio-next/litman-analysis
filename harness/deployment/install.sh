#!/bin/sh
# Instala o actualiza LitMan en este equipo (Ubuntu/Linux). Idempotente: se
# puede volver a ejecutar para actualizar. Nunca instala Git, uv, la CLI del
# proveedor (Codex o Claude Code) ni un navegador por su cuenta: si falta
# algo, se detiene y explica exactamente qué ejecutar o descargar.
set -eu

if [ -z "${LITMAN_APP:-}" ]; then
    echo "Falta LITMAN_APP. Indique la aplicación con la que va a trabajar:" >&2
    echo "  LITMAN_APP=codex bash -c \"\$(curl -fsSL <url de este script>)\"" >&2
    echo "  LITMAN_APP=claude bash -c \"\$(curl -fsSL <url de este script>)\"" >&2
    exit 1
fi
if [ "$LITMAN_APP" != "codex" ] && [ "$LITMAN_APP" != "claude" ]; then
    echo "LITMAN_APP debe ser 'codex' o 'claude' (recibido: $LITMAN_APP)" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "Falta Git. Instálelo desde: https://git-scm.com/downloads" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "Falta uv. Ejecute usted mismo:" >&2
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "Documentación: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

SRC="${LITMAN_SRC_DIR:-$HOME/.local/share/litman/src}"
REPO="${LITMAN_REPO:-https://github.com/marianodelrio-next/litman-analysis.git}"

if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch --tags --quiet
else
    mkdir -p "$(dirname "$SRC")"
    git clone --quiet "$REPO" "$SRC"
fi
LATEST_TAG=$(git -C "$SRC" tag -l 'v*' --sort=-v:refname | head -n1)
if [ -n "$LATEST_TAG" ]; then
    git -C "$SRC" checkout --quiet --detach "$LATEST_TAG"
else
    git -C "$SRC" checkout --quiet --detach origin/HEAD
fi

uv tool install --force --python 3.11 "$SRC/harness" --with "$SRC/core"

if [ "$LITMAN_APP" = "codex" ]; then
    if ! command -v codex >/dev/null 2>&1; then
        echo "Falta la CLI de Codex. Instálela siguiendo:" >&2
        echo "  https://github.com/openai/codex" >&2
        exit 1
    fi
else
    if ! command -v claude >/dev/null 2>&1; then
        echo "Falta la CLI de Claude Code. Instálela siguiendo:" >&2
        echo "  https://docs.claude.com/en/docs/claude-code/setup" >&2
        exit 1
    fi
fi

LITMAN_BIN="$(uv tool dir --bin)/litman"
"$LITMAN_BIN" install --app "$LITMAN_APP" --source "$SRC"

echo ""
echo "Instalación completa. Para terminar:"
echo "  1. Cierre y vuelva a abrir la aplicación."
echo "  2. Abra la carpeta LitMan (~/LitMan)."
echo "  3. Escriba: prepara mi equipo"
