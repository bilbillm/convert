#!/usr/bin/env sh
# Keep the application running while this managed workspace remains active.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
child_pid=''
stop_service() {
    if [ -n "$child_pid" ]; then kill "$child_pid" 2>/dev/null || true; fi
    exit 0
}
trap stop_service TERM INT
while true; do
    "$PROJECT_DIR/run.sh" &
    child_pid=$!
    wait "$child_pid" || true
    child_pid=''
    sleep 3
done
