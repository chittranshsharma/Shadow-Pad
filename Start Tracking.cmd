@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 in PowerShell first. See README.md.
    pause
    popd
    exit /b 1
)
".venv\Scripts\python.exe" webcam_tracker.py %*
set "tracker_exit=%errorlevel%"
if not "%tracker_exit%"=="0" pause
popd
exit /b %tracker_exit%
