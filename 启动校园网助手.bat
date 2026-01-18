@echo off
setlocal EnableDelayedExpansion

:: Initialize Log File (Using English to prevent mojibake)
set "LOG_FILE=debug_log.txt"
echo [%date% %time%] Script Started > "%LOG_FILE%"

:: Change code page to UTF-8
chcp 65001 >> "%LOG_FILE%" 2>&1

title GDIPU Network AutoLogin Helper
cd /d "%~dp0"
echo [Info] Working Directory: %cd% >> "%LOG_FILE%"

echo ==========================================
echo   Campus Network AutoLogin (GDIPU Version)
echo ==========================================
echo.

:: ==============================
:: Step 1: Check Environment
:: ==============================
echo [Step 1] Checking Python Environment... >> "%LOG_FILE%"

:: 1. Check for Embedded Python
if exist "python_runtime\python.exe" (
    echo [Env] Found local Python runtime. >> "%LOG_FILE%"
    set "PYTHON_CMD=python_runtime\python.exe"
    goto :VERIFY_PYTHON
)

:: 2. Check for System Python
python --version >> "%LOG_FILE%" 2>&1
if %errorlevel% equ 0 (
    echo [Env] Found system Python. >> "%LOG_FILE%"
    set "PYTHON_CMD=python"
    goto :VERIFY_PYTHON
)

:: 3. Download Python if missing
echo [Env] Python not found. Downloading... >> "%LOG_FILE%"
echo [Info] Python not found, downloading from Huawei Cloud Mirror...

if not exist "python_runtime" mkdir python_runtime

powershell -NoProfile -Command "& { try { $url = 'https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-embed-amd64.zip'; $dest = 'python_runtime\python.zip'; Write-Host 'Downloading...'; Invoke-WebRequest -Uri $url -OutFile $dest -ErrorAction Stop; Write-Host 'Unzipping...'; Expand-Archive -Path $dest -DestinationPath 'python_runtime' -Force -ErrorAction Stop; Remove-Item $dest -ErrorAction SilentlyContinue; Write-Host 'Configuring...'; $pth = 'python_runtime\python310._pth'; $c = Get-Content $pth; $c | ForEach-Object { if ($_ -match '#import site') { 'import site' } else { $_ } } | Set-Content $pth; Add-Content $pth '..'; Add-Content $pth '..\libs'; exit 0 } catch { Write-Error $_; exit 1 } }" >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo [Error] PowerShell download script failed. >> "%LOG_FILE%"
    echo [Error] Download failed! Please check debug_log.txt.
    pause
    exit /b
)

set "PYTHON_CMD=python_runtime\python.exe"

:VERIFY_PYTHON
:: 4. Verify if Python can actually run (Check for VC++ Redist issues)
echo [Info] Verifying Python execution: %PYTHON_CMD% --version >> "%LOG_FILE%"
"%PYTHON_CMD%" --version >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo.
    echo [CRITICAL ERROR] Python failed to start!
    echo [CRITICAL ERROR] Python failed to start! >> "%LOG_FILE%"
    echo.
    echo ================================================================
    echo Possible Cause: Missing Microsoft Visual C++ Redistributable.
    echo This is common on fresh Windows installations.
    echo.
    echo Please download and install "VC_redist.x64.exe" from Microsoft.
    echo Link: https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo ================================================================
    echo.
    echo [Tip] Log file saved to debug_log.txt
    pause
    exit /b
)

:: ==============================
:: Step 2: Check Dependencies
:: ==============================
:CHECK_LIBS
echo [Step 2] Checking Libraries... >> "%LOG_FILE%"

if exist "libs\flask" (
    echo [Libs] Flask found locally. Skipping install. >> "%LOG_FILE%"
    goto :START_SERVICE
)

echo [Libs] Installing dependencies...
if not exist "libs" mkdir libs

if "%PYTHON_CMD%"=="python" (
    set "PIP_CMD=python -m pip"
) else (
    if not exist "python_runtime\Scripts\pip.exe" (
        echo [Info] Downloading get-pip.py... >> "%LOG_FILE%"
        echo [Info] Initializing pip for embedded Python...
        powershell -Command "Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'python_runtime\get-pip.py'" >> "%LOG_FILE%" 2>&1
        "%PYTHON_CMD%" python_runtime\get-pip.py --no-warn-script-location >> "%LOG_FILE%" 2>&1
        del python_runtime\get-pip.py
    )
    set "PIP_CMD=%PYTHON_CMD% -m pip"
)

echo [Info] Running pip install... >> "%LOG_FILE%"
"%PIP_CMD%" install flask requests pystray Pillow --target=./libs -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo [Error] Pip install failed. Check log. >> "%LOG_FILE%"
    echo [Error] Failed to install libraries! See debug_log.txt.
    pause
    exit /b
)

:: ==============================
:: Step 3: Start Service
:: ==============================
:START_SERVICE
echo [Step 3] Starting Service... >> "%LOG_FILE%"

start "" "%PYTHON_CMD%" web_ui.py
if %errorlevel% neq 0 (
    echo [Error] Failed to launch web_ui.py >> "%LOG_FILE%"
    echo [Error] Failed to start application.
    pause
    exit /b
)

echo [Success] Service started. >> "%LOG_FILE%"

echo.
echo ==========================================
echo  Startup Successful!
echo  Logs saved to debug_log.txt
echo ==========================================
echo.
echo Closing this window in 1 second...
timeout /t 1 >nul
