#!/usr/bin/env bash
# deploy.sh — run ON the server after pushing to GitHub
# Usage: ssh tecviva@100.81.66.33 -p 2223 -i ~/.ssh/harmonykey "cd ~/analytical-dashboards && bash dashboard/deploy.sh"

set -euo pipefail

REPO_DIR="/home/tecviva/analytical-dashboards"
DASH_DIR="$REPO_DIR/dashboard"
VENV_DIR="$DASH_DIR/venv"
SERVICE="eth-dashboard"

echo "=== ETH Dashboard deploy $(date) ==="

# 1. Pull latest code
cd "$REPO_DIR"
git pull origin main
echo "✓ git pull done"

# 2. Create virtualenv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "✓ virtualenv created"
fi

# 3. Install / upgrade Python deps
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$DASH_DIR/requirements.txt"
echo "✓ pip install done"

# 4. Ensure .env exists (never overwrite if present)
if [ ! -f "$DASH_DIR/.env" ]; then
    cp "$DASH_DIR/.env.example" "$DASH_DIR/.env"
    echo "⚠️  .env created from .env.example — fill in API keys before restarting"
fi

# 5. Install / refresh systemd service
sudo cp "$DASH_DIR/eth-dashboard.service" /etc/systemd/system/"$SERVICE".service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"
echo "✓ systemd service restarted"

# 6. Quick health check
sleep 3
if curl -sf http://localhost:5001/dashboard/health | grep -q '"ok"'; then
    echo "✓ health check passed"
else
    echo "✗ health check failed — check: sudo journalctl -u $SERVICE -n 50"
    exit 1
fi

echo "=== deploy complete ==="
