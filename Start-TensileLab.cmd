@echo off
setlocal
cd /d "%~dp0"
>startup.log echo Tensile Lab startup diagnostics
for %%F in (app.py domain.py models.py simulation.py data_io.py visualization.py requirements.txt data\materials.csv data\curve_points.csv data\provenance.csv) do (
    if not exist "%%F" (
        >>startup.log echo Missing required file: %%F
        goto failed
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo Creating a local Python environment...
    py -m venv .venv >>startup.log 2>&1
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'" >>startup.log 2>&1
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import streamlit, numpy, scipy, plotly" >nul 2>&1
if errorlevel 1 (
    echo Installing application dependencies into the local environment...
    ".venv\Scripts\python.exe" -m ensurepip --upgrade >>startup.log 2>&1
    if errorlevel 1 goto failed
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt >>startup.log 2>&1
    if errorlevel 1 goto failed
)
echo Opening Tensile Lab. Keep this window open while using the app.
echo To stop the server, press Ctrl+C in this window.
echo Startup errors are saved in startup.log in this folder.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false --server.address 127.0.0.1 2>>startup.log
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Tensile Lab could not start. Details:
type startup.log
echo.
echo Extract the entire ZIP, not just the launcher and data folder.
echo Keep all program files together. See README.md for setup instructions.
pause
exit /b 1
