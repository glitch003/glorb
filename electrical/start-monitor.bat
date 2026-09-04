@echo off
rem Double-click to launch the glorb power monitor: one web dashboard for the
rem 12 V, 24 V and 72 V battery systems.
rem
rem Binds 0.0.0.0 so you can open it from a phone on the glorb network.
rem IMPORTANT: close BMS_TOOLS, the Orion BMS utility and the Arduino serial
rem monitor first -- Windows gives one program at a time exclusive use of a
rem COM port, and whichever got there first wins.
cd /d "%~dp0"
python -m glorbmon serve --host 0.0.0.0 %*
rem Keep the window open if the server exits/crashes so the error is readable.
echo.
echo glorbmon exited with code %errorlevel%
pause
