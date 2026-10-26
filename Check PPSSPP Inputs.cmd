@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 first. See README.md.
    pause
    popd
    exit /b 1
)
:menu
cls
echo ShadowPad - PPSSPP input check
echo Open Tekken Practice mode before testing.
echo.
echo 1. Left hold       2. Right hold
echo 3. Square          4. Triangle
echo 5. Cross           6. Circle
echo 7. Show bindings   8. Exit
echo.
choice /c 12345678 /n /m "Choose a test (you then have 3 seconds to click PPSSPP): "
set "selection=%errorlevel%"
if "%selection%"=="8" goto done
if "%selection%"=="7" (
    ".venv\Scripts\python.exe" input_check.py
    pause
    goto menu
)
set "test_button="
if "%selection%"=="1" set "test_button=Left"
if "%selection%"=="2" set "test_button=Right"
if "%selection%"=="3" set "test_button=Square"
if "%selection%"=="4" set "test_button=Triangle"
if "%selection%"=="5" set "test_button=Cross"
if "%selection%"=="6" set "test_button=Circle"
if not defined test_button goto menu
".venv\Scripts\python.exe" input_check.py --button %test_button% --run
pause
goto menu
:done
popd
exit /b 0
