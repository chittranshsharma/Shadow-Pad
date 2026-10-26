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
echo 2. Press A in the preview, then click PPSSPP during the 5-second countdown.
echo 3. Lean left/right, rise to jump, dip to duck.
echo 4. Hands at chest: left/right forward or inward punch = Square/Triangle.
echo    Left/right downward hand strike = Cross/Circle. Hold 1/4 sec, return to guard.
echo    Preview should show hands 2/2; Tab explains missing wrists.
echo Ctrl+Alt+P pauses or arms directly. Focus loss pauses and releases inputs.
echo Q/Esc in the preview exits.
".venv\Scripts\python.exe" webcam_tracker.py --control %*
set "tracker_exit=%errorlevel%"
if not "%tracker_exit%"=="0" pause
popd
exit /b %tracker_exit%
