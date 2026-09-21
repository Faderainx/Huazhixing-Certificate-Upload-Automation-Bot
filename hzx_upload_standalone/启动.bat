@echo off

set "PY=python"

set "PKG=%~dp0.."

cd /d "%~dp0"

echo ============================================================

echo  HuaZhiXing Certificate Upload - Standalone

echo  Default mode: DRY-RUN (no real upload, safe preview).

echo  To upload for real: remove " --dry-run" from the line below.

echo ============================================================

"%PY%" main.py --task-package "%PKG%" --level1 --level2 --dry-run

pause

