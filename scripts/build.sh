#!/usr/bin/env bash
# Render build command: install dependencies.
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt

mkdir -p logs
