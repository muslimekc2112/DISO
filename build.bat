@echo off
cd /d "%~dp0"
echo === DISO.exe olusturuluyor / Building DISO.exe ===
python -m pip install -r requirements.txt pyinstaller
python tools\build_exe.py %*
echo.
echo Bitti! / Done!  dist\DISO.exe
echo (ffmpeg\ klasorune ffmpeg.exe koymadiysan program ilk MP3/birlestirme isleminde kendisi indirir.)
echo (Without ffmpeg.exe in ffmpeg\ the program downloads it the first time it needs it.)
echo (Daha kucuk EXE icin / for a smaller EXE:  build.bat --no-ffmpeg)
pause
