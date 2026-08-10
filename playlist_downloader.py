import yt_dlp
import os
from dotenv import load_dotenv
import csv
import random
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re


def check_soundcloud_external_download(track_url):
    """
    Check if a SoundCloud track has an external download link (Free Download button).
    
    Args:
        track_url: SoundCloud track URL
        
    Returns:
        dict with 'has_external_link' (bool) and 'external_link' (str or None)
    """
    try:
        # Fetch the SoundCloud page HTML
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(track_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the embedded JSON data in script tags
        # SoundCloud embeds track data in window.__sc_hydration
        for script in soup.find_all('script'):
            if script.string and 'window.__sc_hydration' in script.string:
                # Search for purchase_url in the JSON data
                match = re.search(r'["\']purchase_url["\']\s*:\s*["\']([^"\']+)', script.string)
                if match:
                    external_url = match.group(1)
                    # Decode unicode escapes if present
                    external_url = external_url.encode().decode('unicode_escape')
                    return {
                        'has_external_link': True,
                        'external_link': external_url
                    }
        
        return {'has_external_link': False, 'external_link': None}
        
    except Exception as e:
        print(f"Error checking external link: {e}")
        return {'has_external_link': False, 'external_link': None, 'error': str(e)}


def analyze_playlist_download_options(
    playlist_url: str,
    token: str,
    output_dir: str = "downloads/playlist",
    log_csv: str = "playlist_download_log.csv",
) -> None:
    """
    Analyze a SoundCloud playlist, log download options per track, and download via yt-dlp when needed.

    Rules:
    - Prefer native SoundCloud download when available (do NOT download via yt-dlp).
    - If native download is not available, download via yt-dlp (even if external link exists).
    - Always log availability and yt-dlp success/failure.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    log_path = Path(log_csv)
    is_new_log = not log_path.exists()
    
    def sleep_between_tracks():
        time.sleep(random.uniform(5, 20))

    def random_request_interval():
        return random.uniform(1, 3)

    tracks_since_long_pause = 0
    next_long_pause_threshold = random.randint(4, 8)

    def maybe_long_pause():
        # Occasionally take a longer break to look less like a bot
        nonlocal tracks_since_long_pause, next_long_pause_threshold
        tracks_since_long_pause += 1
        if tracks_since_long_pause >= next_long_pause_threshold:
            time.sleep(random.uniform(60, 180))
            tracks_since_long_pause = 0
            next_long_pause_threshold = random.randint(4, 8)

    def is_retryable_error(error_message: str) -> bool:
        return "404" in error_message or "401" in error_message

    # Step 1: get playlist entries with minimal requests (flat extraction)
    ydl_opts_list = {
        "extract_flat": True,
        "skip_download": True,
        "username": "oauth",
        "password": token,
        "sleep_interval_requests": random_request_interval(),
        "max_sleep_interval_requests": 20,
        "extractor_retries": 10,
        "retry_sleep": "extractor:exp=1:120",
        "ignoreerrors": True,
        "no_warnings": False,
    }
    
    # Step 2: per-track info (rate-limited requests)
    ydl_opts_info = {
        "format": "original/best",
        "username": "oauth",
        "password": token,
        "sleep_interval_requests": random_request_interval(),
        "max_sleep_interval_requests": 20,
        "extractor_retries": 10,
        "retry_sleep": "extractor:exp=1:120",
        "ignoreerrors": True,
        "no_warnings": False,
    }
    
    # Step 3: download with SAME rate-limited options as the playlist download cell (Cell 28)
    ydl_opts_download = {
        "format": "bestaudio/best",
        "outtmpl": str(output_path / "%(title)s.%(ext)s"),
        "username": "oauth",
        "password": token,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "writethumbnail": True,
        "embedthumbnail": True,
        "sleep_requests": random_request_interval(),
        "sleep_interval": random_request_interval(),
        "max_sleep_interval": 20,
        "sleep_interval_requests": random_request_interval(),
        "max_sleep_interval_requests": 20,
        "extractor_retries": 10,
        "retry_sleep": "extractor:exp=1:120",
        "ignoreerrors": True,
        "no_warnings": False,
    }
    
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "track_title",
                "track_url",
                "native_download_available",
                "external_link_available",
                "external_link",
                "ytdlp_downloaded",
                "ytdlp_error",
            ],
        )
        if is_new_log:
            writer.writeheader()
        
        # Get playlist entries flat to avoid bulk metadata requests
        entries = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts_list) as ydl_list:
                playlist_info = ydl_list.extract_info(playlist_url, download=False)
                entries = playlist_info.get("entries", []) if playlist_info else []
        except Exception as e:
            writer.writerow({
                "track_title": "",
                "track_url": playlist_url,
                "native_download_available": False,
                "external_link_available": False,
                "external_link": "",
                "ytdlp_downloaded": False,
                "ytdlp_error": f"playlist_error: {e}",
            })
            return
        
        def process_entry(entry):
            """Fetch info and download a single entry. Returns (row_dict, needs_retry)."""
            if not entry:
                return None, False
            track_url = entry.get("url") or entry.get("webpage_url")
            if not track_url:
                return None, False

            # Fetch full track info (rate-limited per request)
            try:
                info = ydl.extract_info(track_url, download=False)
            except Exception as e:
                error_message = str(e)
                return {
                    "track_title": entry.get("title", ""),
                    "track_url": track_url,
                    "native_download_available": False,
                    "external_link_available": False,
                    "external_link": "",
                    "ytdlp_downloaded": False,
                    "ytdlp_error": f"info_error: {error_message}",
                }, is_retryable_error(error_message)

            if not info:
                return {
                    "track_title": entry.get("title", ""),
                    "track_url": track_url,
                    "native_download_available": False,
                    "external_link_available": False,
                    "external_link": "",
                    "ytdlp_downloaded": False,
                    "ytdlp_error": "info_error: unavailable (None)",
                }, False

            title = info.get("title", "")
            native_available = bool(info.get("download_url"))

            external_link = ""
            external_available = False
            try:
                ext_result = check_soundcloud_external_download(track_url)
                external_available = bool(ext_result.get("has_external_link"))
                external_link = ext_result.get("external_link") or ""
            except Exception:
                pass

            # If native download is available, prefer it (no yt-dlp download)
            if native_available:
                return {
                    "track_title": title,
                    "track_url": track_url,
                    "native_download_available": True,
                    "external_link_available": external_available,
                    "external_link": external_link,
                    "ytdlp_downloaded": False,
                    "ytdlp_error": "",
                }, False

            # Otherwise download with yt-dlp (even if external link exists)
            ytdlp_ok = False
            ytdlp_err = ""
            try:
                with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_dl:
                    ydl_dl.download([track_url])
                ytdlp_ok = True
            except Exception as e:
                ytdlp_err = str(e)

            return {
                "track_title": title,
                "track_url": track_url,
                "native_download_available": False,
                "external_link_available": external_available,
                "external_link": external_link,
                "ytdlp_downloaded": ytdlp_ok,
                "ytdlp_error": ytdlp_err,
            }, is_retryable_error(ytdlp_err)

        def retry_queued_track(entry):
            """Retry a previously queued 404/401 entry once, tagging the log row."""
            row, _ = process_entry(entry)
            if row is not None:
                row["track_title"] = f"[retry] {row['track_title']}"
                writer.writerow(row)
            sleep_between_tracks()

        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            retry_queue = []
            for entry in entries:
                try:
                    row, needs_retry = process_entry(entry)
                    if row is None:
                        continue
                    writer.writerow(row)
                    if needs_retry:
                        # Don't retry immediately; download the next track first
                        retry_queue.append(entry)
                    sleep_between_tracks()
                    maybe_long_pause()

                    # Retry one queued 404/401 track after moving on to the next track
                    if retry_queue:
                        retry_queued_track(retry_queue.pop(0))
                except Exception as e:
                    writer.writerow({
                        "track_title": entry.get("title", "") if entry else "",
                        "track_url": (entry.get("url") or entry.get("webpage_url")) if entry else "",
                        "native_download_available": False,
                        "external_link_available": False,
                        "external_link": "",
                        "ytdlp_downloaded": False,
                        "ytdlp_error": f"unexpected_error: {e}",
                    })
                    sleep_between_tracks()

            # Retry any tracks still queued after the last entry was processed
            for entry in retry_queue:
                retry_queued_track(entry)

if __name__ == "__main__":

    os.environ['PATH'] = r'C:\ffmpeg\bin;' + os.environ['PATH']
    load_dotenv()
    TOKEN = os.getenv('SC_TOKEN')

    # Usage
    PLAYLIST_LINK = "https://soundcloud.com/timggg/sets/tims-melodic-deep-techno-house"
    analyze_playlist_download_options(PLAYLIST_LINK, TOKEN)


