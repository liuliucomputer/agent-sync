@echo off
chcp 65001 >nul 2>&1
echo ============================================================
echo  Agent Sync - Push to GitHub
echo  Run on a machine that can REACH github.com (VPN if needed)
echo ============================================================
setlocal

where gh >nul 2>nul
if errorlevel 1 (
  echo [ERROR] GitHub CLI (gh) not found. Install from https://cli.github.com
  pause
  exit /b 1
)

if not exist agent-sync (
  git clone agent-sync.bundle agent-sync
  if errorlevel 1 (
    echo [ERROR] Failed to clone bundle. Make sure agent-sync.bundle is next to this script.
    pause
    exit /b 1
  )
) else (
  echo [skip] agent-sync folder already exists
)
cd agent-sync

git remote set-url origin https://github.com/liuliucomputer/agent-sync.git

gh auth status >nul 2>nul
if errorlevel 1 (
  echo [ACTION] Please login first:  gh auth login -h github.com
  echo Then run this script again.
  pause
  exit /b 1
)

echo [info] Creating repo on GitHub (ignore error if it already exists)...
gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>nul

echo [info] Pushing to GitHub...
git push -u origin master
if errorlevel 1 (
  echo [ERROR] Push failed. Check network / repo permissions.
  pause
  exit /b 1
)
echo [OK] Pushed to https://github.com/liuliucomputer/agent-sync
pause
