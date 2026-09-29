---
source: auto
tags:
  - index
---
# Index — Sonotheca

- [[SKILL.md]] — Comprehensive skill/guide for Spotify → SoundCloud playlist migration (extract, search, match, create, add tracks via browser automation with DataDome evasion).
- [[sc_search_and_match.py]] — Searches SoundCloud API for each Spotify track, scores matches by title/artist/duration similarity, saves results to JSON.
- [[create_sc_playlist.py]] — API-based playlist creation script (blocked by DataDome captcha — use browser UI approach instead).
- [[add_tracks_to_playlist.py]] — Standalone Playwright script for adding tracks to a SoundCloud playlist (reference only, can't reuse logged-in browser session).
- [[playlist_downloader.py]] — Downloads tracks from SoundCloud using yt-dlp.
- [[download_batch.py]] — Runs playlist_downloader.py over several playlists strictly sequentially (rate-limit safe) with cooldowns between playlists and a per-playlist crash guard.
- [[soundcloud_check.py]] — Utility for checking SoundCloud playlist/track state via API.
- [[playlist_status.py]] — Read-only playlist→local-file comparison: which tracks are downloaded vs missing (uses SC API resolve + tracks?ids= batch, no downloads).
- [[download_single.py]] — yt-dlp download of individual SoundCloud tracks into the vault downloads/playlist/ folder; detects DRM/no-file honestly.
- [[find_alternatives.py]] — Finds duration-matched (±1s) alternative uploads (label/premiere/repost) of a wanted track — the rescue path for DRM-blocked tracks.
- [[sc_search_results.json]] — Search/match results for the "Dark Mode (Techno)" Spotify playlist.
- [[sc_search_results_edm.json]] — Search/match results for the "Techno EDM Hybrid" Spotify playlist.
- [[sc_playlist_track_ids.json]] — Track IDs for a SoundCloud playlist.
- [[spotify_dark_mode_techno.txt]] — 149 tracks from the "Dark Mode (Techno)" Spotify playlist.
- [[spotify_techno_edm_hybrid.txt]] — 77 tracks from the "Techno EDM Hybrid" Spotify playlist.
- [[.env]] — Environment file containing `SC_TOKEN` (SoundCloud OAuth token for API access).
- [[.gitignore]] — Git ignore rules.
- [[README.md]] — Project readme.
- [[LICENSE]] — Project license.
- [[downloads/]] — Downloaded audio files.
- [[sandbox/]] — Experimental scripts and work-in-progress.