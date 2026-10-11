#!/usr/bin/env python3
"""Fetch Taif (TIF/OETF) departures from flightera.net for the next 48 hours
and write them to flights.json (used by T.html)."""
import json, re, sys, time
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

BASE = "https://www.flightera.net/en/airport/Taif/OETF/departure"
RIY = timezone(timedelta(hours=3))
OUT = "flights.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
DATE_RE = re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+(\d{4}))?")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
IATA_RE = re.compile(r"\(([A-Z]{3})\)")
FN_RE = re.compile(r"\b([A-Z]{2}|[A-Z]\d|\d[A-Z])\s?(\d{1,4}[A-Z]?)\b")


def status_of(text):
    t = text.lower()
    if "cancel" in t:
        return "bad"
    if "departed" in t or "landed" in t or "arrived" in t:
        return None  # skip
    if "delay" in t:
        return "late"
    if "live" in t or "boarding" in t or "departing" in t or "en route" in t:
        return "live"
    return "ok"


def parse_page(html, year_hint):
    soup = BeautifulSoup(html, "html.parser")
    flights = []
    for tr in soup.find_all("tr"):
        text = " ".join(tr.get_text(" ", strip=True).split())
        d = DATE_RE.search(text)
        if not d:
            continue
        times = TIME_RE.findall(text[d.start():])
        if not times:
            continue
        fn = None
        for a in tr.find_all("a", href=True):
            if "/flight/" in a["href"]:
                m = FN_RE.search(a.get_text(" ", strip=True)) or FN_RE.search(a["href"].upper())
                if m:
                    fn = m.group(1) + m.group(2)
                    break
        if not fn:
            m = FN_RE.search(text)
            if not m:
                continue
            fn = m.group(1) + m.group(2)
        codes = [c for c in IATA_RE.findall(text) if c != "TIF"]
        if not codes:
            continue
        st = status_of(text)
        if st is None:
            continue
        day, mon, yr = int(d.group(1)), MONTHS[d.group(2)[:3]], d.group(3)
        year = int(yr) if yr else year_hint
        hh, mm = int(times[0][0]), int(times[0][1])
        dt = datetime(year, mon, day, hh, mm, tzinfo=RIY)
        flights.append((dt, fn, codes[-1], st))
    nxt = None
    for a in soup.find_all("a", href=True):
        if "OffsetStart=" in a["href"] and "later" in a.get_text(" ", strip=True).lower():
            nxt = a["href"]
            if nxt.startswith("/"):
                nxt = "https://www.flightera.net" + nxt
    return flights, nxt


def main():
    now = datetime.now(RIY).replace(second=0, microsecond=0)
    end = now + timedelta(hours=48)
    url, seen_urls, found = BASE, set(), []
    for _ in range(12):
        if url in seen_urls:
            break
        seen_urls.add(url)
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        rows, nxt = parse_page(r.text, now.year)
        found += rows
        if not nxt or not rows or max(x[0] for x in rows) > end:
            break
        url = nxt
        time.sleep(2)
    uniq = {}
    for dt, fn, to, st in found:
        if now <= dt <= end:
            uniq[(dt, fn)] = (dt, fn, to, st)
    flights = sorted(uniq.values())
    if not flights:
        print("No flights parsed - keeping the old flights.json", file=sys.stderr)
        sys.exit(1)
    data = {
        "updated": now.isoformat(),
        "until": end.isoformat(),
        "flights": [[dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), fn, to, st]
                    for dt, fn, to, st in flights],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"Wrote {len(flights)} flights")


if __name__ == "__main__":
    main()
