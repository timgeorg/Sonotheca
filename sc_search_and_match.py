#!/usr/bin/env python3
"""Search SoundCloud for each track in the Spotify playlist export.
Uses the SoundCloud v2 API with an OAuth token.
Outputs a JSON file with matched track IDs."""

import json
import os
import re
import time
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SC_TOKEN")
if not TOKEN:
    print("ERROR: SC_TOKEN not found in .env")
    sys.exit(1)

INPUT_FILE = Path(__file__).parent / "spotify_dnb_archiv.txt"
OUTPUT_FILE = Path(__file__).parent / "sc_search_results_dnb.json"

SC_SEARCH_URL = "https://api-v2.soundcloud.com/search/tracks"
HEADERS = {
    "Authorization": f"OAuth {TOKEN}",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def parse_tracks(filepath: Path) -> list[dict]:
    """Parse the track list file into a list of {title, artist, spotify_id}."""
    tracks = []
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: title --- artist(s) --- spotify_id
        parts = [p.strip() for p in line.split("---")]
        if len(parts) >= 2:
            tracks.append({
                "title": parts[0],
                "artist": parts[1],
                "spotify_id": parts[2] if len(parts) > 2 else None,
            })
    return tracks


def search_track(query: str, limit: int = 5, retries: int = 3) -> list[dict]:
    """Search SoundCloud for tracks matching the query."""
    params = {"q": query, "limit": limit}
    for attempt in range(retries):
        try:
            resp = requests.get(SC_SEARCH_URL, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 403:
                if attempt < retries - 1:
                    wait = 5 * (attempt + 1)
                    print(f"  403, retrying in {wait}s... (attempt {attempt+1}/{retries})")
                    time.sleep(wait)
                    continue
                return []
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "id": t["id"],
                    "title": t["title"],
                    "permalink_url": t.get("permalink_url"),
                    "duration": t.get("duration"),
                    "user": t.get("user", {}).get("username", ""),
                    "playback_count": t.get("playback_count") or 0,
                }
                for t in data.get("collection", [])
            ]
        except Exception as e:
            if attempt < retries - 1:
                print(f"  Search error (attempt {attempt+1}): {e}, retrying...")
                time.sleep(3 * (attempt + 1))
                continue
            print(f"  Search error: {e}")
            return []
    return []


def score_match(result: dict, target_title: str, target_artist: str) -> float:
    """Score how well a search result matches the target track."""
    title_lower = target_title.lower()
    artist_lower = target_artist.lower()
    r_title_lower = result["title"].lower()
    r_user_lower = result["user"].lower()

    score = 0.0

    # Title similarity (simple substring/token matching)
    title_tokens = set(re.split(r"[^a-z0-9]+", title_lower)) - {"", "original", "mix", "remix"}
    r_title_tokens = set(re.split(r"[^a-z0-9]+", r_title_lower)) - {"", "original", "mix", "remix"}

    if title_tokens:
        overlap = len(title_tokens & r_title_tokens) / len(title_tokens)
        score += overlap * 50

    # Exact title match bonus
    if title_lower in r_title_lower or r_title_lower in title_lower:
        score += 20

    # Artist similarity
    artist_tokens = set(re.split(r"[^a-z0-9]+", artist_lower)) - {""}
    # Handle multiple artists (comma separated)
    r_user_tokens = set(re.split(r"[^a-z0-9]+", r_user_lower)) - {""}

    if artist_tokens:
        artist_overlap = len(artist_tokens & r_user_tokens) / len(artist_tokens)
        score += artist_overlap * 30

    # Popularity bonus (more plays = more likely the right track)
    plays = result.get("playback_count") or 0
    if plays > 100000:
        score += 5
    elif plays > 10000:
        score += 2

    return score


def main():
    tracks = parse_tracks(INPUT_FILE)
    print(f"Loaded {len(tracks)} tracks from {INPUT_FILE.name}")

    # Load existing results to resume
    results = []
    searched_titles = set()
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text())
        results = existing.get("results", [])
        for r in results:
            searched_titles.add(f"{r['spotify_title']}||{r['spotify_artist']}")
        print(f"Resuming: {len(results)} already searched, {len(tracks) - len(results)} remaining")

    for i, track in enumerate(tracks):
        key = f"{track['title']}||{track['artist']}"
        if key in searched_titles:
            continue

        query = f"{track['artist']} {track['title']}"
        print(f"[{i+1}/{len(tracks)}] Searching: {query}")

        hits = search_track(query)
        if not hits:
            # Try with just title if artist+title fails
            hits = search_track(track["title"])

        # Score and sort
        for h in hits:
            h["match_score"] = score_match(h, track["title"], track["artist"])
        hits.sort(key=lambda x: x["match_score"], reverse=True)

        best = hits[0] if hits else None
        match_status = "matched" if best and best["match_score"] > 40 else "uncertain" if best else "not_found"

        results.append({
            "spotify_title": track["title"],
            "spotify_artist": track["artist"],
            "spotify_id": track.get("spotify_id"),
            "sc_match": best,
            "sc_candidates": hits[:3],
            "status": match_status,
        })

        if best:
            print(f"  -> {best['title']} by {best['user']} (score: {best['match_score']:.0f}, plays: {best.get('playback_count', 0)})")
        else:
            print(f"  -> NOT FOUND")

        # Save after every track (for resume capability)
        OUTPUT_FILE.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False))

        # Rate limit (be gentle, avoid 403s)
        time.sleep(3)

    # Summary
    matched = sum(1 for r in results if r["status"] == "matched")
    uncertain = sum(1 for r in results if r["status"] == "uncertain")
    not_found = sum(1 for r in results if r["status"] == "not_found")

    print(f"\n=== Summary ===")
    print(f"Matched:   {matched}/{len(results)}")
    print(f"Uncertain: {uncertain}/{len(results)}")
    print(f"Not found: {not_found}/{len(results)}")
    print(f"Results saved to {OUTPUT_FILE.name}")

    # Extract just the SC track IDs for playlist creation
    sc_ids = [r["sc_match"]["id"] for r in results if r["status"] in ("matched", "uncertain") and r["sc_match"]]
    ids_file = Path(__file__).parent / "sc_playlist_track_ids.json"
    ids_file.write_text(json.dumps({
        "playlist_name": "Dark Mode (Techno)",
        "track_ids": sc_ids,
        "total": len(sc_ids),
    }, indent=2))
    print(f"Track IDs for playlist: {len(sc_ids)} -> {ids_file.name}")


if __name__ == "__main__":
    main()