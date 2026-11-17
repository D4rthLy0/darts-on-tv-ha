#!/usr/bin/env python3
"""Darts on UK TV for the next ~31 days, printed as JSON for sensor.darts_on_tv.

Sources (free, no account):
  * wheresthematch.com/live-darts-on-tv/  -> sessions: date, start time, tournament,
    round, venue, TV channels. Times on the page are UK time.
  * dartsnews.com tournament hub page ("<tournament>-...results-schedule...")
    -> who's playing in each session, once the draw / order of play is out.
    Best effort: if it can't be found or parsed, matches are just left empty.

Run by the command_line sensor every 3 hours. Uses only the standard library.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser

try:
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover
    UK = None

UA = {"User-Agent": "Mozilla/5.0 (HomeAssistant darts_tv)"}
WTM = "https://www.wheresthematch.com/live-darts-on-tv/"
DN_INDEX = "https://dartsnews.com/pdc"
MAX_SESSIONS = 25
MATCH_DAYS = 3  # only attach line-ups to sessions in the next few days (keeps attributes small)

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
DAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def text(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def now_uk():
    return datetime.now(UK) if UK else datetime.now()


# ---------------------------------------------------------------- TV listings
def parse_listings(page):
    sessions = []
    for row in re.findall(r"<tr>(.*?)</tr>", page, flags=re.S):
        if "start-details" not in row or "fixture-details" not in row:
            continue
        fx = re.search(r'class="fixture-details">(.*?)</td>', row, flags=re.S)
        fx_html = fx.group(1) if fx else ""
        event = text((re.search(r"<strong[^>]*>(.*?)</strong>", fx_html, flags=re.S) or [None, ""])[1])
        # Text after the tournament name is "<round> - <venue>"
        rest = text(re.sub(r'<span class="fixture">.*?</span>', "", fx_html, count=1, flags=re.S))
        rnd, venue = rest, ""
        if " - " in rest:
            rnd, venue = rest.rsplit(" - ", 1)
        sd = re.search(r'class="start-details">(.*?)</td>', row, flags=re.S)
        sd_txt = text(sd.group(1)) if sd else ""
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th) (\w+) (\d{4}).*?(\d{1,2}):(\d{2})", sd_txt)
        if not m:
            continue
        day, mon, year, hh, mm = m.groups()
        mon_n = MONTHS.get(mon.lower())
        if not mon_n:
            continue
        start = datetime(int(year), mon_n, int(day), int(hh), int(mm), tzinfo=UK)
        ch = re.search(r'class="channel-details">(.*?)</td>', row, flags=re.S)
        channels = []
        if ch:
            for c in re.findall(r'<span class="sr-only">(.*?)</span>', ch.group(1), flags=re.S):
                c = text(c)
                if c and c not in channels:
                    channels.append(c)
        sessions.append({
            "start": start.isoformat(),
            "event": event or "Darts",
            "round": rnd.strip(),
            "venue": venue.strip(),
            "channels": channels,
            "matches": [],
        })
    return sessions


# ------------------------------------------------------------- who's playing
class Lines(HTMLParser):
    """Flattens a page into text lines; table rows become lists of cells."""
    BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "tr", "br"}

    def __init__(self):
        super().__init__()
        self.out, self.buf, self.row, self.cell, self.in_cell = [], [], None, [], False
        self.skip = 0

    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if t:
            self.out.append(t)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "tr":
            self.flush()
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell = True, []
        elif tag in self.BLOCK and not self.in_cell:
            self.flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.in_cell = False
        elif tag == "tr" and self.row is not None:
            self.out.append(self.row)
            self.row = None
        elif tag in self.BLOCK and not self.in_cell:
            self.flush()

    def handle_data(self, data):
        if self.skip:
            return
        (self.cell if self.in_cell else self.buf).append(data)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def find_hub(index_html, event):
    """Link to dartsnews' '<tournament> <year>: results, schedule ...' page."""
    want = slug(re.sub(r"^(pdc|bdo|wdf)\s+", "", event, flags=re.I))
    for href in re.findall(r'href="(https://dartsnews\.com/pdc/[^"#]+)"', index_html):
        tail = href.rsplit("/", 1)[-1]
        if want and want in tail and "schedule" in tail:
            return href
    return None


def parse_lineups(hub_html, year):
    """{(date, 'afternoon'|'evening'): [ 'A v B', ...]} from a hub page."""
    p = Lines()
    p.feed(hub_html)
    found, date, sess = {}, None, None
    for item in p.out:
        if isinstance(item, str):
            dm = re.match(rf"^(?:{DAYS}),? (\d{{1,2}})(?:st|nd|rd|th)? (\w+)(?: (\d{{4}}))?$", item, re.I)
            if dm and dm.group(2).lower() in MONTHS:
                date = datetime(int(dm.group(3) or year), MONTHS[dm.group(2).lower()], int(dm.group(1))).date()
                sess = None
                continue
            sm = re.match(r"^(afternoon|evening|night|morning) session", item, re.I)
            if sm:
                sess = "afternoon" if sm.group(1).lower() in ("afternoon", "morning") else "evening"
            continue
        cells = [c for c in item if c]
        if date and sess and len(cells) >= 3 and cells[1].lower() in ("v", "vs", "vs."):
            a, b = cells[0], cells[2]
            if a.lower().startswith("player") or re.match(r"(winner|loser)", a, re.I):
                continue
            b = re.sub(r"\s*\([A-Z]\)$", "", b)  # drop "(J)" group letter
            found.setdefault((date, sess), []).append(f"{a} v {b}")
    return found


def add_lineups(sessions):
    soon = now_uk().date() + timedelta(days=MATCH_DAYS)
    wanted = {s["event"] for s in sessions if datetime.fromisoformat(s["start"]).date() <= soon}
    if not wanted:
        return
    try:
        index = fetch(DN_INDEX)
    except Exception:
        return
    for event in wanted:
        url = find_hub(index, event)
        if not url:
            continue
        try:
            lineups = parse_lineups(fetch(url), now_uk().year)
        except Exception:
            continue
        for s in sessions:
            st = datetime.fromisoformat(s["start"])
            if s["event"] != event or st.date() > soon:
                continue
            key = (st.date(), "afternoon" if st.hour < 17 else "evening")
            if key in lineups:
                s["matches"] = lineups[key]
                s["source"] = url


def main():
    try:
        sessions = parse_listings(fetch(WTM))
    except Exception as e:
        print(json.dumps({"next": None, "error": str(e)[:200], "sessions": []}))
        return 0
    cutoff = now_uk() - timedelta(hours=4)  # keep tonight's session while it's on
    sessions = [s for s in sessions if datetime.fromisoformat(s["start"]) >= cutoff]
    sessions.sort(key=lambda s: s["start"])
    sessions = sessions[:MAX_SESSIONS]
    try:
        add_lineups(sessions)
    except Exception:
        pass
    upcoming = [s for s in sessions if datetime.fromisoformat(s["start"]) >= now_uk() - timedelta(hours=1)]
    print(json.dumps({
        "next": upcoming[0]["start"] if upcoming else None,
        "updated": now_uk().isoformat(timespec="seconds"),
        "sessions": sessions,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
