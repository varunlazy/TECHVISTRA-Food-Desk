#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x app/.venv/bin/python ]; then
 echo 'Run Mac - Install and Setup.command first.'
else
 app/.venv/bin/python app/configure_secure_qr.py
fi
read -r -p 'Press Enter to close...'
