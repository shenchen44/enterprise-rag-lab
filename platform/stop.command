#!/bin/zsh
set -eu
cd "$(dirname "$0")"
python3 scripts/platform.py stop
