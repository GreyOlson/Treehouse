#!/bin/bash
# Double-click this file to start the Treehouse mailbox.
# It works no matter where the Treehouse folder lives: it cd's to its own
# folder first, so you never have to type a path.
cd "$(dirname "$0")" || exit 1
echo "Treehouse folder: $(pwd)"
echo "Starting the mailbox - leave this window open, then click a Generate"
echo "button in Roblox Studio. (Ctrl+C here to stop.)"
echo ""
python3 mailbox/server.py
echo ""
echo "Mailbox stopped. You can close this window."
