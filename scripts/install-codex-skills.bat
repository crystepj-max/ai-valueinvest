@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PYTHON_LAUNCHER=py -3"
) else (
  set "PYTHON_LAUNCHER=python"
)

%PYTHON_LAUNCHER% "%ROOT%\scripts\sync-codex-skills.py"
if errorlevel 1 exit /b %ERRORLEVEL%

%PYTHON_LAUNCHER% "%ROOT%\scripts\install-project-skills.py" "%ROOT%" codex
if errorlevel 1 exit /b %ERRORLEVEL%

echo Codex skills are available from this repository's .agents\skills directory.
echo Restart Codex to pick up new skills.
