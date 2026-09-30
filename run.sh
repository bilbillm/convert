#!/usr/bin/env sh
set -eu
APP_PATH=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python "$APP_PATH/scripts/appserver.py"
