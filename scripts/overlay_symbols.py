#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from icalendar import Calendar


# ----------------------------
# CONFIG (easy to tweak)
# ----------------------------

# Prefix symbols (front-of-title, as you want)
SYM_HOLYDAY = "✝️"
SYM_FAST = "⛔"
SYM_ABST = "🐟"

# Traditional (classical) holy days list (1962-style baseline).
# Matching is done on normalized SUMMARY text (stripped of arrows/punctuation).
HOLY_DAYS_1962_TITLES = {
    # Jan 1
    "circumcision of our lord",

    # Jan 6
    "epiphany of our lord",
    "the epiphany of our lord",

    # Mar 19
    "st joseph spouse of the blessed virgin mary",
    "st joseph",
    "st. joseph",

    # Ascension / Corpus Christi
    "ascension of our lord",
    "the ascension of our lord",
    "corpus christi",

    # Jun 29
    "ss peter and paul apostles",
    "ss. peter and paul",
    "saints peter and paul",
    "st. peter and st. paul",
    "st peter and st paul",

    # Aug 15
    "assumption of the blessed virgin mary",
    "the assumption of the blessed virgin mary",
    "assumption",

    # Nov 1
    "all saints",
    "all saints day",

    # Dec 8
    "immaculate conception of the blessed virgin mary",
    "the immaculate conception",
    "immaculate conception",

    # Dec 25
    "nativity of our lord",
    "christmas",
}

# Optional: treat every Sunday as "holy" (I recommend False—too noisy)
MARK_SUNDAYS_AS_HOLY = False


# ----------------------------
# DATE MATH (fast/abstinence)
# ----------------------------

def easter_gregorian(y: int) -> date:
    """Anonymous Gregorian computus (Meeus/Jones/Butcher)."""
    a = y % 19
    b = y // 100
    c = y % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(y, month, day)

def is_sunday(d: date) -> bool:
    return d.weekday() == 6  # Monday=0 ... Sunday=6

def is_friday(d: date) -> bool:
    return d.weekday() == 4  # Friday

def ash_wednesday(y: int) -> date:
    return easter_gregorian(y) - timedelta(days=46)

def pentecost_sunday(y: int) -> date:
    return easter_gregorian(y) + timedelta(days=49)

def ember_days(y: int) -> set[date]:
    """
    Traditional ember day approximation (1962-era pattern):
    - Advent: Wed/Fri/Sat after Dec 13 (St. Lucy)
    - Lent: Wed/Fri/Sat after 1st Sunday of Lent
    - Pentecost: Wed/Fri/Sat in Pentecost week
    - September: Wed/Fri/Sat after 3rd Sunday of September
    """
    out: set[date] = set()

    # Advent ember days: first Wed on/after Dec 13, then Fri/Sat
    dec13 = date(y, 12, 13)
    # find next Wednesday on/after Dec 13
    wd = dec13 + timedelta(days=(2 - dec13.weekday()) % 7)  # Wednesday=2
    out.update({wd, wd + timedelta(days=2), wd + timedelta(days=3)})

    # Lent ember days: Wed/Fri/Sat after 1st Sunday of Lent
    aw = ash_wednesday(y)
    # 1st Sunday of Lent is the Sunday after Ash Wednesday
    first_lent_sun = aw + timedelta(days=(6 - aw.weekday()) % 7)
    wed_after = first_lent_sun + timedelta(days=3)
    out.update({wed_after, wed_after + timedelta(days=2), wed_after + timedelta(days=3)})

    # Pentecost ember days: Wed/Fri/Sat in Pentecost week
    p = pentecost_sunday(y)
    wed = p + timedelta(days=3)
    out.update({wed, wed + timedelta(days=2), wed + timedelta(days=3)})

    # September ember days: after 3rd Sunday of September
    sept1 = date(y, 9, 1)
    first_sun = sept1 + timedelta(days=(6 - sept1.weekday()) % 7)
    third_sun = first_sun + timedelta(days=14)
    wed = third_sun + timedelta(days=3)
    out.update({wed, wed + timedelta(days=2), wed + timedelta(days=3)})

    return out

def vigil_days(y: int) -> set[date]:
    """
    Traditional vigils commonly observed as fast+abstinence days.
    (You can add/remove later.)
    """
    e = easter_gregorian(y)
    p = pentecost_sunday(y)
    return {
        date(y, 12, 24),            # Christmas Vigil
        date(y, 8, 14),             # Assumption Vigil
        date(y, 10, 31),            # All Saints Vigil
        p - timedelta(days=1),      # Vigil of Pentecost (Saturday)
        date(y, 6, 28),             # Vigil of Ss Peter & Paul (often kept)
    }

def penitential_marks(d: date) -> tuple[bool, bool]:
    """
    Returns (fast, abstinence) for the date using a traditional-ish rule set:
    - Abstinence: all Fridays
    - Fast+Abstinence: Ash Wednesday; weekdays of Lent (Mon–Sat); Ember Days; listed Vigils
    - Holy Saturday: included by Lent rule
    - Sundays are never fast days
    """
    y = d.year
    e = easter_gregorian(y)
    aw = ash_wednesday(y)

    # Lent window: Ash Wednesday through Holy Saturday
    holy_saturday = e - timedelta(days=1)
    in_lent_window = aw <= d <= holy_saturday

    embers = ember_days(y)
    vigils = vigil_days(y)

    abst = False
    fast = False

    # Fridays: abstinence
    if is_friday(d):
        abst = True

    # Lent (excluding Sundays): fast+abstinence
    if in_lent_window and not is_sunday(d):
        fast = True
        abst = True

    # Ember days: fast+abstinence (even outside Lent)
    if d in embers and not is_sunday(d):
        fast = True
        abst = True

    # Vigils: fast+abstinence (unless it lands on Sunday)
    if d in vigils and not is_sunday(d):
        fast = True
        abst = True

    return fast, abst


# ----------------------------
# SUMMARY NORMALIZATION
# ----------------------------

SYM_STRIP_RE = re.compile(r"^\s*(✝️|⛔|🐟|\s)+\s*")

def normalize_title(summary: str) -> str:
    s = summary.strip()
    # remove existing symbols if already present
    s = SYM_STRIP_RE.sub("", s).strip()

    # keep Joe's outranked marker "›" but don't let it affect matching
    s_for_match = s.lstrip("›»").strip()

    # lowercase + collapse spaces
    s_for_match = re.sub(r"\s+", " ", s_for_match).lower()
    return s_for_match

def strip_existing_symbols(summary: str) -> str:
    s = summary.strip()
    s = SYM_STRIP_RE.sub("", s).strip()
    return s


def build_prefix(is_holy: bool, is_fast: bool, is_abst: bool) -> str:
    # Order: holy day, fast, abstinence (consistent)
    p = ""
    if is_holy:
        p += SYM_HOLYDAY
    if is_fast:
        p += SYM_FAST
    if is_abst:
        p += SYM_ABST
    return p


def main(in_path: str, out_path: str) -> None:
    raw = Path(in_path).read_bytes()
    cal = Calendar.from_ical(raw)

    for component in cal.walk("VEVENT"):
        dtstart = component.get("DTSTART")
        if not dtstart:
            continue
        dt = dtstart.dt
        if hasattr(dt, "date"):   # datetime -> date
            d = dt.date()
        else:
            d = dt  # VALUE=DATE -> datetime.date

        summary = str(component.get("SUMMARY", "")).strip()
        base = strip_existing_symbols(summary)

        match_key = normalize_title(summary)

        is_holy = match_key in HOLY_DAYS_1962_TITLES
        if MARK_SUNDAYS_AS_HOLY and is_sunday(d):
            is_holy = True

        fast, abst = penitential_marks(d)
        # Traditional dispensation: Holy Days override penance markings
        if is_holy:
            fast = False
            abst = False

        prefix = build_prefix(is_holy, fast, abst)
        if prefix:
            component["SUMMARY"] = f"{prefix} {base}"
        else:
            component["SUMMARY"] = base

    Path(out_path).write_bytes(cal.to_ical())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/overlay_symbols.py INPUT.ics OUTPUT.ics", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
