#!/bin/zsh
# Daily refresh of profile stat cards. Runs from launchd
# (~/Library/LaunchAgents/com.lincode.github-profile-stats.plist).
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "$(dirname "$0")/.."

git pull --rebase --quiet origin main
python3 scripts/update_stats.py

if ! git diff --quiet -- assets; then
    git add assets
    git commit --quiet -m "chore: refresh profile stat cards [auto]"
    git push --quiet origin main
    echo "$(date '+%Y-%m-%d %H:%M') pushed fresh cards"
else
    echo "$(date '+%Y-%m-%d %H:%M') no changes"
fi
