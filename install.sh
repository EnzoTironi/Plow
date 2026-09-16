#!/bin/sh
# One command:
#   curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
# Or, inside a checkout: ./install.sh
set -eu

REPO="${ZOEN_REPO:-https://github.com/EnzoTironi/Plow.git}"
RUNNER="${ZOEN_RUNNER:-https://github.com/plow-pbc/plow-agents.git}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "falta $1." >&2
    exit 1
  }
}

need git
need python3
need docker
docker info >/dev/null 2>&1 || {
  echo "Abra o Docker e tente de novo." >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  echo "falta o Compose." >&2
  exit 1
}

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

if [ -d plow-credentials ] && [ ! -f plow-credentials ]; then
  echo "Algo ficou pela metade. Rode: docker compose down && rmdir plow-credentials && $0" >&2
  exit 1
fi

plow() {
  ./bin/plow-agents "$@"
}

if [ ! -f plow-credentials ]; then
  echo
  echo "Mande do celular exatamente a frase abaixo."
  echo
  plow login || plow login --new-line
  echo
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
  echo "ligando…"
  plow mint "$line"
fi

python3 "$ROOT/skills/zoen/scripts/face.py" rename || true

echo "ligando…"
if ! docker compose up --build -d; then
  docker logout public.ecr.aws >/dev/null 2>&1 || true
  docker compose up --build -d
fi

echo
echo "Pronto. Mande um iMessage."
