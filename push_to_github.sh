#!/usr/bin/env bash
set -e
echo "=========================================================="
echo " Agent Sync - Push to GitHub"
echo " (token supported: GIT_TOKEN / GH_TOKEN / token.txt)"
echo "=========================================================="

if [ ! -d agent-sync ]; then
  git clone agent-sync.bundle agent-sync
fi
cd agent-sync
git remote set-url origin https://github.com/liuliucomputer/agent-sync.git

# --- 决定 token 来源（优先 GIT_TOKEN / token.txt，纯 git 推送）---
TOKEN="${GIT_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f token.txt ]; then
  TOKEN="$(head -n1 token.txt)"
fi

if [ -n "$TOKEN" ]; then
  echo "[info] Using token (pure git, no gh needed)"
  git remote set-url origin "https://liuliucomputer:${TOKEN}@github.com/liuliucomputer/agent-sync.git"
  echo "[info] Pushing... (create repo 'agent-sync' on GitHub first if it does not exist)"
  git push -u origin master
  echo "[OK] Pushed to https://github.com/liuliucomputer/agent-sync"
  exit 0
fi

# --- 无 GIT_TOKEN：尝试 GH_TOKEN 或交互式 gh ---
if [ -n "${GH_TOKEN:-}" ]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "[ERROR] gh not found. Install from https://cli.github.com or use GIT_TOKEN."
    exit 1
  fi
  echo "[info] Using GH_TOKEN"
  echo "$GH_TOKEN" | gh auth login --with-token -h github.com
  gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>/dev/null || true
  git push -u origin master
  echo "[OK] Pushed to https://github.com/liuliucomputer/agent-sync"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "[ERROR] No token and no gh. Set GIT_TOKEN / GH_TOKEN, or install gh."
  exit 1
fi
gh auth status >/dev/null 2>&1 || { echo "[ACTION] Login first: gh auth login -h github.com"; exit 1; }
gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>/dev/null || true
git push -u origin master
echo "[OK] Pushed to https://github.com/liuliucomputer/agent-sync"
