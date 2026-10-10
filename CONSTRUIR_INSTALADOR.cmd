@echo off
setlocal
cd /d "%~dp0"
title Constructor Loreto One

echo ============================================================
echo  LORETO ONE - CONSTRUCTOR DE INSTALADOR WINDOWS
echo ============================================================
echo.

if not exist "manage.py" (
  echo ERROR: Este constructor debe estar en la raiz del proyecto LoretoOne,
  echo        junto a manage.py.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: No existe .venv\Scripts\python.exe en este proyecto.
  pause
  exit /b 1
)

if not exist "launcher.py" (
  echo ERROR: Falta launcher.py.
  pause
  exit /b 1
)

if not exist "assets\loretoone.ico" (
  echo ERROR: Faltan los recursos graficos del instalador.
  pause
  exit /b 1
)

echo [1/5] Instalando dependencias del proyecto y Desktop...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r desktop\requirements-desktop.txt
if errorlevel 1 goto :error

echo [2/5] Instalando/actualizando PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :error

echo [3/5] Verificando Django antes de empaquetar...
".venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto :error

echo [4/5] Generando LoretoOne.exe (el usuario final NO necesitara Python)...
if exist build rmdir /S /Q build
if exist dist\LoretoOne rmdir /S /Q dist\LoretoOne
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean LoretoOne.spec
if errorlevel 1 goto :error

echo [5/5] Buscando Inno Setup y generando el instalador final...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 no esta instalado. Intentando instalarlo con winget...
  where winget >nul 2>nul || goto :noinno
  winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
  set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" goto :noinno

"%ISCC%" LoretoOne.iss
if errorlevel 1 goto :error

echo.
echo ============================================================
echo LISTO.
echo Instalador creado en:
echo %CD%\Instalador_Final\LoretoOne_Setup_1.0.0_x64.exe
echo ============================================================
explorer "%CD%\Instalador_Final"
pause
exit /b 0

:noinno
echo.
echo LoretoOne.exe fue generado, pero falta Inno Setup 6 para crear Setup.exe.
echo Instala Inno Setup 6 y vuelve a ejecutar este archivo.
pause
exit /b 2

:error
echo.
echo ERROR: La construccion se detuvo. Copia el texto de esta ventana y envialo.
pause
exit /b 1
