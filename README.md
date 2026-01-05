# Sonotheca
Tools &amp; Functions that help to build your offline Music Library

## SoundCloud vs local MP3 folder

This repo includes a small script to compare a SoundCloud playlist against a local folder of MP3s.

### Install

```bash
pip install -U yt-dlp mutagen
```

### Run

```bash
python soundcloud_check.py sync "<SOUNDCLOUD_PLAYLIST_URL>" "D:\\Path\\To\\MusicFolder" --csv tracks.csv --local-csv local.csv --joined-csv joined.csv --missing-csv missing.csv
```

- `tracks.csv` is the exported playlist metadata
- `local.csv` is the exported local ID3 metadata
- `joined.csv` shows playlist-to-local matches side-by-side
- `missing.csv` lists playlist tracks not found in your local folder

Matching uses **only** local MP3 ID3 metadata (`artist` + `title`). Filenames are not considered.

Matching logic is intersection-based: a playlist track is considered present if there is at least one overlapping token in the artist strings **and** at least one overlapping token in the title strings (case-insensitive).

Fallback: if the local MP3's ID3 **comment** tag contains the SoundCloud track URL, that URL will be used to match the playlist entry.
