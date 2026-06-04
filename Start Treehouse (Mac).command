#!/bin/bash
# Double-click this file to start the Treehouse mailbox.
# It works no matter where the Treehouse folder lives: it cd's to its own
# folder first, so you never have to type a path. It prefers uv (which can run
# the mailbox even if you don't have Python), and falls back to python3.
cd "$(dirname "$0")" || exit 1
echo "Treehouse folder: $(pwd)"
echo "Starting the mailbox - leave this window open, then click a Generate"
echo "button in Roblox Studio. (Ctrl+C here to stop.)"
echo ""
if command -v uv >/dev/null 2>&1; then
  uv run mailbox/server.py
elif command -v python3 >/dev/null 2>&1; then
  python3 mailbox/server.py
else
  echo "Couldn't find 'uv' or 'python3'."
  echo "Easiest fix - install uv (it runs Treehouse and fetches Python for you):"
  echo "    https://astral.sh/uv   (or: curl -LsSf https://astral.sh/uv/install.sh | sh)"
  echo "Or install Python 3 from https://python.org/downloads , then run this again."
fi
echo ""
echo "Mailbox stopped. You can close this window."
