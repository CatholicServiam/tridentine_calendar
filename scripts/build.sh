#!/usr/bin/env bash
set -euo pipefail

YEAR="$(date -u +%Y)"
NEXT="$((YEAR + 1))"

mkdir -p public

# Generate base calendar (this year + next)
tridentine_calendar --output public/base.ics "$YEAR" "$NEXT"

# Apply your symbol overlay to produce the published feed
python scripts/overlay_symbols.py public/base.ics public/tridentine_calendar.ics

# Optional: keep repo clean
rm -f public/base.ics
