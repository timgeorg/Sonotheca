# Sonotheca
Tools and scripts for building an offline music library from SoundCloud playlists, with traceable logs and a focus on matching what you already have locally.

## What this repo is for

This repo centers around two related workflows:

1) Downloading tracks from a SoundCloud playlist with clear logging and rate-limited requests.
2) Comparing a SoundCloud playlist to a local MP3 folder using ID3 metadata.

The code is intentionally practical: gather data, log everything, and make it easy to review what happened without guesswork.

## Primary workflow: playlist_downloader.py

This is the main script. It analyzes a SoundCloud playlist and logs what download options exist per track. If a native SoundCloud download is not available, it downloads via yt-dlp.

### Behavior overview

- Uses an authenticated SoundCloud token for playlist access.
- For each track, checks:
	- native SoundCloud download availability
	- external download link (Free Download button) availability
- If native download is available, it logs the track and skips yt-dlp.
- If native download is not available, it downloads via yt-dlp and logs success or failure.
- Writes a CSV log for each run (appends to an existing log).
- Rate-limits requests to reduce the chance of 429s.

### Install

```bash
pip install -U yt-dlp python-dotenv requests beautifulsoup4
```

You also need FFmpeg available on your PATH for audio conversion and metadata embedding.

### Configure token

Create a .env file in the repo root and set:

```
SC_TOKEN=your_soundcloud_oauth_token
```

The script uses this token via python-dotenv.

### Run

Update the playlist URL in the script or call it from another driver module. The current default is:

```python
PLAYLIST_LINK = "https://soundcloud.com/user-251038582/sets/10yeardancerobix"
```

Then run:

```bash
python playlist_downloader.py
```

### Output

By default, downloads go to:

```
downloads/playlist/
```

The log CSV defaults to:

```
playlist_download_log.csv
```

Columns in the log:

- track_title
- track_url
- native_download_available
- external_link_available
- external_link
- ytdlp_downloaded
- ytdlp_error

## SoundCloud vs local MP3 folder

This workflow compares a SoundCloud playlist against a local folder of MP3s.

### Install

```bash
pip install -U yt-dlp mutagen
```

### Run

```bash
python soundcloud_check.py sync "<SOUNDCLOUD_PLAYLIST_URL>" "D:\Path\To\MusicFolder" --csv tracks.csv --local-csv local.csv --joined-csv joined.csv --missing-csv missing.csv
```

- `tracks.csv` is the exported playlist metadata
- `local.csv` is the exported local ID3 metadata
- `joined.csv` shows playlist-to-local matches side-by-side
- `missing.csv` lists playlist tracks not found in your local folder

Matching uses only local MP3 ID3 metadata (`artist` + `title`). Filenames are not considered.

Matching logic is intersection-based: a playlist track is considered present if there is at least one overlapping token in the artist strings and at least one overlapping token in the title strings (case-insensitive).

Fallback: if the local MP3's ID3 comment tag contains the SoundCloud track URL, that URL is used to match the playlist entry.

## Sandbox

The sandbox/ directory is exploratory and contains notebooks and helper scripts used to test ideas, inspect playlist data, and prototype automation steps. It is not required for the main workflows and can be treated as scratch space.

## Notes and intent

- This repo is built to be auditable: logs and CSV exports are first-class outputs.
- Downloads and matching are intentionally conservative to avoid false positives and over-downloading.
- If you are extending the project, keep the same mindset: prefer logs and inspectable artifacts over silent behavior.
