"""Run playlist_downloader.py over several SoundCloud playlists, one after another.

Why this exists
---------------
SoundCloud rate-limits aggressively (HTTP 429) and playlist_downloader.py already
paces itself internally (5-20s between tracks, plus 60-180s breaks every 4-8
tracks). Running playlists in parallel multiplies the request rate and trips the
limiter, so this driver is **strictly sequential** and adds a longer cooldown
between playlists on top of the per-track pacing.

Usage
-----
    python download_batch.py --file playlists.txt [--out-dir DIR] [--log CSV] [--limit N]
    python download_batch.py URL1 URL2 ...

Each playlist runs to completion (or crash) before the next starts. A failing
playlist does not stop the batch — the error is recorded and the run continues.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Allow running from the repo root or anywhere else.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from playlist_downloader import analyze_playlist_download_options  # noqa: E402


def load_env(repo_root: Path) -> str:
    load_dotenv(repo_root / ".env")
    token = (os.getenv("SC_TOKEN") or "").strip()
    if not token:
        raise SystemExit(f"ERROR: SC_TOKEN not set in {repo_root / '.env'}")
    return token


def read_playlists(path: str) -> list[str]:
    urls: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def slug(url: str) -> str:
    """Playlist slug from a URL, with the owner prefix stripped.

    'https://soundcloud.com/timggg/sets/tims-classic-house' -> 'classic-house'
    """
    raw = url.rstrip("/").rsplit("/", 1)[-1]
    return raw.removeprefix("tims-")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="Playlist URLs (or use --file)")
    parser.add_argument("--file", help="Text file with one playlist URL per line")
    parser.add_argument("--out-dir", default="downloads/playlist")
    parser.add_argument("--log", default="playlist_download_log.csv")
    parser.add_argument(
        "--subdir-per-playlist",
        action="store_true",
        help="Write each playlist into <out-dir>/<slug>/ instead of one flat "
        "folder. Keeps playlists separable so they can be merged or moved "
        "individually later.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max tracks per playlist (smoke test). Default: all.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=None,
        help="Seconds between playlists. Default: random 120-300.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    token = load_env(repo_root)

    playlists = list(args.urls)
    if args.file:
        playlists += read_playlists(args.file)
    if not playlists:
        raise SystemExit("ERROR: no playlist URLs given (pass URLs or --file)")

    total = len(playlists)
    print(f"=== Sonotheca batch: {total} playlist(s) ===")
    print(f"out-dir={args.out_dir}  log={args.log}  limit={args.limit}")
    print(f"started {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    batch_start = time.time()

    failures: list[tuple[str, str]] = []
    for i, url in enumerate(playlists, start=1):
        print(f"--- [{i}/{total}] {slug(url)} ---")
        print(f"    {url}")
        t0 = time.time()
        # Optional per-playlist subfolder so playlists stay separable (and can
        # be merged or relocated individually later).
        playlist_dir = str(Path(args.out_dir) / slug(url)) if args.subdir_per_playlist else args.out_dir
        if args.subdir_per_playlist:
            print(f"    -> {playlist_dir}")
        try:
            analyze_playlist_download_options(
                url,
                token,
                output_dir=playlist_dir,
                log_csv=args.log,
                max_tracks=args.limit,
            )
            print(f"    done in {time.time() - t0:.0f}s")
        except KeyboardInterrupt:
            print("\nInterrupted by user — stopping batch.")
            return 130
        except Exception as e:  # keep the batch alive
            failures.append((slug(url), str(e)))
            print(f"    FAILED after {time.time() - t0:.0f}s: {e}")
            traceback.print_exc()

        if i < total:
            cooldown = args.cooldown if args.cooldown is not None else random.uniform(120, 300)
            print(f"    cooldown {cooldown:.0f}s before next playlist...\n")
            try:
                time.sleep(cooldown)
            except KeyboardInterrupt:
                print("\nInterrupted during cooldown — stopping batch.")
                return 130

    elapsed = time.time() - batch_start
    print(f"\n=== batch finished in {elapsed / 60:.1f} min ===")
    if failures:
        print("FAILED playlists:")
        for s, err in failures:
            print(f"  - {s}: {err}")
    else:
        print("All playlists processed without a crash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
