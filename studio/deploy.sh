#!/bin/bash
# Deploy studio to the Lenovo (Pop!_OS): sync code, set up the venv, (re)start the service.
# usage: studio/deploy.sh [host]        first run also needs: SUDO_PASS=... for the systemd unit and tailscale serve
set -euo pipefail
HOST=${1:-chinmay@lenovo}
HERE=$(cd "$(dirname "$0")" && pwd)
rsync -az --delete --exclude __pycache__ --exclude .venv "$HERE/" "$HOST:studio/"
ssh "$HOST" 'set -e; cd ~/studio
  [ -x .venv/bin/python ] || ~/.local/bin/uv venv --python 3.14 .venv -q
  ~/.local/bin/uv pip install -q --python .venv/bin/python -r requirements.txt'
if [ -n "${SUDO_PASS:-}" ]; then
  ssh "$HOST" "echo '$SUDO_PASS' | sudo -S -p '' bash -c '
    cp ~chinmay/studio/studio.service /etc/systemd/system/studio.service
    systemctl daemon-reload && systemctl enable studio -q
    tailscale serve --bg --https=443 http://127.0.0.1:8790 >/dev/null'"
fi
ssh "$HOST" "echo '${SUDO_PASS:-}' | sudo -S -p '' systemctl restart studio 2>/dev/null || sudo -n systemctl restart studio"
sleep 3
curl -sf https://lenovo.tail0e5368.ts.net/health && echo
