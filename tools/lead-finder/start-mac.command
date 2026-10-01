#!/bin/sh
cd "$(dirname "$0")"
# Claude-Paket für die KI-Bewertung (optional, Tool läuft auch ohne)
python3 -c "import anthropic" 2>/dev/null || python3 -m pip install --user --quiet anthropic
python3 leadfinder.py
