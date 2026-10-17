@echo off
cd /d "%~dp0"
echo === Hizli Indirici EXE olusturuluyor ===
python -m pip install -r requirements.txt pyinstaller

set EXTRA=
python -c "import yt_dlp_ejs" 2>nul && set EXTRA=--collect-all yt_dlp_ejs
if exist "ffmpeg\ffmpeg.exe" (set EXTRA=%EXTRA% --add-data "ffmpeg;ffmpeg")

python -m PyInstaller --noconsole --onefile --clean ^
  --name HizliIndirici ^
  --collect-all customtkinter ^
  --collect-all yt_dlp ^
  --collect-all certifi ^
  --collect-all tkinterdnd2 ^
  %EXTRA% ^
  main.py
echo.
echo Bitti! EXE dosyan: dist\HizliIndirici.exe
echo (ffmpeg\ klasorune ffmpeg.exe koymadiysan program ilk MP3/birlestirme isleminde kendisi indirir.)
pause
