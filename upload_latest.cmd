@echo off
REM ============================================================
REM  upload_latest.cmd
REM  Uploads the most recently added PDF(s) and Excel file from
REM  a local Windows folder to the Attendance server.
REM
REM  Usage:
REM    1. Edit KEY, WATCH_DIR, BASE below.
REM    2. Run manually:        upload_latest.cmd
REM    3. Schedule daily 09:00: see SCHTASKS line at bottom.
REM ============================================================

setlocal enabledelayedexpansion

REM --- CONFIG -------------------------------------------------
set "KEY=YOUR_API_KEY_HERE"
set "BASE=https://rnd.asiakawaii.com/attendance"
set "WATCH_DIR=C:\Company_Data\03_就業日報PDF"
set "LOG=%WATCH_DIR%\upload_log.txt"
REM How many most-recent PDFs to upload (e.g. 2 = today's two PDFs)
set "PDF_COUNT=2"
REM ------------------------------------------------------------

echo. >> "%LOG%"
echo ===== %date% %time% ===== >> "%LOG%"

REM --- 1. Ping server ----------------------------------------
curl -s -H "X-API-Key: %KEY%" "%BASE%/api/v1/ping" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Server not reachable >> "%LOG%"
    exit /b 1
)

REM --- 2. Upload the N most recently modified PDFs -----------
set /a n=0
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_DIR%\*.pdf" 2^>nul') do (
    set /a n+=1
    if !n! leq %PDF_COUNT% (
        echo Uploading PDF: %%F >> "%LOG%"
        curl -s -X POST ^
            -H "X-API-Key: %KEY%" ^
            -F "file=@%WATCH_DIR%\%%F;type=application/pdf" ^
            "%BASE%/api/v1/pdf/upload" >> "%LOG%" 2>&1
        echo. >> "%LOG%"
    )
)

REM --- 3. Upload the single most recent Excel file -----------
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_DIR%\*.xlsx" "%WATCH_DIR%\*.xls" 2^>nul') do (
    echo Uploading Excel: %%F >> "%LOG%"
    curl -s -X POST ^
        -H "X-API-Key: %KEY%" ^
        -F "file=@%WATCH_DIR%\%%F" ^
        "%BASE%/api/v1/pdf/upload" >> "%LOG%" 2>&1
    echo. >> "%LOG%"
    goto :done_excel
)
:done_excel

REM --- 4. Trigger server-side Auto-update (preview + save) ---
echo Triggering auto-update... >> "%LOG%"
curl -s -X POST -H "X-API-Key: %KEY%" ^
    "%BASE%/api/v1/pdf/auto-upload?save=true" >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo ===== DONE ===== >> "%LOG%"
endlocal
exit /b 0

REM ============================================================
REM  SCHEDULE THIS TO RUN AT A SPECIFIC TIME (e.g. 09:00 daily)
REM  Open CMD as Administrator and run:
REM
REM    schtasks /create /tn "AttendanceUpload" ^
REM      /tr "C:\path\to\upload_latest.cmd" ^
REM      /sc daily /st 09:00 /rl highest /f
REM
REM  Run once for testing:
REM    schtasks /run /tn "AttendanceUpload"
REM
REM  Delete the schedule:
REM    schtasks /delete /tn "AttendanceUpload" /f
REM ============================================================
