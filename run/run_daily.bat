@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if defined PYTHON set "PY=%PYTHON%"
"%PY%" -m src.cli collect >> data\run.log 2>&1
"%PY%" -m src.cli script  >> data\run.log 2>&1
"%PY%" -m src.cli topics  >> data\run.log 2>&1
echo. >> data\run.log
