@echo off
cd /d "%~dp0"
echo === Hizli Indirici EXE olusturuluyor ===
python -m pip install -r requirements.txt pyinstaller
python tools\build_exe.py %*
echo.
echo Bitti! EXE dosyan: dist\DISO.exe
echo (ffmpeg\ klasorune ffmpeg.exe koymadiysan program ilk MP3/birlestirme isleminde kendisi indirir.)
echo (Daha kucuk EXE icin:  build.bat --no-ffmpeg)
pause
