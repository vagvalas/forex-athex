@echo off
REM Builds dist\ATHEX\ATHEX.exe on Windows. Needs Python 3.12+ from python.org (the "py" launcher).
cd /d "%~dp0"
if not exist .venv-win py -3 -m venv .venv-win || goto :error
call .venv-win\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt -r requirements-build.txt || goto :error
python -m pytest -q || goto :error
pyinstaller --noconfirm --clean --windowed --onedir --name ATHEX --collect-data ttkbootstrap --copy-metadata ttkbootstrap athex_to_metastock.py || goto :error
echo.
echo OK: dist\ATHEX\ATHEX.exe  (copy the whole dist\ATHEX folder)
goto :eof
:error
echo BUILD FAILED
exit /b 1
