@echo off
setlocal

echo ============================================================
echo   WHUT School Notice - Uninstall scheduled task
echo ------------------------------------------------------------
echo   This only deletes the scheduled task.
echo   It does NOT delete any files on D:\school_notice
echo   (your state.json, code and logs stay where they are).
echo ============================================================
echo.

schtasks /Query /TN "WHUT_SchoolNotice" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Task "WHUT_SchoolNotice" does not exist. Nothing to do.
    echo.
    pause
    exit /b 0
)

schtasks /Delete /TN "WHUT_SchoolNotice" /F
if errorlevel 1 (
    echo.
    echo [ERROR] Delete failed. Please right-click this file,
    echo         choose "Run as administrator", and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Scheduled task deleted.
echo.
pause
exit /b 0
