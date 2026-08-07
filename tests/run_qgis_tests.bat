@echo off
REM Run the QGIS-tier tests under the bundled QGIS Python (sets OSGeo4W env).
REM Auto-detects the QGIS install + launcher. Override with: set QGIS_ROOT=... before calling.
setlocal
set "QT_QPA_PLATFORM=offscreen"

REM Probe candidate roots (newest first) unless QGIS_ROOT already set.
if not defined QGIS_ROOT (
    for %%R in ("C:\QGIS 3.44.11" "C:\QGIS 4.0.3") do (
        if not defined QGIS_ROOT if exist "%%~R\bin\python-qgis-ltr.bat" set "QGIS_ROOT=%%~R"
        if not defined QGIS_ROOT if exist "%%~R\bin\python-qgis.bat" set "QGIS_ROOT=%%~R"
    )
)
if not defined QGIS_ROOT (
    echo ERROR: no QGIS install found. Set QGIS_ROOT to your QGIS folder.
    exit /b 1
)

REM The 3.x LTR ships python-qgis-ltr.bat; QGIS 4+ ships python-qgis.bat.
set "QGIS_PY=%QGIS_ROOT%\bin\python-qgis-ltr.bat"
if not exist "%QGIS_PY%" set "QGIS_PY=%QGIS_ROOT%\bin\python-qgis.bat"
if not exist "%QGIS_PY%" (
    echo ERROR: no python-qgis launcher under "%QGIS_ROOT%\bin".
    exit /b 1
)

cd /d "%~dp0.."
echo Using "%QGIS_PY%"
call "%QGIS_PY%" -m pytest -m "qgis or gui" %*
