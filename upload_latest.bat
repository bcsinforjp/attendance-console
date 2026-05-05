@echo off
REM ============================================================
REM  upload_latest.bat   (Windows 10/11)
REM  - No admin rights, no PowerShell policy issues
REM  - Uses curl.exe (built into Windows 10 1803+)
REM  - All paths relative to this .bat file
REM
REM  Three SEPARATE flows in one script:
REM
REM    [A] Attendance PDFs                  → /api/v1/pdf/upload
REM        then trigger /api/v1/pdf/auto-upload?save=true
REM
REM    [B] Daily-packs フルキャスト Excel    → /api/v1/xlsx/upload
REM        then trigger /api/daily-packs/auto-extract-excel
REM
REM    [C] Send LINE card                   → /api/line/send-message
REM        Posts the same Buttons-Template card the web GUI sends
REM        (Reports / Gantt / Summary "Send to LINE" buttons), but
REM        uses the branded default card image on the Pi instead of
REM        a per-day screenshot. Tap target is /m/report or /m/summary
REM        — identical to the locked web flow.
REM
REM  Each flow is its own labelled subroutine and can be invoked
REM  independently — see "Run a specific flow" below.
REM
REM  IMPORTANT: flow [C] is INTENTIONALLY EXCLUDED from "all".
REM  A double-click of this .bat must NEVER spam LINE recipients;
REM  the LINE card is operator-triggered only via `line` arg.
REM
REM  HOW TO USE
REM    1. Put this .bat in a folder, e.g.  C:\AttendanceUpload\
REM    2. First run will create config.txt — edit it, paste your API key.
REM    3. Drop files into:
REM         C:\AttendanceUpload\watch\pdf\   ← attendance PDFs (.pdf)
REM         C:\AttendanceUpload\watch\xlsx\  ← daily-packs Excel (.xlsx/.xlsm)
REM    4. Double-click the .bat to run BOTH upload flows in order.
REM       (The LINE card is NOT sent by a double-click — see below.)
REM
REM  Run a specific flow only:
REM       upload_latest.bat pdf                          :: only flow [A]
REM       upload_latest.bat xlsx                         :: only flow [B]
REM       upload_latest.bat all                          :: [A]+[B] (default)
REM       upload_latest.bat line                         :: [C] attendance, yesterday
REM       upload_latest.bat line summary                 :: [C] summary,    yesterday
REM       upload_latest.bat line attendance 2026-05-03   :: [C] explicit date
REM       upload_latest.bat line summary    2026-05-03   :: [C] explicit date
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
    echo [INFO] Running BOTH upload flows — Attendance PDF then Daily-packs Excel
    echo [INFO] LINE flow is NOT included in "all" — run `upload_latest.bat line` to send.
    call :upload_pdf
    call :upload_xlsx
    goto :done
)
if /i "%MODE%"=="line" (
    echo [INFO] Running flow [C] only — Send LINE card
    call :DO_LINE "%~2" "%~3"
    goto :done
)
echo [ERROR] Unknown mode "%MODE%". Use: pdf ^| xlsx ^| all ^| line
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
REM  [C]  LINE FLOW  ──  send Buttons-Template card to recipients
REM
REM  Endpoint: POST /api/line/send-message   (no upload, no API key)
REM  Body:     {"report_date":"YYYY-MM-DD","type":"attendance"|"summary"}
REM
REM  Notes:
REM   - /api/line/* endpoints are intentionally UNAUTHENTICATED on
REM     this deployment (see API_APP_GUIDE.md §8.2). Do NOT add an
REM     X-API-Key header — the server rejects unknown auth shapes.
REM   - The recipient sees the same card the web GUI's "Send to LINE"
REM     buttons render, except the image is the branded default card
REM     (static/line_card_default/{attendance,summary}_card.jpg)
REM     instead of a screenshot.
REM   - Date defaults to YESTERDAY (operator usually sends after the
REM     day closes). Computed via PowerShell because cmd.exe's
REM     locale-dependent %date% parsing is unreliable across regions.
REM
REM  Args (positional, both optional):
REM    %1 = "attendance" | "summary"  (default: attendance)
REM    %2 = "YYYY-MM-DD"              (default: yesterday)
REM ============================================================
:DO_LINE
echo.
echo --- [C] LINE send flow ---
echo --- [C] LINE send flow --- >> "%LOG%"

REM --- arg 1: type ---
set "LINE_TYPE=%~1"
if "%LINE_TYPE%"=="" set "LINE_TYPE=attendance"
if /i not "%LINE_TYPE%"=="attendance" if /i not "%LINE_TYPE%"=="summary" (
    echo [ERROR] LINE type must be "attendance" or "summary" — got "%LINE_TYPE%"
    echo [ERROR] LINE type must be "attendance" or "summary" — got "%LINE_TYPE%" >> "%LOG%"
    exit /b 1
)

REM --- arg 2: report_date ---
REM PowerShell is the only reliable cross-locale way to do "yesterday in
REM YYYY-MM-DD" on Windows. cmd's %date% parsing breaks on JP/EU locales.
set "LINE_DATE=%~2"
if "%LINE_DATE%"=="" (
    for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"`) do set "LINE_DATE=%%D"
)
if "%LINE_DATE%"=="" (
    echo [ERROR] Could not compute yesterday's date and no date was passed.
    echo [ERROR] Could not compute yesterday's date and no date was passed. >> "%LOG%"
    exit /b 1
)

REM --- Build JSON body in a temp file ---
REM cmd.exe escaping of nested double-quotes inside `curl -d "..."` is
REM unreliable (carets, doubled quotes, parentheses inside if-blocks all
REM interact badly). Writing the body to a temp file and using
REM `--data-binary @file` sidesteps the entire mess.
set "LINE_BODY=%TEMP%\upload_latest_line_body.json"
> "%LINE_BODY%" echo {"report_date":"%LINE_DATE%","type":"%LINE_TYPE%"}

set "LINE_RESP=%TEMP%\upload_latest_line_resp.txt"
if exist "%LINE_RESP%" del "%LINE_RESP%" >nul 2>&1

echo Sending LINE card: type=%LINE_TYPE% date=%LINE_DATE%
echo Sending LINE card: type=%LINE_TYPE% date=%LINE_DATE% >> "%LOG%"
echo Endpoint: %BASE%/api/line/send-message >> "%LOG%"
echo Body: >> "%LOG%"
type "%LINE_BODY%" >> "%LOG%"
echo. >> "%LOG%"

REM -w prints HTTP status on its own line after the body so we can grep it.
curl -s -X POST ^
    -H "Content-Type: application/json" ^
    --data-binary "@%LINE_BODY%" ^
    -w "\nHTTP_STATUS=%%{http_code}\n" ^
    "%BASE%/api/line/send-message" > "%LINE_RESP%" 2>&1

REM Append response to main log
echo --- response --- >> "%LOG%"
type "%LINE_RESP%" >> "%LOG%"
echo --- /response --- >> "%LOG%"

REM Pull HTTP status out of the response file
set "LINE_HTTP="
for /f "tokens=2 delims==" %%S in ('findstr /b "HTTP_STATUS=" "%LINE_RESP%" 2^>nul') do set "LINE_HTTP=%%S"
if "%LINE_HTTP%"=="" set "LINE_HTTP=000"

if "%LINE_HTTP%"=="200" (
    echo [OK] LINE card sent — HTTP %LINE_HTTP% type=%LINE_TYPE% date=%LINE_DATE%
    echo [OK] LINE card sent — HTTP %LINE_HTTP% type=%LINE_TYPE% date=%LINE_DATE% >> "%LOG%"
) else (
    echo [ERROR] LINE send failed — HTTP %LINE_HTTP%. See %LOG%
    echo [ERROR] LINE send failed — HTTP %LINE_HTTP% type=%LINE_TYPE% date=%LINE_DATE% >> "%LOG%"
)

REM Cleanup temp body (keep response file for post-mortem if needed)
del "%LINE_BODY%" >nul 2>&1
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
