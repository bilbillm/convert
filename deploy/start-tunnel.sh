#!/usr/bin/env sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SECRET_DIR=${CONVERT_SECRET_DIR:-$PROJECT_DIR/.secrets}
BIN=${CHISEL_BIN:-$PROJECT_DIR/.local/bin/chisel}
# This file is generated locally and excluded from Git; never put credentials in arguments.
. "$SECRET_DIR/client.env"
export AUTH
FINGERPRINT=$(cat "$SECRET_DIR/fingerprint")
TUNNEL_PROXY=${HTTPS_PROXY:-${HTTP_PROXY:-}}
if [ -n "$TUNNEL_PROXY" ]; then
    exec "$BIN" client --proxy "$TUNNEL_PROXY" --fingerprint "$FINGERPRINT" \
        --keepalive 25s --max-retry-interval 15s \
        https://convert.lumoren.cn/_lumo_tunnel R:0.0.0.0:18000:127.0.0.1:8000
else
    exec "$BIN" client --fingerprint "$FINGERPRINT" --keepalive 25s --max-retry-interval 15s \
        https://convert.lumoren.cn/_lumo_tunnel R:0.0.0.0:18000:127.0.0.1:8000
fi
