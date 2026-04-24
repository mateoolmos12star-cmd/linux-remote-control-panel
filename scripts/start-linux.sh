#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PORT="${REMOTE_PANEL_PORT:-${ENDEAVOUR_PANEL_PORT:-8787}}"
export REMOTE_PANEL_PORT="$PORT"

URL="http://localhost:$PORT"

if command -v curl >/dev/null 2>&1 && curl -fsS "$URL/api/state" >/dev/null 2>&1; then
  :
else
  if command -v python3 >/dev/null 2>&1; then
    python3 "$ROOT/server.py" >/tmp/linux-remote-control-panel.log 2>&1 &
  else
    python "$ROOT/server.py" >/tmp/linux-remote-control-panel.log 2>&1 &
  fi
  sleep 1
fi

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 &
else
  printf '%s\n' "$URL"
fi
