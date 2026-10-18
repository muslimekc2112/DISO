@echo off
cd /d "%~dp0"
echo === Hizli Indirici testleri ===
python -m pip install -q -r requirements-dev.txt
python -m pytest %*
pause
