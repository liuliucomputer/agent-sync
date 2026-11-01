@echo off
chcp 65001 >nul 2>&1
echo ============================================================
echo  Agent Sync - Push to GitHub
echo  (token supported: GIT_TOKEN / GH_TOKEN / token.txt)
echo ============================================================
setlocal EnableDelayedExpansion

if not exist agent-sync (
  git clone agent-sync.bundle agent-sync
  if errorlevel 1 ( echo [ERROR] bundle clone failed. Keep agent-sync.bundle next to this script. & pause & exit /b 1 )
) else ( echo [skip] agent-sync folder already exists )
cd agent-sync
git remote set-url origin https://github.com/liuliucomputer/agent-sync.git

REM --- 决定 token 来源 ---
set TOKEN=
if defined GIT_TOKEN set TOKEN=!GIT_TOKEN!
if exist token.txt ( set /p TOKEN=<token.txt )

if defined TOKEN (
  echo [info] Using token (pure git, no gh needed)
  git remote set-url origin https://liuliucomputer:!TOKEN!@github.com/liuliucomputer/agent-sync.git
  echo [info] Pushing... (if repo does not exist yet, create it first at https://github.com/new )
  git push -u origin master
  if errorlevel 1 (
    echo [ERROR] Push failed. If the repo 'agent-sync' does not exist, create it at:
    echo   https://github.com/new   (Repository name: agent-sync, Public)
    echo then re-run this script.
    pause & exit /b 1
  )
  echo [OK] Pushed to https://github.com/liuliucomputer/agent-sync
  pause & exit /b 0
)

REM --- 无 GIT_TOKEN：尝试 GH_TOKEN 或交互式 gh ---
if defined GH_TOKEN (
  where gh >nul 2>nul || ( echo [ERROR] gh not found. Install from https://cli.github.com or use GIT_TOKEN & pause & exit /b 1 )
  echo [info] Using GH_TOKEN
  echo !GH_TOKEN! | gh auth login --with-token -h github.com
  gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>nul
  git push -u origin master
  if errorlevel 1 ( echo [ERROR] Push failed. Check network / permissions. & pause & exit /b 1 )
  echo [OK] Pushed to https://github.com/liuliucomputer/agent-sync
  pause & exit /b 0
)

where gh >nul 2>nul || ( echo [ERROR] gh not found. Install or set GIT_TOKEN/GH_TOKEN. & pause & exit /b 1 )
gh auth status >nul 2>nul || ( echo [ACTION] Login first: gh auth login -h github.com & pause & exit /b 1 )
gh repo create agent-sync --public --description "Agent Sync - multi AI agent conversation sync (web edition)" 2>nul
git push -u origin master
if errorlevel 1 ( echo [ERROR] Push failed. & pause & exit /b 1 )
echo [OK] Pushed to https://github.com/liuliucomputer/agent-sync
pause
