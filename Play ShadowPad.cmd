@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 first. See README.md.
    pause
    popd
    exit /b 1
)
if not exist "models\gesture_recognizer.task" (
    ".venv\Scripts\python.exe" download_model.py --variant hands
    if errorlevel 1 (
        pause
        popd
        exit /b 1
    )
)
echo ShadowPad movement controller
echo 1. In the camera preview, press C and sit still for two seconds.
echo 2. Press A in the preview, then click PPSSPP during the 5-second countdown.
echo 3. Lean left/right, rise to jump, dip to duck.
echo 4. Hold a closed fist fully in view until READY, then punch straight forward.
echo    Left/right closed fist = Square/Triangle. Open-palm forward push = Cross/Circle.
echo    Return the hand after each attack. H resets guards; Tab shows diagnostics.
echo    Attack reach defaults to 1.6x; [ and ] adjust it in the preview.
echo    Test Gestures.cmd lets you check detections without sending game keys.
echo Ctrl+Alt+P pauses or arms directly. Focus loss pauses and releases inputs.
echo Q/Esc in the preview exits.
".venv\Scripts\python.exe" webcam_tracker.py --control %*
set "tracker_exit=%errorlevel%"
if not "%tracker_exit%"=="0" pause
popd
exit /b %tracker_exit%
