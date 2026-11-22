#!/bin/bash
set -e
cd "$(dirname "$0")"
trap 'echo "Setup stopped. Review the message above."; read -r -p "Press Enter to close..."' ERR
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  echo 'Installing Python 3.12 from python.org. macOS will request your administrator password.'
  setup_dir="$(mktemp -d)"
  pkg="$setup_dir/python.pkg"
  curl --fail --location --proto '=https' --tlsv1.2 https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg -o "$pkg"
  pkgutil --check-signature "$pkg" | tee "$setup_dir/signature.txt"
  grep -q 'Python Software Foundation' "$setup_dir/signature.txt"
  sudo installer -pkg "$pkg" -target /
  rm -f "$pkg"
fi
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
python3 app/launcher.py --setup
