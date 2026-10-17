@echo off
cd /d "%~dp0"
echo === Hizli Indirici ===
python -m pip install -r requirements.txt
python main.py
pause
