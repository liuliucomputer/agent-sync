#!/usr/bin/env bash
set -e
echo "=========================================================="
echo " Agent Sync - Push to GitHub"
echo " Run on a machine that can REACH github.com (VPN if needed)"
echo "=========================================================="

if ! command -v gh >/dev/null 2>&1; then
  echo "[ERROR] GitHub CLI (gh) not found. Install from https://cli.github.com"
  exit 1
fi

if [ ! -d agent-sync ]; then
  git clone agent-sync.bundle agent-sync
fi
cd agent-sync
git remote set-url origin https://github.com/liuliucomputer/agent-sync.git

if ! gh auth status >/dev/null 2>&1; then
  echo "[ACTION] Please login first:  gh auth login -h github.com"
  exit 1
fi

echo "[info] Creating repo on GitHub (ignore if it already exists)..."
gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>/dev/null || true

echo "[info] Pushing to GitHub..."
git push -u origin master
echo "[OK] Pushed to https://github.com/liuliucomputer/agent-sync"
