@echo off
cd /d "%~dp0"

echo ======================================
echo  Compilation et lancement ic705_qt
echo ======================================
echo.

echo [1/3] Configuration CMake...
cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DCMAKE_PREFIX_PATH="C:\Qt\6.11.0\msvc2022_64" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERREUR: Echec de la configuration
    pause
    exit /b 1
)

echo [2/3] Compilation Release...
cmake --build build --config Release >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERREUR: Echec de la compilation
    pause
    exit /b 1
)

echo [3/3] Deploiement des DLL Qt...
"C:\Qt\6.11.0\msvc2022_64\bin\windeployqt.exe" --qmldir qml --release "build\Release\ic705_qt.exe" >nul 2>&1

echo.
echo Lancement de l'application...
start "" "build\Release\ic705_qt.exe"
