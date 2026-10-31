#!/usr/bin/env bash
# Start all four local target servers in the background and wait for health.
#
# Loads DEEPSEEK_API_KEY from the repo-root .env and passes it ONLY through the
# environment (never printed, never written to a file). Logs go to targets/.run.
# Each server binds 127.0.0.1 only. Safe to re-run: it stops any old instances
# first.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
RUN="$HERE/.run"
RAG_PY="$REPO/data/raw/targets/.venv-rag/bin/python"
DVLA_PY="$REPO/data/raw/targets/.venv-dvla/bin/python"
mkdir -p "$RUN"

# Load the API key into the environment without echoing it.
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
fi
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "ERROR: DEEPSEEK_API_KEY not set (expected in $REPO/.env)" >&2
  exit 1
fi

"$HERE/stop.sh" >/dev/null 2>&1 || true

start_one() {
  local name="$1" port="$2"; shift 2
  echo "starting $name on port $port ..."
  ( cd "$REPO" && exec "$@" ) >"$RUN/$name.log" 2>&1 &
  echo $! >"$RUN/$name.pid"
}

# Three campus RAG cases (DECISIONS.md D9) + the DVLA agent.
start_one rag_poisoned 8101 "$RAG_PY" "$HERE/rag_server.py" \
  --name campus_poisoned --corpus poisoned --prompt stock    --port 8101
start_one rag_clean    8102 "$RAG_PY" "$HERE/rag_server.py" \
  --name campus_clean    --corpus clean    --prompt stock    --port 8102
start_one rag_hardened  8104 "$RAG_PY" "$HERE/rag_server.py" \
  --name campus_hardened --corpus poisoned --prompt hardened --port 8104
start_one dvla         8103 "$DVLA_PY" "$HERE/dvla_server.py"

wait_health() {
  local port="$1" name="$2" tries=120
  for _ in $(seq 1 "$tries"); do
    if curl -sf "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      echo "  UP   $name  http://127.0.0.1:$port"
      return 0
    fi
    # Give up early if the process died (e.g. import error).
    if [ -f "$RUN/$name.pid" ] && ! kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
      echo "  DOWN $name  (process exited -- see $RUN/$name.log)"
      return 1
    fi
    sleep 1
  done
  echo "  DOWN $name  (no /health after ${tries}s -- see $RUN/$name.log)"
  return 1
}

echo
echo "waiting for health (the RAG servers download an embedding model on first run)..."
rc=0
wait_health 8101 rag_poisoned || rc=1
wait_health 8102 rag_clean    || rc=1
wait_health 8104 rag_hardened || rc=1
wait_health 8103 dvla         || rc=1
echo
if [ "$rc" -eq 0 ]; then
  echo "all four targets are UP."
else
  echo "one or more targets are DOWN; check the logs in $RUN."
fi
exit "$rc"
