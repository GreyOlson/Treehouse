@echo off
REM Double-click this file to start the Treehouse mailbox.
REM It cd's to its own folder first (%~dp0), so the folder can live anywhere.
REM It prefers uv (which can run the mailbox even without Python), else python.
cd /d "%~dp0"
echo Treehouse folder: %cd%
echo Starting the mailbox - leave this window open, then click a Generate
echo button in Roblox Studio. (Ctrl+C here to stop.)
echo.

where uv >nul 2>nul
if %errorlevel%==0 (
  uv run mailbox\server.py
  goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
  python mailbox\server.py
  goto done
)
echo Couldn't find "uv" or "python".
echo Easiest fix - install uv (runs Treehouse and fetches Python for you):
echo     https://astral.sh/uv
echo Or install Python 3 from https://python.org/downloads , then run this again.

:done
echo.
echo Mailbox stopped. Press any key to close.
pause >nul
