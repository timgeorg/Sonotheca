from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class Track:
	artist: str
	title: str
	url: str | None = None
	track_id: str | None = None
	duration: float | None = None
	comment_url: str | None = None

	def display(self) -> str:
		if self.artist and self.title:
			return f"{self.artist} - {self.title}"
		if self.title:
			return self.title
		if self.url:
			return self.url
		return "<unknown track>"


_SC_URL_RE = re.compile(r"https?://(?:on\.)?soundcloud\.com/[^\s\]\)\"\'<>]+", re.IGNORECASE)

def _track_key(artist: str, title: str) -> tuple[str, str] | None:
	artist = (artist or "").strip()
	title = (title or "").strip()
	if not artist or not title:
		return None
	return (artist, title)

def _casefold(text: str) -> str:
	return (text or "").strip().casefold()


def _tokenize(text: str) -> set[str]:
	"""Tokenize a string for intersection-style matching.

	This is intentionally simple: split on non-alphanumerics and compare case-insensitively.
	"""
	t = _casefold(text)
	if not t:
		return set()
	for ch in t:
		# Fast path: avoid regex; normalize separators to spaces.
		if not ("a" <= ch <= "z" or "0" <= ch <= "9" or ch.isspace()):
			t = t.replace(ch, " ")
	return {p for p in t.split() if p}


def _normalize_url(url: str | None) -> str | None:
	if not url:
		return None
	u = url.strip()
	if not u:
		return None
	# Remove trailing slashes for easier matching.
	while u.endswith("/"):
		u = u[:-1]
	return u.casefold()


def _extract_soundcloud_url_from_comment(mp3_path: Path) -> str | None:
	"""Extract a SoundCloud URL from ID3 comment (COMM) frames, if present."""
	try:
		from mutagen.id3 import ID3  # type: ignore
		from mutagen.id3 import COMM  # type: ignore
	except ImportError:
		return None

	try:
		tags = ID3(str(mp3_path))
	except Exception:
		return None

	comments: list[str] = []
	for frame in tags.values():
		if isinstance(frame, COMM):
			try:
				text = " ".join(str(x) for x in (frame.text or []))
			except Exception:
				text = ""
			if text:
				comments.append(text)

	blob = "\n".join(comments)
	if not blob:
		return None

	m = _SC_URL_RE.search(blob)
	return m.group(0).strip() if m else None


def export_playlist_to_csv(playlist_url: str, csv_path: str | Path) -> list[Track]:
	"""Extract playlist metadata via yt-dlp and export it to a CSV."""
	try:
		from yt_dlp import YoutubeDL  # type: ignore
	except ImportError as exc:
		raise RuntimeError(
			"yt-dlp is required. Install with: pip install -U yt-dlp"
		) from exc

	ydl_opts = {
		"skip_download": True,
		"quiet": True,
		"extract_flat": False,
		"nocheckcertificate": True,
	}

	tracks: list[Track] = []
	with YoutubeDL(ydl_opts) as ydl:
		info = ydl.extract_info(playlist_url, download=False)

	entries = (info or {}).get("entries") or []
	for entry in entries:
		if not entry:
			continue

		title = (entry.get("title") or "").strip()
		artist = (
			(entry.get("uploader") or "").strip()
			or (entry.get("artist") or "").strip()
			or (entry.get("creator") or "").strip()
		)
		url = (entry.get("webpage_url") or entry.get("original_url") or "") or None
		track_id = (str(entry.get("id")) if entry.get("id") is not None else None)
		duration = entry.get("duration")
		duration_f = float(duration) if isinstance(duration, (int, float)) else None

		tracks.append(
			Track(
				artist=artist,
				title=title,
				url=url,
				track_id=track_id,
				duration=duration_f,
			)
		)

	csv_path = Path(csv_path)
	csv_path.parent.mkdir(parents=True, exist_ok=True)

	with csv_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(["Index", "Artist", "Title", "DurationSec", "Id", "Url"])
		for i, t in enumerate(tracks, start=1):
			writer.writerow([i, t.artist, t.title, t.duration, t.track_id, t.url])

	return tracks


def iter_local_mp3_tracks(folder: str | Path) -> Iterable[Track]:
	folder_path = Path(folder)
	if not folder_path.exists():
		raise FileNotFoundError(f"Folder not found: {folder_path}")

	try:
		from mutagen.easyid3 import EasyID3  # type: ignore
		from mutagen.mp3 import MP3  # type: ignore
	except ImportError:
		raise RuntimeError(
			"mutagen is required to read local MP3 ID3 tags. Install with: pip install -U mutagen"
		)

	for path in folder_path.rglob("*.mp3"):
		artist = ""
		title = ""
		duration: float | None = None
		comment_url: str | None = None

		try:
			tags = EasyID3(str(path))
			artist = (tags.get("artist") or [""])[0].strip()
			title = (tags.get("title") or [""])[0].strip()
		except Exception:
			artist = ""
			title = ""

		try:
			audio = MP3(str(path))
			duration = float(audio.info.length) if getattr(audio, "info", None) else None
		except Exception:
			duration = None

		comment_url = _extract_soundcloud_url_from_comment(path)

		yield Track(
			artist=artist,
			title=title,
			url=str(path),
			duration=duration,
			comment_url=comment_url,
		)


def export_local_to_csv(local_folder: str | Path, csv_path: str | Path) -> list[Track]:
	local_tracks = list(iter_local_mp3_tracks(local_folder))
	csv_path = Path(csv_path)
	csv_path.parent.mkdir(parents=True, exist_ok=True)

	with csv_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(["Index", "Artist", "Title", "DurationSec", "Path", "SoundCloudUrl"])
		for i, t in enumerate(local_tracks, start=1):
			writer.writerow([i, t.artist, t.title, t.duration, t.url, t.comment_url])

	return local_tracks


def sync(
	playlist_url: str,
	local_folder: str | Path,
	*,
	playlist_csv_path: str | Path = "tracks.csv",
	local_csv_path: str | Path = "local.csv",
	joined_csv_path: str | Path | None = "joined.csv",
	missing_csv_path: str | Path | None = "missing.csv",
) -> list[Track]:
	"""Export playlist to CSV and return playlist tracks missing from local folder."""
	playlist_tracks = export_playlist_to_csv(playlist_url, playlist_csv_path)
	local_tracks = export_local_to_csv(local_folder, local_csv_path)

	local_artist_index: dict[str, set[int]] = {}
	local_title_index: dict[str, set[int]] = {}
	local_sc_url_index: dict[str, set[int]] = {}
	skipped_local = 0
	for idx, t in enumerate(local_tracks):
		artist_tokens = _tokenize(t.artist)
		title_tokens = _tokenize(t.title)
		if not artist_tokens or not title_tokens:
			skipped_local += 1
			continue
		for tok in artist_tokens:
			local_artist_index.setdefault(tok, set()).add(idx)
		for tok in title_tokens:
			local_title_index.setdefault(tok, set()).add(idx)
		sc_url = _normalize_url(t.comment_url)
		if sc_url:
			local_sc_url_index.setdefault(sc_url, set()).add(idx)

	missing: list[Track] = []
	joined_rows: list[tuple[str, Track, Track | None]] = []
	for t in playlist_tracks:
		# 1) Fallback match: SoundCloud URL stored in local MP3 comment.
		playlist_sc_url = _normalize_url(t.url)
		if playlist_sc_url and playlist_sc_url in local_sc_url_index:
			match_idx = next(iter(local_sc_url_index[playlist_sc_url]))
			joined_rows.append(("url", t, local_tracks[match_idx]))
			continue

		# 2) Primary match: token intersections (artist AND title).
		artist_tokens = _tokenize(t.artist)
		title_tokens = _tokenize(t.title)
		if not artist_tokens or not title_tokens:
			joined_rows.append(("unmatchable", t, None))
			missing.append(t)
			continue

		artist_candidates: set[int] = set()
		for tok in artist_tokens:
			artist_candidates |= local_artist_index.get(tok, set())

		title_candidates: set[int] = set()
		for tok in title_tokens:
			title_candidates |= local_title_index.get(tok, set())

		intersection = artist_candidates & title_candidates
		if intersection:
			match_idx = next(iter(intersection))
			joined_rows.append(("tokens", t, local_tracks[match_idx]))
		else:
			joined_rows.append(("missing", t, None))
			missing.append(t)

	if joined_csv_path is not None:
		joined_csv_path = Path(joined_csv_path)
		joined_csv_path.parent.mkdir(parents=True, exist_ok=True)
		with joined_csv_path.open("w", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			writer.writerow(
				[
					"MatchMethod",
					"PlaylistArtist",
					"PlaylistTitle",
					"PlaylistDurationSec",
					"PlaylistId",
					"PlaylistUrl",
					"LocalArtist",
					"LocalTitle",
					"LocalDurationSec",
					"LocalPath",
					"LocalSoundCloudUrl",
				]
			)
			for method, pl, loc in joined_rows:
				writer.writerow(
					[
						method,
						pl.artist,
						pl.title,
						pl.duration,
						pl.track_id,
						pl.url,
						(loc.artist if loc else ""),
						(loc.title if loc else ""),
						(loc.duration if loc else ""),
						(loc.url if loc else ""),
						(loc.comment_url if loc else ""),
					]
				)

	if missing_csv_path is not None:
		missing_csv_path = Path(missing_csv_path)
		missing_csv_path.parent.mkdir(parents=True, exist_ok=True)
		with missing_csv_path.open("w", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			writer.writerow(["Index", "Artist", "Title", "DurationSec", "Id", "Url"])
			for i, t in enumerate(missing, start=1):
				writer.writerow([i, t.artist, t.title, t.duration, t.track_id, t.url])

	if skipped_local:
		print(
			f"Note: skipped {skipped_local} local MP3(s) with missing/broken ID3 artist/title tags."
		)

	return missing


def _main() -> int:
	parser = argparse.ArgumentParser(
		description=(
			"Compare a SoundCloud playlist to a local MP3 folder and list missing tracks."
		)
	)
	sub = parser.add_subparsers(dest="cmd", required=True)

	sync_p = sub.add_parser("sync", help="Export playlist CSV and print missing tracks")
	sync_p.add_argument("playlist_url", help="SoundCloud playlist URL")
	sync_p.add_argument("local_folder", help="Folder containing MP3 files")
	sync_p.add_argument("--csv", dest="csv_path", default="tracks.csv")
	sync_p.add_argument("--local-csv", dest="local_csv", default="local.csv")
	sync_p.add_argument("--joined-csv", dest="joined_csv", default="joined.csv")
	sync_p.add_argument("--missing-csv", dest="missing_csv", default="missing.csv")

	args = parser.parse_args()

	if args.cmd == "sync":
		missing = sync(
			args.playlist_url,
			args.local_folder,
			playlist_csv_path=args.csv_path,
			local_csv_path=args.local_csv,
			joined_csv_path=args.joined_csv,
			missing_csv_path=args.missing_csv,
		)

		if missing:
			print(f"Missing {len(missing)} track(s):")
			for t in missing:
				print(f"- {t.display()}")
			return 2

		print("All playlist tracks appear to be present locally.")
		return 0

	return 1


if __name__ == "__main__":
	raise SystemExit(_main())
