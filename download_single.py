"""Download individual SoundCloud tracks via yt-dlp (same options as
playlist_downloader.py, minus the per-track availability probes).

Usage:
    python download_single.py https://soundcloud.com/tonaltheory/step-to-the-rhythm
    python download_single.py URL1 URL2 URL3 ...

Output goes to downloads/playlist/ in the vault root (same folder the playlist
downloader writes to). Needs SC_TOKEN in .env.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import yt_dlp
from dotenv import load_dotenv


def random_request_interval() -> float:
    return random.uniform(1, 3)


def download_one(url: str, token: str, output_path: Path) -> str:
    """Download a single track, returning a short status string."""
    outtmpl = str(output_path / "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "username": "oauth",
        "password": token,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
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

    print(f"\n>>> {url}")
    import time
    start = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # A real download writes (or rewrites) an audio file. Detect success by
        # looking for any output file modified at/after the start of this run.
        title = (info or {}).get("title") or ""
        produced = [p for p in output_path.iterdir() if p.stat().st_mtime >= start - 1]

        # yt-dlp leaves the .mp3 plus optional .jpg/.webp/.m4a/.temp artifacts.
        mp3s = [p for p in produced if p.suffix.lower() == ".mp3"]
        if mp3s:
            print(f"    OK: {title or url}")
            return "ok"

        msg = "no file produced (DRM-protected / geo-blocked / no formats)"
        if title:
            msg = f"{msg} — title but no file: {title}"
        if produced:
            msg = f"{msg} — wrote (non-mp3): {[p.name for p in produced][:3]}"
        print(f"    FAIL: {msg}")
        return f"fail: {msg}"
    except Exception as e:
        print(f"    FAIL: {e}")
        return f"fail: {e}"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return 0

    load_dotenv()
    token = os.getenv("SC_TOKEN", "")
    if not token:
        print("ERROR: SC_TOKEN not set in .env")
        return 2

    # Vault-root downloads folder (absolute, independent of CWD).
    output_path = Path(__file__).resolve().parent.parent.parent / "downloads" / "playlist"
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {output_path}")

    results = []
    for u in sys.argv[1:]:
        results.append(download_one(u, token, output_path))

    print("\n=== Summary ===")
    for u, r in zip(sys.argv[1:], results):
        print(f"  {r if r=='ok' else r}: {u}")
    return 0 if all(r == "ok" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
