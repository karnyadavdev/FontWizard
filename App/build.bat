@echo off
setlocal
pushd "%~dp0"

:: Detect Python executable
set "PYTHON_EXE=python"
where python >nul 2>&1
if %errorlevel% neq 0 (
    if exist "..\tools\python\python.exe" (
        set "PYTHON_EXE=..\tools\python\python.exe"
    ) else (
        where py >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=py"
        ) else (
            echo [!] Python was not found in PATH or ..\tools\python\
            popd
            exit /b 1
        )
    )
)

echo Using Python: %PYTHON_EXE%
echo Installing build dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    popd
    exit /b 1
)

echo Cleaning old build outputs...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "FontWizard.spec" del "FontWizard.spec"
if exist "Font Wizard.spec" del "Font Wizard.spec"

echo Building Font Wizard...
%PYTHON_EXE% -m PyInstaller --noconfirm --onefile --windowed --name "FontWizard" ^
    --add-data "src/assets;assets" ^
    --icon="src/assets/font-wizard.ico" ^
    --version-file="fontwizard_version_info.txt" ^
    "src/main.py"
if errorlevel 1 (
    popd
    exit /b 1
)

echo.
echo Building installer with Inno Setup...
set "ISCC_EXE="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
    where ISCC.exe > "%TEMP%\fontwizard_iscc.txt" 2>nul
)
if not defined ISCC_EXE if exist "%TEMP%\fontwizard_iscc.txt" set /p ISCC_EXE=<"%TEMP%\fontwizard_iscc.txt"
if exist "%TEMP%\fontwizard_iscc.txt" del "%TEMP%\fontwizard_iscc.txt"
if defined ISCC_EXE goto HaveIscc
echo [!] ISCC.exe from Inno Setup 6 was not found.
set /p "INSTALL_INNO=Install Inno Setup 6 now via winget? [Y/N] "
if /i not "%INSTALL_INNO%"=="Y" (
    echo Get it from https://jrsoftware.org/isinfo.php
    popd
    exit /b 1
)
where winget >nul 2>&1
if errorlevel 1 (
    echo [!] winget was not found. Get Inno Setup from https://jrsoftware.org/isinfo.php
    popd
    exit /b 1
)
echo Installing Inno Setup 6 via winget...
winget install -e --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo [!] winget install failed.
    popd
    exit /b 1
)
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
    echo [!] ISCC.exe still not found. Get it from https://jrsoftware.org/isinfo.php
    popd
    exit /b 1
)
:HaveIscc

echo Using Inno Setup: "%ISCC_EXE%"
for /f "tokens=2 delims=()" %%a in ('findstr /c:"filevers=" fontwizard_version_info.txt') do set "VER_RAW=%%a"
set "VER4=%VER_RAW:,=.%"
set "VER4=%VER4: =%"
for /f "tokens=1-4 delims=." %%a in ("%VER4%") do set "APP_VER=%%a.%%b.%%c"
for /f "tokens=4 delims=." %%d in ("%VER4%") do set "APP_VER_FULL=%APP_VER%.%%d"
if not defined APP_VER set "APP_VER=2.0.0"
if not defined APP_VER_FULL set "APP_VER_FULL=2.0.0.0"
echo App version: %APP_VER%
"%ISCC_EXE%" /DMyAppVersion=%APP_VER% /DMyAppVersionFull=%APP_VER_FULL% "installer.iss"
if errorlevel 1 (
    popd
    exit /b 1
)

echo.
echo Build complete! Run the installer from the 'dist\' folder.
popd
