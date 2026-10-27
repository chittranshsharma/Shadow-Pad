#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3.14 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-mac.txt
.venv/bin/python download_model.py --variant full
.venv/bin/python download_model.py --variant hands
echo 'Ready. Run .venv/bin/python webcam_tracker.py --practice'
