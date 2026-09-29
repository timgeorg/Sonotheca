"""Read-only SoundCloud playlist → local-file comparison. No downloads.

For each track in a playlist, report whether it exists in a local MP3 folder.

Playlist metadata is read in ONE SoundCloud API resolve call (reliable titles
and artists, and avoids the DRM crashes / per-track hammering that break
yt-dlp's non-flat extraction). Local matching reuses soundcloud_check.py's
token-intersection logic plus a filename fallback for downloads named
'Artist - Title.mp3'.

This script never writes to the music library — it only reads playlist
metadata and local MP3 ID3 tags.

Usage:
    python playlist_status.py \
        "https://soundcloud.com/timggg/sets/tims-classic-techno" \
        "/home/tim/Vault/downloads/playlist" \
        [--csv /tmp/status.csv]

Needs SC_TOKEN in .env (same as the other tools).
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from soundcloud_check import _normalize_url, _tokenize, iter_local_mp3_tracks


def _sc_get(url: str, token: str) -> dict:
    """GET a SoundCloud API endpoint with OAuth."""
    import json
    import urllib.request

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"OAuth {token}")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_playlist_entries(playlist_url: str, token: str) -> list[dict]:
    """Get the playlist's tracks using the resolve + tracks?ids= batch endpoints.

    Returns a list of {id, title, artist, url}. The resolve payload gives all
    track IDs but only full metadata for the first few; the rest arrive as
    partial objects. We fill those in with the /tracks?ids=... batch endpoint
    (one request per ~50 IDs), keeping API usage low (2–3 calls for a typical
    playlist) and avoiding per-track hammering.
    """
    import urllib.parse

    resolved = _sc_get(
        "https://api-v2.soundcloud.com/resolve?url="
        + urllib.parse.quote(playlist_url),
        token,
    )

    raw = resolved.get("tracks")
    if isinstance(raw, dict):  # paged collection object
        raw = raw.get("collection") or []

    # Consolidate by id, keeping order and the first-seen partial object.
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for t in raw or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id"))
        if tid in by_id:
            continue
        by_id[tid] = t
        order.append(tid)

    def summarize(t: dict) -> dict:
        return {
            "id": str(t.get("id")),
            "title": (t.get("title") or "").strip(),
            "artist": ((t.get("user") or {}).get("username") or "").strip(),
            "url": t.get("permalink_url")
            or f"https://api-v2.soundcloud.com/tracks/{t.get('id')}",
        }

    out: list[dict] = []
    # Track IDs whose resolve object is missing title/permalnk (needs enrichment).
    to_fetch: list[str] = []
    for tid in order:
        t = by_id[tid]
        if not t.get("title") or not t.get("permalink_url"):
            to_fetch.append(tid)
        else:
            out.append(summarize(t))

    # Batch-fetch the partial entries.
    batch_size = 50
    rich: dict[str, dict] = {}
    for start in range(0, len(to_fetch), batch_size):
        chunk = to_fetch[start : start + batch_size]
        url = "https://api-v2.soundcloud.com/tracks?ids=" + urllib.parse.quote(
            ",".join(chunk)
        )
        data = _sc_get(url, token)
        for t in data or []:
            if isinstance(t, dict) and t.get("id") is not None:
                rich[str(t["id"])] = t

    # Reassemble in original order.
    final: list[dict] = []
    for tid in order:
        src = rich.get(tid) or by_id[tid]
        final.append(summarize(src))
    return final


def build_local_index(local_folder: str | Path):
    """Index local MP3s by ID3 artist/title tokens, SoundCloud URL, and filename.

    Returns (local_tracks, artist_idx, title_idx, sc_url_idx, filename_idx).
    """
    local_tracks = list(iter_local_mp3_tracks(local_folder))
    artist_idx: dict[str, set[int]] = {}
    title_idx: dict[str, set[int]] = {}
    sc_url_idx: dict[str, set[int]] = {}
    filename_idx: dict[str, set[int]] = {}

    for idx, t in enumerate(local_tracks):
        for tok in _tokenize(t.artist):
            artist_idx.setdefault(tok, set()).add(idx)
        for tok in _tokenize(t.title):
            title_idx.setdefault(tok, set()).add(idx)

        u = _normalize_url(t.comment_url)
        if u:
            sc_url_idx.setdefault(u, set()).add(idx)

        stem = Path(t.url).stem if t.url else ""
        for tok in _tokenize(stem):
            filename_idx.setdefault(tok, set()).add(idx)

    return local_tracks, artist_idx, title_idx, sc_url_idx, filename_idx


def is_local_present(pl_url, pl_artist, pl_title, indexes) -> bool:
    """Is the playlist track matched by some local MP3?"""
    _, artist_idx, title_idx, sc_url_idx, filename_idx = indexes

    # 1) URL match via ID3 comment tag.
    pl_sc = _normalize_url(pl_url)
    if pl_sc and pl_sc in sc_url_idx:
        return True

    artist_tokens = _tokenize(pl_artist)
    title_tokens = _tokenize(pl_title)

    # 2) Token intersection on artist AND title.
    if artist_tokens and title_tokens:
        ar: set[int] = set()
        for tok in artist_tokens:
            ar |= artist_idx.get(tok, set())
        tt: set[int] = set()
        for tok in title_tokens:
            tt |= title_idx.get(tok, set())
        if ar & tt:
            return True

    # 3) Filename fallback: every title token appears in one file's name.
    if title_tokens:
        candidates: set[int] | None = None
        for tok in title_tokens:
            cand = filename_idx.get(tok, set())
            if not cand:
                candidates = set()
                break
            candidates = cand if candidates is None else (candidates & cand)
        if candidates:
            return True

    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playlist_url", help="SoundCloud playlist URL")
    parser.add_argument("local_folder", help="Folder of MP3s to compare against")
    parser.add_argument("--csv", help="Optional path to write results CSV")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("SC_TOKEN", "")
    if not token:
        print("ERROR: SC_TOKEN not set in .env")
        return 2

    print("Fetching playlist entries (one API call)...")
    entries = fetch_playlist_entries(args.playlist_url, token)
    print(f"Playlist has {len(entries)} track(s).\n")

    print("Indexing local MP3s...")
    indexes = build_local_index(args.local_folder)

    print(f"{'#':>3}  {'Status':<10} Title")
    print("-" * 70)
    rows = []
    for i, e in enumerate(entries, start=1):
        title = e["title"] or e["url"] or "<untitled>"
        present = is_local_present(e["url"], e["artist"], e["title"], indexes)
        status = "downloaded" if present else "missing"
        rows.append(
            {
                "index": i,
                "title": title,
                "artist": e["artist"],
                "status": status,
                "url": e["url"],
            }
        )
        print(f"{i:>3}  {status:<10} {title}")

    missing = [r for r in rows if r["status"] == "missing"]
    print("\n" + "=" * 70)
    print(f"Downloaded: {len(rows) - len(missing)} / {len(rows)}")
    print(f"MISSING:    {len(missing)} / {len(rows)}")

    if missing:
        print("\nTo download:")
        for r in missing:
            label = (r["artist"] + " - " if r["artist"] else "") + r["title"]
            print(f"- {label}  {r['url']}")

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["index", "title", "artist", "status", "url"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV written to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
