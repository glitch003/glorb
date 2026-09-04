@echo off
rem Double-click to launch the whole glorb dashboard: LED control and live
rem battery monitoring for the 12 V, 24 V and 72 V systems, on one page.
rem
rem Opens on http://localhost:8080/ and binds 0.0.0.0, so you can also reach
rem it from a phone on the glorb network at http://<car ip>:8080/.
rem
rem IMPORTANT: close BMS_TOOLS, the Orion BMS utility and the Arduino serial
rem monitor first. Windows gives one program at a time exclusive use of a COM
rem port, and whichever got there first wins.
cd /d "%~dp0"
python -m glorbdash serve --host 0.0.0.0 %*
rem Keep the window open if it exits/crashes so the error is readable.
echo.
echo glorbdash exited with code %errorlevel%
pause
