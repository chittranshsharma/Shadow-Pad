@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 first. See README.md.
    pause
    popd
    exit /b 1
)
echo ShadowPad movement controller
echo 1. In the camera preview, press C and sit still for two seconds.
echo 2. Click PPSSPP, then press Ctrl+Alt+P to arm or pause.
echo 3. Lean left/right, rise to jump, dip to duck.
echo Q/Esc in the preview exits. Focus loss pauses and releases inputs.
".venv\Scripts\python.exe" webcam_tracker.py --control %*
set "tracker_exit=%errorlevel%"
if not "%tracker_exit%"=="0" pause
popd
exit /b %tracker_exit%
