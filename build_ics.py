#!/usr/bin/env python3
"""
Chicago City Council & committee meetings -> iCalendar (.ics) feed.

Pulls meetings from the City Clerk eLMS public API
(https://api.chicityclerkelms.chicago.gov/meeting) and writes a calendar
file that Outlook/Exchange, Apple Calendar or Google Calendar can subscribe to.

- Each meeting keeps a stable UID (the Clerk's meetingId), so time/date/location
  edits update the existing event instead of creating duplicates.
- SEQUENCE is derived from the Clerk's lastPublicationDate, so calendar clients
  treat every Clerk re-publication as a newer revision.
- Cancelled meetings stay on the calendar, marked STATUS:CANCELLED and prefixed
  "CANCELLED:" so a cancellation is visible rather than silently vanishing.

No third-party dependencies (standard library only).

Usage:
  python3 build_ics.py                      # all bodies -> chicago-council.ics
  python3 build_ics.py --bodies "City Council" "Committee on Transportation and Public Way"
  python3 build_ics.py --out docs/council.ics --past-days 14 --future-days 120
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.chicityclerkelms.chicago.gov/meeting"
MEETING_PAGE = "https://chicityclerkelms.chicago.gov/Meeting/?meetingId={}"
# The Clerk publishes a start time only; these are placeholder lengths.
DEFAULT_MINUTES = {"City Council": 240}
FALLBACK_MINUTES = 120


def fetch_meetings(start_utc: datetime) -> list[dict]:
    """Page through /meeting for everything on or after start_utc."""
    out, skip, top = [], 0, 200
    # The API accepts an unquoted ISO timestamp with a trailing Z; quoted
    # strings or bare dates return "Invalid use of search and filter parameters".
    flt = f"date ge {start_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    while True:
        qs = urllib.parse.urlencode(
            {"filter": flt, "sort": "date asc", "top": top, "skip": skip}
        )
        req = urllib.request.Request(
            f"{API}?{qs}", headers={"User-Agent": "chicago-council-ics/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
        data = payload.get("data", [])
        out.extend(data)
        pages = payload.get("meta", {}).get("pages", 1)
        skip += top
        if not data or skip >= pages * top:
            break
    return out


def esc(text: str) -> str:
    """Escape text per RFC 5545 section 3.3.11."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Fold content lines at 75 octets (RFC 5545 section 3.1)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not parts else 74
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += b
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def utc_stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def to_vevent(m: dict) -> list[str]:
    start = datetime.fromisoformat(m["date"])
    minutes = DEFAULT_MINUTES.get(m["body"], FALLBACK_MINUTES)
    end = start + timedelta(minutes=minutes)
    pub = datetime.fromisoformat(m["lastPublicationDate"])
    status = (m.get("status") or "").strip()
    cancelled = status.lower().startswith("cancel")

    title = m["body"]
    if cancelled:
        title = f"CANCELLED: {title}"
    elif status.lower() in ("recessed", "reconvened"):
        title = f"{title} ({status})"

    page = MEETING_PAGE.format(m["meetingId"])
    desc = [f"Status: {status}"]
    if m.get("comment"):
        desc.append(m["comment"].strip())
    for f in m.get("files") or []:
        desc.append(f"{f.get('attachmentType', 'File')}: {f.get('path')}")
    if m.get("videoLink"):
        desc.append(f"Video: {m['videoLink']}")
    desc.append(f"Clerk page: {page}")
    desc.append(f"Last published by Clerk: {pub.strftime('%Y-%m-%d %H:%M UTC')}")

    return [
        "BEGIN:VEVENT",
        f"UID:{m['meetingId'].lower()}@chicityclerkelms.chicago.gov",
        f"DTSTAMP:{utc_stamp(pub)}",
        f"LAST-MODIFIED:{utc_stamp(pub)}",
        # Monotonic revision counter; minutes since 2020 fits comfortably in an int.
        f"SEQUENCE:{int((pub - datetime(2020, 1, 1, tzinfo=timezone.utc)).total_seconds() // 60)}",
        f"DTSTART:{utc_stamp(start)}",
        f"DTEND:{utc_stamp(end)}",
        f"SUMMARY:{esc(title)}",
        f"LOCATION:{esc(m.get('location') or '')}",
        f"DESCRIPTION:{esc(chr(10).join(desc))}",
        f"URL:{page}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
        "TRANSP:TRANSPARENT",  # show as free; these are tracking events
        "END:VEVENT",
    ]


def build(meetings: list[dict], cal_name: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//chicago-council-ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(cal_name)}",
        "X-WR-TIMEZONE:America/Chicago",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for m in meetings:
        lines.extend(to_vevent(m))
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="chicago-council.ics")
    ap.add_argument("--bodies", nargs="*", help="Only include these bodies (exact names)")
    ap.add_argument("--past-days", type=int, default=14)
    ap.add_argument("--future-days", type=int, default=180)
    ap.add_argument("--name", default="Chicago City Council & Committees")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    meetings = fetch_meetings(now - timedelta(days=a.past_days))
    horizon = now + timedelta(days=a.future_days)
    meetings = [m for m in meetings if datetime.fromisoformat(m["date"]) <= horizon]
    if a.bodies:
        wanted = set(a.bodies)
        # Joint committees list several bodies in one name; match on substring.
        meetings = [
            m for m in meetings
            if m["body"] in wanted
            or any(w.replace("Committee on ", "") in m["body"] for w in wanted)
        ]

    ics = build(meetings, a.name)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(ics)
    print(f"Wrote {len(meetings)} meetings to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
