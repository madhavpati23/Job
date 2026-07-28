@echo off
REM Daily job-search watch. Run by Windows Task Scheduler.
REM Uses this script's own folder, so the repo can live anywhere.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m jobapply_mcp.cli watch >> "data\watch.log" 2>&1
