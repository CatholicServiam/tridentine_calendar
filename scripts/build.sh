#!/usr/bin/env bash
set -euo pipefail

YEAR="$(date -u +%Y)"
NEXT="$((YEAR + 1))"

mkdir -p docs

# Generate base calendar (this year + next)
tridentine_calendar --output docs/base.ics "$YEAR" "$NEXT"

# Apply your symbol overlay to produce the published feed
python scripts/overlay_symbols.py docs/base.ics docs/tridentine_calendar.ics

# Optional: keep repo clean
rm -f docs/base.ics
