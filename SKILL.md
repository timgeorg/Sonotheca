---
name: spotify-to-soundcloud-migration
description: >
  USE when the user wants to clone/migrate a Spotify playlist to SoundCloud.
  Covers the full pipeline: extracting tracks from a Spotify playlist URL,
  searching SoundCloud for matching tracks, scoring matches, creating a
  SoundCloud playlist, and adding tracks via browser automation with
  human-like delays to avoid DataDome bot detection.

  Key constraints:
  - SoundCloud API write operations (POST/PUT) are blocked by DataDome captcha.
  - Must use browser UI automation (Playwright) for adding tracks.
  - Must use randomized human-like delays (3-8s between tracks) to avoid triggering captcha.
  - Fresh browser sessions are needed if a session gets DataDome-flagged.
  - After ~12-15 rapid additions, DataDome starts blocking — pace is critical.
  - **SoundCloud playlists have a HARD 500-track limit.** Playlists >500 tracks
    must be split into multiple playlists (e.g. "Name", "Name #2", "Name #3").
---

# Spotify → SoundCloud Playlist Migration

## Overview

This skill clones a Spotify playlist to a SoundCloud playlist. The pipeline has
four stages:

1. **Extract** tracks from the Spotify playlist URL
2. **Search & Match** each track on SoundCloud
3. **Create** a SoundCloud playlist (via browser UI)
4. **Add** tracks to the playlist via browser automation with human-like delays

## Prerequisites

- Python venv with `requests`, `python-dotenv` installed
- SoundCloud `.env` file with `SC_TOKEN` (OAuth token)
- SoundCloud account logged in in VS Code's integrated browser
- `sc_search_and_match.py` script in the Sonotheca repository

## Stage 1: Extract Spotify Tracks

### Method A: Spotify Embed API (works for playlists ≤ 100 tracks)

```python
import requests

playlist_id = "2MzqTNFNOrH26U769B7oKz"  # from the Spotify URL
embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
resp = requests.get(embed_url)
# Parse __NEXT_DATA__ JSON from the HTML
# Extract trackList: [{ title, artists: [{ name }], id }]
```

The embed API returns `__NEXT_DATA__` JSON containing a `trackList` array.
**Limitation**: capped at 100 tracks, no pagination.

### Method B: DOM Scrape (for playlists > 100 tracks)

Navigate to the Spotify playlist page in the browser, scrape `[role="group"]`
elements. Filter out "Recommended" tracks by finding the "Recommended" heading
and only taking tracks before it.

### Output format

Save as a text file, one track per line:
```
title --- artist --- spotify_track_id
```

Example: `spotify_playlist.txt`

## Stage 2: Search & Match on SoundCloud

Use `sc_search_and_match.py`:

```bash
cd /home/tim/Vault/Repositories/Sonotheca
# Edit INPUT_FILE and OUTPUT_FILE at the top of the script
# Set INPUT_FILE = "spotify_playlist.txt"
# Set OUTPUT_FILE = "sc_search_results.json"
python sc_search_and_match.py
```

The script:
- Searches `https://api-v2.soundcloud.com/search/tracks?q={query}&limit=5` for each track
- Scores matches by title similarity, artist match, and duration proximity
- Saves results as JSON with best match + candidates for each track
- Has resume capability (skips already-searched tracks)
- Rate-limited (3-second delay between searches)

### Result JSON structure

```json
{
  "results": [
    {
      "spotify_title": "Komtie (Kom Tie Dan He!)",
      "spotify_artist": "Dimitri Vegas & Like Mike, ...",
      "spotify_id": "4eKzx7tcRxOLpa4QWmRHse",
      "sc_match": {
        "id": 1534945861,
        "title": "Dimitri Vegas & Like Mike x ...",
        "permalink_url": "https://soundcloud.com/smashthehouse/...",
        "duration": 142238,
        "user": "Smash The House",
        "match_score": 75.33
      },
      "sc_candidates": [...]
    }
  ]
}
```

### Manual review

After searching, review low-score matches (score < 60). Common false positives:
- DJ sets/mixes instead of individual tracks
- Remixes with similar names but wrong artists
- "Techno remix" versions that are different from the original

## Stage 3: Create SoundCloud Playlist

### API approach (BLOCKED by DataDome)

```python
# This does NOT work — DataDome returns 403 + captcha interstitial
import requests
headers = {"Authorization": f"OAuth {token}"}
r = requests.post("https://api-v2.soundcloud.com/playlists", json={...}, headers=headers)
# → 403 with captcha URL
```

### Browser UI approach (works)

1. Open a fresh browser session in VS Code's integrated browser
2. Navigate to `https://soundcloud.com/login`
3. User logs in manually (cannot automate — OAuth iframe blocks Playwright)
4. Navigate to `https://soundcloud.com/discover`
5. Click "Create playlist" or navigate to any track and use the add-to-playlist dialog
6. Create a new playlist from the dialog

## Stage 4: Add Tracks via Browser Automation

### CRITICAL: DataDome Bot Detection

SoundCloud uses **DataDome** for bot detection. Key learnings:

- **API writes (POST/PUT) are ALWAYS blocked** → 403 + captcha interstitial
- **Browser UI clicks work** but only with proper pacing
- **First ~12 rapid additions succeed**, then DataDome starts blocking
- **DataDome fingerprints the browser session** — once flagged, ALL writes fail
- **Fresh browser session** resets the fingerprint but requires re-login

### CRITICAL: 500-Track Playlist Limit

**SoundCloud playlists have a hard maximum of 500 tracks.** This is a platform
limit, not a bot-detection issue. When a playlist reaches 500 tracks:

- The "add to playlist" toggle button becomes **disabled** for that playlist.
- The button's tooltip reads: *"Playlists können maximal 500 Tracks enthalten.
  Füge diesen Track einer anderen Playlist hinzu oder leg eine neue an."*
  (Playlists can contain a maximum of 500 tracks. Add this track to another
  playlist or create a new one.)
- **The click still registers as "ok"** in automation — the UI shows the toggle
  being clicked, but the track is NOT added. This is a **silent failure**.
- The playlist track count stays frozen at 500.

**How to detect it:** After a batch, verify the playlist count via the resolve
API. If the count is stuck at 500 despite "ok" results, the playlist is full.

```javascript
// Check if a playlist is at the 500-track cap
const res = await fetch('https://api-v2.soundcloud.com/resolve?url=https://soundcloud.com/USER/sets/PLAYLIST&client_id=CLIENT_ID');
const data = await res.json();
const isFull = data.track_count >= 500;  // true = at cap
```

**How to handle it:** For Spotify playlists with >500 tracks, split into
multiple SoundCloud playlists:
- "Playlist Name" (tracks 1-500)
- "Playlist Name #2" (tracks 501-1000)
- "Playlist Name #3" (tracks 1001+)

Create each new playlist via the same browser UI flow, then add the remaining
tracks to it. The `#2`/`#3` suffix keeps them grouped in the library.

### Working approach: Playwright clicks + human-like delays

```
For each track:
  1. Random pre-navigation delay (3-7 seconds, 15% chance of +5s longer pause)
  2. Navigate to track URL (waitUntil: 'domcontentloaded')
  3. Random page-reading delay (4-7 seconds)
  4. Random scroll (100-400px)
  5. Short delay (0.5-1.5 seconds)
  6. Find crossfade iframe (URL contains '/n/')
  7. Click "Zur Playlist hinzufügen" button via Playwright getByRole
  8. Random dialog-reading delay (1.5-3.5 seconds)
  9. Find playlist in .modal__content by searching <li> elements
  10. Click the playlist's toggle button via Playwright locator
  11. Wait for add to process (3-5 seconds)
  12. Check for DataDome captcha iframe → if detected, STOP
  13. Check for error "Leider ist etwas schiefgegangen" → retry or skip
  14. Press Escape to close modal
  15. Short delay (0.5-1 second)
```

### Key implementation details

**Use Playwright locators, NOT `page.evaluate` DOM clicks:**
```javascript
// ✅ WORKS: Playwright click triggers proper React synthetic events
const btn = frame.getByRole('button', { name: 'Zur Playlist hinzufügen' });
await btn.click({ timeout: 5000 });

// ❌ DOES NOT WORK: Native DOM .click() doesn't trigger React handlers
await page.evaluate(() => {
  document.querySelector('button[aria-label="Zur Playlist hinzufügen"]').click();
});
```

**Crossfade iframe:**
- Track pages embed a crossfade iframe from the `/n/` subpath
- The "Add to playlist" button lives inside this iframe
- Access via `page.frames()` → find frame where `f.url().includes('/n/')`

**Playlist toggle in modal:**
- After clicking "Add to playlist", a modal opens in the main document (not iframe)
- Modal has class `.modal__content`
- Playlists are `<li>` elements inside the modal
- Find the target playlist by text content, then click its child `<button>`

```javascript
const modal = page.locator('.modal__content');
const targetPlaylist = modal.locator('li', { hasText: 'Playlist Name' }).first();
const toggleBtn = targetPlaylist.locator('button').first();
await toggleBtn.click({ timeout: 5000 });
```

**Captcha detection:**
```javascript
const captcha = await page.evaluate(() => 
  !!document.querySelector('iframe[title="Verification system"]')
);
if (captcha) {
  // Session is burned — need fresh browser session + re-login
  STOP;
}
```

**Error detection:**
```javascript
const error = await page.evaluate(() => {
  const p = document.querySelector('.modal__content p');
  return p ? p.textContent : null;
});
if (error && error.includes('schiefgegangen')) {
  // Server rejected the add — track not added
  // Can retry or skip
}
```

### Verifying track count

```javascript
const count = await page.evaluate(async () => {
  const res = await fetch(
    'https://api-v2.soundcloud.com/playlists/{PLAYLIST_ID}' +
    '?client_id=SYyXueujTqHDMhknjklMhdgKi3KfRssi&representation=full'
  );
  const data = await res.json();
  return data.tracks?.length;
});
```

Note: `client_id` works for read operations. `OAuth` token is needed for writes
but DataDome blocks API writes regardless.

### Handling failed tracks

Some tracks may fail because the crossfade iframe doesn't load. Retry with:
- `waitUntil: 'networkidle'` instead of `'domcontentloaded'`
- Extended wait time (8-10 seconds after navigation)
- Fallback to `page.evaluate` DOM click as last resort

### When DataDome blocks the session

1. Open a **new browser page** with `forceNew: true`
2. Navigate to `https://soundcloud.com/login`
3. User logs in manually
4. Do some "human" browsing first (browse discover page, scroll, visit library)
5. Resume adding tracks with the same delay pattern

The pre-browsing before the first write is critical — DataDome assesses the
session before allowing the first write operation.

## Files in Sonotheca Repository

| File | Purpose |
|------|---------|
| `sc_search_and_match.py` | Searches SoundCloud for each Spotify track, scores matches |
| `create_sc_playlist.py` | API-based playlist creation (BLOCKED by DataDome — use browser instead) |
| `add_tracks_to_playlist.py` | Standalone Playwright script (reference only) |
| `spotify_*.txt` | Input track list files |
| `sc_search_results*.json` | Search/match results |
| `.env` | Contains `SC_TOKEN` (SoundCloud OAuth token) |

## Quick Start Checklist

1. Get Spotify playlist URL → extract track IDs
2. Save tracks to `spotify_{name}.txt` in format `title --- artist --- id`
3. Edit `sc_search_and_match.py` INPUT_FILE and OUTPUT_FILE
4. Run `python sc_search_and_match.py`
5. Review matches (check for wrong matches, DJ sets, etc.)
6. Open fresh browser → user logs in to SoundCloud
7. Create playlist via browser UI
8. Add tracks with randomized human-like delays (batch of 10 per code execution)
9. If DataDome captcha appears → open new session, re-login, resume
10. Verify final track count via API