@echo off
rem Windows version of start.sh — double-click to launch the glorb LED server:
rem web UI + E1.31 output to the Angios.
rem Binds 0.0.0.0 so you can open the UI from a phone on the glorb network.
cd /d "%~dp0"
python -m glorbleds serve --host 0.0.0.0 %*
rem Keep the window open if the server exits/crashes so the error is readable.
echo.
echo glorbleds exited with code %errorlevel%
pause
