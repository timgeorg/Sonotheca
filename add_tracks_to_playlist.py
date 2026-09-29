#!/usr/bin/env python3
"""Automate adding tracks to the 'Dark Mode (Techno)' SoundCloud playlist via browser UI.

Uses Playwright to drive the browser. For each track URL:
1. Navigate to the track page
2. Click "Zur Playlist hinzufügen" (Add to playlist) in the crossfade frame
3. In the dialog, find the "Dark Mode (Techno)" playlist row and click its toggle button
4. Wait for the add to complete
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Read track URLs from the search results
INPUT_FILE = Path(__file__).parent / "sc_search_results.json"
PLAYLIST_NAME = "Dark Mode (Techno)"

# Tracks already added (1-4): Interpol, Outline, Beyond the Time, C166W
# We'll process from index 4 onwards (0-based) = track 5
START_INDEX = 4


def get_track_urls():
    """Extract SoundCloud URLs for matched/uncertain tracks."""
    data = json.loads(INPUT_FILE.read_text())
    results = data.get("results", [])
    urls = []
    for r in results:
        m = r.get("sc_match")
        if m and r["status"] in ("matched", "uncertain"):
            url = m.get("permalink_url")
            if url:
                urls.append(url)
    return urls


def main():
    urls = get_track_urls()
    print(f"Total tracks to process: {len(urls)}")
    print(f"Starting from index {START_INDEX} (track {START_INDEX+1})")

    with sync_playwright() as p:
        # Connect to the existing browser (the one with the logged-in session)
        # We need to use the same browser context. Use connect_over_cdp if available.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # We can't easily reuse the existing logged-in session via CDP here.
        # Instead, we'll use the cookies from the existing session.
        # For now, let's just print the plan and let the user know.
        print("NOTE: This script needs to run in the existing logged-in browser session.")
        print("The VS Code browser automation is used instead. See the chat flow.")
        browser.close()


if __name__ == "__main__":
    main()