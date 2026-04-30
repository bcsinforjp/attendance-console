@echo off
REM ============================================================
REM  upload_latest.bat   (Windows 10/11)
REM  - No admin rights, no PowerShell policy issues
REM  - Uses curl.exe (built into Windows 10 1803+)
REM  - All paths relative to this .bat file
REM
REM  Two SEPARATE upload flows in one script:
REM
REM    [A] Attendance PDFs                  → /api/v1/pdf/upload
REM        then trigger /api/v1/pdf/auto-upload?save=true
REM
REM    [B] Daily-packs フルキャスト Excel    → /api/v1/xlsx/upload
REM        then trigger /api/daily-packs/auto-extract-excel
REM
REM  Each flow is its own labelled subroutine and can be invoked
REM  independently — see "Run a specific flow" below.
REM
REM  HOW TO USE
REM    1. Put this .bat in a folder, e.g.  C:\AttendanceUpload\
REM    2. First run will create config.txt — edit it, paste your API key.
REM    3. Drop files into:
REM         C:\AttendanceUpload\watch\pdf\   ← attendance PDFs (.pdf)
REM         C:\AttendanceUpload\watch\xlsx\  ← daily-packs Excel (.xlsx/.xlsm)
REM    4. Double-click the .bat to run BOTH flows in order.
REM
REM  Run a specific flow only:
REM       upload_latest.bat pdf      :: only flow [A]
REM       upload_latest.bat xlsx     :: only flow [B]
REM       upload_latest.bat all      :: both (default)
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CONFIG=%~dp0config.txt"
set "WATCH_PDF=%~dp0watch\pdf"
set "WATCH_XLSX=%~dp0watch\xlsx"
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

if not exist "%WATCH_PDF%"  mkdir "%WATCH_PDF%"
if not exist "%WATCH_XLSX%" mkdir "%WATCH_XLSX%"

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

REM --- Ping server -------------------------------------------
echo Pinging %BASE% ...
curl -s -H "X-API-Key: %KEY%" "%BASE%/api/v1/ping" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Server not reachable. See %LOG%
    pause
    exit /b 1
)

REM --- Decide which flow(s) to run ---------------------------
REM CMD parsing note: the `&` operator runs the next statement
REM UNCONDITIONALLY — it is NOT gated by the preceding `if`. So we
REM MUST wrap each branch in parentheses to keep the `goto :done`
REM inside the conditional. Without the parens, `goto :done` runs
REM after the first `if` check regardless of the result and the
REM later branches never execute.
set "MODE=%1"
if "%MODE%"=="" set "MODE=all"

if /i "%MODE%"=="pdf" (
    echo [INFO] Running flow [A] only — Attendance PDF
    call :upload_pdf
    goto :done
)
if /i "%MODE%"=="xlsx" (
    echo [INFO] Running flow [B] only — Daily-packs Excel
    call :upload_xlsx
    goto :done
)
if /i "%MODE%"=="all" (
    echo [INFO] Running BOTH flows — Attendance PDF then Daily-packs Excel
    call :upload_pdf
    call :upload_xlsx
    goto :done
)
echo [ERROR] Unknown mode "%MODE%". Use: pdf ^| xlsx ^| all
pause
exit /b 1

:done
echo. >> "%LOG%"
echo ===== DONE ===== >> "%LOG%"
echo Done. Log: %LOG%
endlocal
exit /b 0


REM ============================================================
REM  [A]  PDF FLOW  ──  attendance PDFs
REM
REM  Steps:
REM    1. Walk %WATCH_PDF% in newest-first order
REM    2. Upload up to %PDF_COUNT% files to /api/v1/pdf/upload
REM    3. Trigger /api/v1/pdf/auto-upload?save=true
REM ============================================================
:upload_pdf
echo.
echo --- [A] Attendance PDF flow ---
echo --- [A] Attendance PDF flow --- >> "%LOG%"
set /a n_pdf=0
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_PDF%\*.pdf" 2^>nul') do (
    set /a n_pdf+=1
    if !n_pdf! leq %PDF_COUNT% (
        echo Uploading PDF: %%F
        echo Uploading PDF: %%F >> "%LOG%"
        curl -s -X POST ^
            -H "X-API-Key: %KEY%" ^
            -F "file=@%WATCH_PDF%\%%F;type=application/pdf" ^
            "%BASE%/api/v1/pdf/upload" >> "%LOG%" 2>&1
        echo. >> "%LOG%"
    )
)
if %n_pdf%==0 (
    echo No .pdf files in %WATCH_PDF%
    echo No .pdf files in %WATCH_PDF% >> "%LOG%"
    goto :eof
)
echo Triggering attendance auto-update...
echo Triggering /api/v1/pdf/auto-upload?save=true >> "%LOG%"
curl -s -X POST -H "X-API-Key: %KEY%" ^
    "%BASE%/api/v1/pdf/auto-upload?save=true" >> "%LOG%" 2>&1
echo. >> "%LOG%"
goto :eof


REM ============================================================
REM  [B]  XLSX FLOW  ──  daily-packs フルキャスト Excel
REM
REM  Steps:
REM    1. Walk %WATCH_XLSX% in newest-first order
REM    2. Upload the most recent .xlsx/.xlsm to /api/v1/xlsx/upload
REM    3. Trigger /api/daily-packs/auto-extract-excel
REM       (server picks the latest file in its watched folder, parses,
REM        returns preview — same flow as the console "Auto-update" button)
REM ============================================================
:upload_xlsx
echo.
echo --- [B] Daily-packs Excel flow ---
echo --- [B] Daily-packs Excel flow --- >> "%LOG%"
set "PICKED_XLSX="
for /f "delims=" %%F in ('dir /b /o:-d /a:-d "%WATCH_XLSX%\*.xlsx" "%WATCH_XLSX%\*.xlsm" 2^>nul') do (
    if not defined PICKED_XLSX set "PICKED_XLSX=%%F"
)
if not defined PICKED_XLSX (
    echo No .xlsx/.xlsm files in %WATCH_XLSX%
    echo No .xlsx/.xlsm files in %WATCH_XLSX% >> "%LOG%"
    goto :eof
)
echo Uploading Excel: %PICKED_XLSX%
echo Uploading Excel: %PICKED_XLSX% >> "%LOG%"
curl -s -X POST ^
    -H "X-API-Key: %KEY%" ^
    -F "file=@%WATCH_XLSX%\%PICKED_XLSX%" ^
    "%BASE%/api/v1/xlsx/upload" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo Triggering daily-packs Excel auto-extract...
echo Triggering /api/daily-packs/auto-extract-excel >> "%LOG%"
curl -s -X POST -H "X-API-Key: %KEY%" ^
    "%BASE%/api/daily-packs/auto-extract-excel" >> "%LOG%" 2>&1
echo. >> "%LOG%"
goto :eof


REM ============================================================
REM  SCHEDULE WITHOUT ADMIN RIGHTS
REM  Open a normal CMD window (no admin) and run ONE of these:
REM
REM    Daily at 09:00 — both flows:
REM      schtasks /create /tn "AttendanceUpload" ^
REM        /tr "\"%~dp0upload_latest.bat\"" ^
REM        /sc daily /st 09:00 /f
REM
REM    Daily at 09:00 — PDF flow only:
REM      schtasks /create /tn "AttendanceUploadPDF" ^
REM        /tr "\"%~dp0upload_latest.bat\" pdf" ^
REM        /sc daily /st 09:00 /f
REM
REM    Daily at 09:30 — Excel flow only:
REM      schtasks /create /tn "AttendanceUploadXLSX" ^
REM        /tr "\"%~dp0upload_latest.bat\" xlsx" ^
REM        /sc daily /st 09:30 /f
REM
REM  Run once now:   schtasks /run    /tn "AttendanceUpload"
REM  See it:         schtasks /query  /tn "AttendanceUpload"
REM  Remove it:      schtasks /delete /tn "AttendanceUpload" /f
REM ============================================================
