#!/usr/bin/env python3
"""Create a SoundCloud playlist and add tracks from the search results JSON."""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SC_TOKEN")
if not TOKEN:
    print("ERROR: SC_TOKEN not found in .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"OAuth {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

INPUT_FILE = Path(__file__).parent / "sc_search_results.json"
PLAYLIST_NAME = "Dark Mode (Techno)"
PLAYLIST_DESCRIPTION = "Cloned from Spotify playlist 'Dark Mode (Techno)' by irgendsontim. 149 tracks on Spotify, matched on SoundCloud."


def get_my_user_id():
    """Get the current user's ID."""
    resp = requests.get("https://api-v2.soundcloud.com/me", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["id"]


def get_track_ids():
    """Extract SoundCloud track IDs from search results."""
    data = json.loads(INPUT_FILE.read_text())
    results = data.get("results", [])

    # Only include matched and uncertain (not "not_found")
    track_ids = []
    for r in results:
        match = r.get("sc_match")
        if match and r["status"] in ("matched", "uncertain"):
            track_ids.append(match["id"])

    return track_ids


def create_playlist(user_id, name, description):
    """Create a new playlist."""
    # SoundCloud v2 API: POST /playlists
    payload = {
        "playlist": {
            "title": name,
            "description": description,
            "sharing": "private",
            "tracks": [],  # Will add tracks separately
        }
    }
    resp = requests.post(
        f"https://api-v2.soundcloud.com/users/{user_id}/playlists",
        headers=HEADERS,
        json=payload,
    )
    if resp.status_code == 201:
        playlist = resp.json()
        print(f"Created playlist: {playlist['title']} (id: {playlist['id']})")
        return playlist["id"]
    else:
        print(f"Create playlist error: {resp.status_code}")
        print(resp.text[:500])
        return None


def add_tracks_to_playlist(playlist_id, track_ids):
    """Add tracks to the playlist. SoundCloud allows adding in batches."""
    # PUT /playlists/{id} with the full track list
    # The API expects track URIs in the format: soundcloud:tracks:{id}
    track_uris = [{"id": tid} for tid in track_ids]

    # SoundCloud playlist PUT replaces all tracks, so we add all at once
    payload = {
        "playlist": {
            "tracks": track_uris,
        }
    }
    resp = requests.put(
        f"https://api-v2.soundcloud.com/playlists/{playlist_id}",
        headers=HEADERS,
        json=payload,
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"Added {len(data.get('tracks', []))} tracks to playlist")
        return True
    else:
        print(f"Add tracks error: {resp.status_code}")
        print(resp.text[:500])
        return False


def main():
    print("Getting user ID...")
    user_id = get_my_user_id()
    print(f"User ID: {user_id}")

    print("\nGetting track IDs from search results...")
    track_ids = get_track_ids()
    print(f"Found {len(track_ids)} track IDs to add")

    if not track_ids:
        print("No tracks to add!")
        sys.exit(1)

    print(f"\nCreating playlist '{PLAYLIST_NAME}'...")
    playlist_id = create_playlist(user_id, PLAYLIST_NAME, PLAYLIST_DESCRIPTION)

    if not playlist_id:
        print("Failed to create playlist")
        sys.exit(1)

    print(f"\nAdding {len(track_ids)} tracks to playlist {playlist_id}...")
    # Add in batches of 50 to avoid payload size issues
    batch_size = 50
    success = True
    all_added = []
    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i:i + batch_size]
        print(f"  Batch {i//batch_size + 1}: tracks {i+1}-{min(i+batch_size, len(track_ids))}")

        track_uris = [{"id": tid} for tid in all_added + batch]
        payload = {"playlist": {"tracks": track_uris}}

        resp = requests.put(
            f"https://api-v2.soundcloud.com/playlists/{playlist_id}",
            headers=HEADERS,
            json=payload,
        )
        if resp.status_code in (200, 201):
            all_added = all_added + batch
            print(f"  OK ({len(all_added)} total)")
        else:
            print(f"  Error: {resp.status_code}")
            print(f"  {resp.text[:300]}")
            success = False

        time.sleep(1)

    if success:
        print(f"\n=== Done ===")
        print(f"Playlist: {PLAYLIST_NAME}")
        print(f"Tracks added: {len(all_added)}/{len(track_ids)}")
        print(f"URL: https://soundcloud.com/user-{user_id}/sets/dark-mode-techno")
    else:
        print(f"\nSome tracks may not have been added. Check the playlist manually.")


if __name__ == "__main__":
    main()