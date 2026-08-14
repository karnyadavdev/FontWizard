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
echo Creating release ZIP...
if exist "dist\FontWizard.zip" del "dist\FontWizard.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1; Compress-Archive -LiteralPath 'dist\FontWizard.exe', '..\LICENSE', '..\third-party-notices.txt' -DestinationPath 'dist\FontWizard.zip' -Force"
if errorlevel 1 (

    popd
    exit /b 1
)

echo.
echo Build complete! Upload 'dist\FontWizard.zip' from the 'dist\' folder.
popd
