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
echo ShadowPad gesture practice - no game keys are sent.
echo Press C and sit still for two seconds, then press A to start.
echo Hold a fist near your chest until READY, punch straight forward, then return.
echo Use a forward open-palm push for the same-side kick button.
echo Check that each movement increments only its matching counter once.
echo H resets hand guards. A pauses/resumes practice. Q/Esc exits.
".venv\Scripts\python.exe" webcam_tracker.py --practice %*
set "tracker_exit=%errorlevel%"
if not "%tracker_exit%"=="0" pause
popd
exit /b %tracker_exit%
