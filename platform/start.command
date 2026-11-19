#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ "${1:-}" == "--build" ]]; then python3 scripts/platform.py build; fi
python3 scripts/platform.py start
open http://127.0.0.1:9080
