#!/bin/bash
# Launcher script for Auto-Update-Free

# Get the real directory of this script (resolve symlinks)
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Tạo môi trường ảo..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Set icon for taskbar (WM_CLASS)
export QT_QPA_PLATFORMTHEME=gtk3

# Run the application
python main.py
