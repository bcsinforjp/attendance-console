@echo off
REM ============================================================
REM  upload_latest.bat   (works on any Windows 10/11 PC)
REM  - No admin rights needed
REM  - No PowerShell execution-policy issues
REM  - Uses curl.exe (built into Windows 10 1803+ and Windows 11)
REM  - All paths relative to this .bat file
REM
REM  HOW TO USE
REM    1. Put this .bat in a folder, e.g.  C:\AttendanceUpload\
REM    2. Create subfolder:                 C:\AttendanceUpload\watch\
REM       Drop your PDFs and Excel files there.
REM    3. First run will create config.txt - edit it, put your API key.
REM    4. Double-click the .bat to run.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CONFIG=%~dp0config.txt"
set "WATCH_DIR=%~dp0watch"
set "LOG=%~dp0upload_log.txt"

REM --- First-run setup ---------------------------------------
if not exist "%CONFIG%" (
    echo Creating default config.txt ...
    > "%CONFIG%" echo KEY=YOUR_API_KEY_HERE
    >>"%CONFIG%" echo BASE=https://rnd.asiakawaii.com/attendance
    >>"%CONFIG%" echo PDF_COUNT=2
    echo.
    echo  Please open config.txt, paste your API key, then run again.
    echo  Config file: %CONFIG%
    pause
    exit /b 0
)

if not exist "%WATCH_DIR%" mkdir "%WATCH_DIR%"

REM --- Load config -------------------------------------------
for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG%") do (
    set "%%A=%%B"
)

REM --- Check curl is available -------------------------------
where curl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] curl.exe not found. Needs Windows 10 1803+ or Windows 11.
    pause
    exit /b 1
)

echo. >> "%LOG%"
echo ===== %date% %time% ===== >> "%LOG%"
echo Watch folder: %WATCH_DIR% >> "%LOG%"

REM --- 1. Ping server ----------------------------------------
echo Pinging %BASE% ...
curl -s -H "X-API-Key: %KEY%" "%BASE%/api/v1/ping" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Server not reachable. See %LOG%
    exit /b 1
)

REM --- 2. Upload N most recent PDFs --------------------------
set /a n=0
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_DIR%\*.pdf" 2^>nul') do (
    set /a n+=1
    if !n! leq %PDF_COUNT% (
        echo Uploading PDF: %%F
        echo Uploading PDF: %%F >> "%LOG%"
        curl -s -X POST ^
            -H "X-API-Key: %KEY%" ^
            -F "file=@%WATCH_DIR%\%%F;type=application/pdf" ^
            "%BASE%/api/v1/pdf/upload" >> "%LOG%" 2>&1
        echo. >> "%LOG%"
    )
)

REM --- 3. Upload most recent Excel ---------------------------
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_DIR%\*.xlsx" "%WATCH_DIR%\*.xls" 2^>nul') do (
    echo Uploading Excel: %%F
    echo Uploading Excel: %%F >> "%LOG%"
    curl -s -X POST ^
        -H "X-API-Key: %KEY%" ^
        -F "file=@%WATCH_DIR%\%%F" ^
        "%BASE%/api/v1/pdf/upload" >> "%LOG%" 2>&1
    echo. >> "%LOG%"
    goto :done_excel
)
:done_excel

REM --- 4. Trigger server-side auto-update --------------------
echo Triggering auto-update...
curl -s -X POST -H "X-API-Key: %KEY%" ^
    "%BASE%/api/v1/pdf/auto-upload?save=true" >> "%LOG%" 2>&1

echo Done. Log: %LOG%
echo ===== DONE ===== >> "%LOG%"
endlocal
exit /b 0

REM ============================================================
REM  SCHEDULE WITHOUT ADMIN RIGHTS
REM  Open a normal CMD window (no admin) and run ONE of these:
REM
REM    Daily at 09:00:
REM      schtasks /create /tn "AttendanceUpload" ^
REM        /tr "\"%~dp0upload_latest.bat\"" ^
REM        /sc daily /st 09:00 /f
REM
REM    Every weekday at 18:30:
REM      schtasks /create /tn "AttendanceUpload" ^
REM        /tr "\"C:\AttendanceUpload\upload_latest.bat\"" ^
REM        /sc weekly /d MON,TUE,WED,THU,FRI /st 18:30 /f
REM
REM  Run once now:   schtasks /run    /tn "AttendanceUpload"
REM  See it:         schtasks /query  /tn "AttendanceUpload"
REM  Remove it:      schtasks /delete /tn "AttendanceUpload" /f
REM ============================================================
