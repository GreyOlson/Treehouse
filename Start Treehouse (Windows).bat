@echo off
REM Double-click this file to start the Treehouse mailbox.
REM It works no matter where the Treehouse folder lives: it cd's to its own
REM folder first (%~dp0), so you never have to type a path.
cd /d "%~dp0"
echo Treehouse folder: %cd%
echo Starting the mailbox - leave this window open, then click a Generate
echo button in Roblox Studio. (Ctrl+C here to stop.)
echo.
python mailbox\server.py
echo.
echo Mailbox stopped. Press any key to close.
pause >nul
