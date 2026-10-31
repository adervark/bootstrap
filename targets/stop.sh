#!/usr/bin/env bash
# Stop all three target servers started by start.sh (by their pid files).
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$HERE/.run"

stopped=0
for name in rag_poisoned rag_clean rag_hardened dvla; do
  pidfile="$RUN/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "stopped $name (pid $pid)"
      stopped=1
    fi
    rm -f "$pidfile"
  fi
done

[ "$stopped" -eq 0 ] && echo "no running targets found"
exit 0
