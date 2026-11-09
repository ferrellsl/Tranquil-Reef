@echo off
rem Builds "Tranquil Reef Installer.exe" with the channel inside.
rem Run build.py first so out\TranquilReef.zip exists.
cd /d "%~dp0"
python make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name "Tranquil Reef Installer" ^
  --icon tranquil_reef.ico --add-data "..\out\TranquilReef.zip;." --add-data "tranquil_reef.ico;." ^
  --distpath ..\dist --workpath ..\build tranquil_reef_installer.py
