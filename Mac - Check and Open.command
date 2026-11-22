#!/bin/bash
cd "$(dirname "$0")"
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
if [ ! -x app/.venv/bin/python ]; then
 echo 'Run Mac - Install and Setup.command first.'
else
 app/.venv/bin/python app/launcher.py --open
fi
read -r -p 'Press Enter to close...'
