#!/bin/sh
# Founders: Agent Index → Zoen → Deploy (docs/INSTALL.md). This script is the fallback.
#   curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
# Local Docker instead: ./install.sh --local
set -eu

REPO="${ZOEN_REPO:-https://github.com/EnzoTironi/Plow.git}"
RUNNER="${ZOEN_RUNNER:-https://github.com/plow-pbc/plow-agents.git}"
IMAGE="${ZOEN_IMAGE:-ghcr.io/enzotironi/zoen/all-in-one@sha256:ffb63ba0c437e7ecb11c0fdd82fbd15a4462973a4d97939cc679e250b4f7bc7c}"

LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
    *)
      echo "uso: $0 [--local]" >&2
      exit 1
      ;;
  esac
done
if [ "${ZOEN_LOCAL:-}" = "1" ]; then
  LOCAL=1
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "falta $1." >&2
    exit 1
  }
}

need git
need python3

is_zoen() {
  [ -f "$1/compose.yml" ] && [ -f "$1/Dockerfile" ] && grep -q 'AGENT_ID: \${AGENT_ID:-zoen}' "$1/compose.yml"
}

ROOT=""
case "$0" in
  */install.sh|install.sh)
    ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    ;;
esac
if [ -n "$ROOT" ] && ! is_zoen "$ROOT"; then
  ROOT=""
fi
if [ -z "$ROOT" ] && is_zoen "$(pwd)"; then
  ROOT=$(pwd)
fi
if [ -z "$ROOT" ]; then
  ROOT="${ZOEN_DIR:-$HOME/Plow}"
  if [ ! -d "$ROOT/.git" ]; then
    if [ -e "$ROOT" ] && [ -n "$(ls -A "$ROOT" 2>/dev/null || true)" ]; then
      echo "$ROOT já existe e não é o Zoen. Defina ZOEN_DIR." >&2
      exit 1
    fi
    echo "baixando…"
    git clone "$REPO" "$ROOT"
  fi
fi

cd "$ROOT"
if [ ! -f compose.yml ] || ! grep -q 'AGENT_ID: \${AGENT_ID:-zoen}' compose.yml; then
  echo "este diretório não é o Zoen: $ROOT" >&2
  exit 1
fi

if [ ! -x tools/plow-agents/bin/plow-agents ]; then
  echo "baixando…"
  git clone --depth 1 "$RUNNER" tools/plow-agents
fi

plow() {
  ./bin/plow-agents "$@"
}

token_file="${XDG_CONFIG_HOME:-$HOME/.config}/plow/token"

ensure_login() {
  if [ -s "$token_file" ]; then
    return
  fi
  echo
  echo "Mande do celular exatamente a frase abaixo."
  echo
  plow login || plow login --new-line
}

ensure_line() {
  lines=$(plow lines)
  echo "$lines"
  line=$(printf '%s\n' "$lines" | awk -F '\t' 'NR > 1 && $4 == "free" { print $1; exit }')
  if [ -z "$line" ]; then
    echo "sem linha livre. criando…"
    plow login --new-line
    lines=$(plow lines)
    echo "$lines"
    line=$(printf '%s\n' "$lines" | awk -F '\t' 'NR > 1 && $4 == "free" { print $1; exit }')
  fi
  if [ -z "$line" ]; then
    echo "Ainda sem linha. Fale com o suporte Plow." >&2
    exit 1
  fi
}

if [ "$LOCAL" = 1 ]; then
  need docker
  docker info >/dev/null 2>&1 || {
    echo "Abra o Docker e tente de novo." >&2
    exit 1
  }
  docker compose version >/dev/null 2>&1 || {
    echo "falta o Compose." >&2
    exit 1
  }
  if [ -d plow-credentials ] && [ ! -f plow-credentials ]; then
    echo "Algo ficou pela metade. Rode: docker compose down && rmdir plow-credentials && $0 --local" >&2
    exit 1
  fi
  if [ ! -f plow-credentials ]; then
    ensure_login
    ensure_line
    echo "ligando…"
    plow mint "$line"
  fi
  python3 "$ROOT/skills/zoen/scripts/face.py" rename || true
  echo "ligando…"
  if ! docker compose up --build -d; then
    docker logout public.ecr.aws >/dev/null 2>&1 || true
    docker compose up --build -d
  fi
else
  ensure_login
  ensure_line
  echo "ligando…"
  plow deploy "$IMAGE" --line "$line"
  n=0
  st=""
  while [ "$n" -lt 36 ]; do
    st=$(plow agents | awk -F '\t' -v line="$line" '$1==line { print $3; exit }')
    case "$st" in
      running) break ;;
      failed*)
        echo "não subiu: $st" >&2
        exit 1
        ;;
    esac
    n=$((n + 1))
    sleep 5
  done
  case "$st" in
    running) ;;
    *)
      echo "ainda não subiu. rode: ./bin/plow-agents agents" >&2
      exit 1
      ;;
  esac
fi

echo
plow lines
echo
echo "Pronto. Mande um iMessage."
