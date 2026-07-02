#!/usr/bin/env bash
# Auto-deploy: pulls new commits on main and restarts the bot if anything changed.
# Run periodically by erezbot-deploy.timer; safe to run by hand too. Exits quietly
# when already up to date, so the journal only shows lines when a deploy happened.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/ErezBot}"
BRANCH="main"
SERVICE="erezbot"

cd "$REPO_DIR"
git fetch origin "$BRANCH" --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

echo "New commits on $BRANCH: $(git rev-parse --short HEAD) -> $(git rev-parse --short "origin/$BRANCH")"
# reset --hard instead of pull: unattended-safe even after a force-push, and the server
# should never have local edits anyway. Untracked state (.env, credentials.json,
# token.json, memory.db) is not touched by reset.
git reset --hard "origin/$BRANCH" --quiet
"$REPO_DIR/.venv/bin/pip" install -r requirements.txt --quiet
sudo systemctl restart "$SERVICE"
echo "Deployed $(git rev-parse --short HEAD) and restarted $SERVICE"
