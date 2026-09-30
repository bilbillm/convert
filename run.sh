#!/usr/bin/env sh
set -eu
APP_PATH=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python -m uvicorn main:app --app-dir "$APP_PATH" --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --workers 1
