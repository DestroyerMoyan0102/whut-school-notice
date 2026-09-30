@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   WHUT School Notice - Install scheduled task
echo ------------------------------------------------------------
echo   Task name : WHUT_SchoolNotice
echo   Schedule  : every day at 12:00
echo   Catch-up  : if the PC was off or offline, run ASAP after
echo   Working on: D: drive (script, state file, cache)
echo ============================================================
echo.

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%ProgramFiles%\Python313\python.exe" set "PY=%ProgramFiles%\Python313\python.exe"
if not defined PY if exist "%ProgramFiles%\Python312\python.exe" set "PY=%ProgramFiles%\Python312\python.exe"

if not defined PY (
    echo [ERROR] Python 3 not found in the usual places.
    echo         Please install Python 3, or open this file with Notepad
    echo         and set the PY variable to your python.exe path.
    echo.
    pause
    exit /b 1
)

echo [OK] Using Python: %PY%
echo.

echo [..] Generating task.xml ...
"%PY%" "%~dp0make_task_xml.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to generate task.xml
    echo.
    pause
    exit /b 1
)

echo.
echo [..] Registering the scheduled task ...
schtasks /Create /TN "WHUT_SchoolNotice" /XML "%~dp0task.xml" /F
if errorlevel 1 goto failed

echo.
echo [OK] Scheduled task created successfully.
echo.
schtasks /Query /TN "WHUT_SchoolNotice" /FO LIST
echo.
echo ------------------------------------------------------------
echo  Done. The first automatic run is TOMORROW at 12:00.
echo  To run it right now, execute:
echo      schtasks /Run /TN "WHUT_SchoolNotice"
echo ------------------------------------------------------------
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Could not create the scheduled task.
echo         Please right-click this file, choose "Run as administrator",
echo         and run it again.
echo.
pause
exit /b 1
