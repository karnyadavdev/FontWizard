@echo off
setlocal
pushd "%~dp0"

echo Installing build dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    popd
    exit /b 1
)

echo Cleaning old build outputs...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Font Wizard.spec" del "Font Wizard.spec"

echo Building Font Wizard...
python -m PyInstaller --noconfirm --onefile --windowed --name "Font Wizard" ^
    --add-data "src/assets;assets" ^
    --icon="src/assets/font-wizard.ico" ^
    "src/main.py"
if errorlevel 1 (
    popd
    exit /b 1
)

echo.
echo Creating release ZIP...
if exist "dist\Font Wizard App.zip" del "dist\Font Wizard App.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath 'dist\Font Wizard.exe', '..\LICENSE', '..\THIRD-PARTY-NOTICES.txt' -DestinationPath 'dist\Font Wizard App.zip' -Force"
if errorlevel 1 (
    popd
    exit /b 1
)

echo.
echo Build complete! Upload 'dist\Font Wizard App.zip' from the 'dist\' folder.
popd
