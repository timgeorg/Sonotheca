"""Find alternative SoundCloud uploads/reposts of tracks, duration-matched.

For each track title given, search SoundCloud for other uploads of the same
track (label/premiere/repost variants). Only candidates whose duration matches
the ORIGINAL track within ±1 second are reported — anything else is likely a
snippet/preview/rip and is skipped.

Original durations are read from the playlist via the API (batch /tracks?ids=
endpoint). Usage:
    python find_alternatives.py "https://soundcloud.com/timggg/sets/tims-classic-techno" \
        "Step to the Rhythm" "Born Slippy" "Redox" ...
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv


def _sc_get(url, token) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"OAuth {token}")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def playlist_tracks(playlist_url, token):
    resolved = _sc_get(
        "https://api-v2.soundcloud.com/resolve?url=" + urllib.parse.quote(playlist_url), token
    )
    raw = resolved.get("tracks")
    if isinstance(raw, dict):
        raw = raw.get("collection") or []
    by_id = {}
    order = []
    for t in raw or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id"))
        if tid not in by_id:
            by_id[tid] = t
            order.append(tid)
    # Batch fetch full metadata incl. duration for all ids.
    rich = {}
    for start in range(0, len(order), 50):
        chunk = order[start : start + 50]
        url = "https://api-v2.soundcloud.com/tracks?ids=" + urllib.parse.quote(",".join(chunk))
        for t in _sc_get(url, token) or []:
            if isinstance(t, dict) and t.get("id") is not None:
                rich[str(t["id"])] = t
    out = []
    for tid in order:
        src = rich.get(tid) or by_id[tid]
        out.append(
            {
                "id": tid,
                "title": (src.get("title") or "").strip(),
                "artist": ((src.get("user") or {}).get("username") or "").strip(),
                "url": src.get("permalink_url") or f"https://api-v2.soundcloud.com/tracks/{tid}",
                "duration": src.get("duration"),
            }
        )
    return out


def search_tracks(query, token, limit=50):
    url = "https://api-v2.soundcloud.com/search/tracks?q=" + urllib.parse.quote(query) + f"&limit={limit}"
    try:
        data = _sc_get(url, token)
    except Exception as e:
        print(f"   search error for {query!r}: {e}")
        return []
    return [c for c in data.get("collection", []) if isinstance(c, dict)]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    playlist_url = sys.argv[1]
    wanted_titles = sys.argv[2:]

    load_dotenv()
    token = os.getenv("SC_TOKEN", "")
    if not token:
        print("ERROR: SC_TOKEN not set in .env")
        return 2

    print("Fetching playlist (for original durations)...")
    tracks = playlist_tracks(playlist_url, token)
    # Map wanted titles -> original track record (first matching, case-insensitive substring).
    originals = {}
    for wt in wanted_titles:
        wl = wt.casefold()
        for t in tracks:
            if wl in (t["title"] or "").casefold():
                originals[wt] = t
                break
        else:
            print(f"! no playlist track matched: {wt!r}")

    for wt in wanted_titles:
        orig = originals.get(wt)
        if orig is None:
            continue
        o_dur = orig.get("duration")
        o_sec = (o_dur / 1000) if o_dur else None
        print(f"\n=== {orig['title']!r} | {orig['artist']!r} | original ~{o_sec:.0f}s {orig['url']}")
        cands = search_tracks(orig["title"], token)
        matches = []
        for c in cands:
            c_dur = c.get("duration")
            c_sec = (c_dur / 1000) if c_dur else None
            if c_sec and o_sec and abs(c_sec - o_sec) <= 1.0:
                c_artist = (c.get("user") or {}).get("username") or ""
                # skip the exact same upload (same id).
                if str(c.get("id")) == orig["id"]:
                    continue
                matches.append((c_artist, c.get("title"), c_sec, c.get("permalink_url")))
        # Keep earliest-uploaded distinct permalinks that differ from the original.
        seen = set()
        unique = []
        for artist, title, sec, url in matches:
            if url in seen:
                continue
            seen.add(url)
            unique.append((artist, title, sec, url))
        print(f"  {len(unique)} duration-matched alternative(s) (±1s):")
        for artist, title, sec, url in unique[:8]:
            print(f"    [{sec:.0f}s] {artist} - {title}  {url}")
        if not unique:
            print("    (none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
