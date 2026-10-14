"""Metadata embedding utility for recorded audio files using mutagen."""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from mutagen.mp4 import MP4, MP4Cover

from pyradiko.program import Program

logger = logging.getLogger(__name__)


def _detect_image_format(data: bytes) -> int:
    """Detect image format for MP4Cover."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return MP4Cover.FORMAT_PNG
    return MP4Cover.FORMAT_JPEG


def fetch_image_data(url: str, session: requests.Session | None = None) -> bytes | None:
    """Fetch image bytes from a URL."""
    if not url:
        return None
    try:
        client = session or requests
        res = client.get(url, timeout=10)
        if res.status_code == 200:
            return res.content
    except Exception as e:
        logger.warning(f"Failed to fetch artwork from {url}: {e}")
    return None


def embed_metadata(
    filepath: str | Path,
    program: Program | None = None,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = "Radio",
    date: str | None = None,
    desc: str | None = None,
    artwork_url: str | None = None,
    artwork_data: bytes | None = None,
    session: requests.Session | None = None,
) -> None:
    """Embed metadata tags and cover artwork into an M4A audio file.

    Args:
        filepath: Path to the .m4a file.
        program: Optional Program instance to extract metadata from.
        title: Optional custom track title.
        artist: Optional custom artist/performer.
        album: Optional custom album name.
        genre: Genre name (default: 'Radio').
        date: Optional broadcast date (YYYY-MM-DD).
        desc: Optional description text.
        artwork_url: Optional URL to fetch cover image from.
        artwork_data: Optional raw bytes of cover image.
        session: Optional requests.Session for downloading artwork.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    audio = MP4(path)

    # Resolve metadata fields from explicit arguments or Program object
    final_title = title
    if final_title is None and program:
        if program.broadcast_date:
            final_title = f"{program.title} ({program.broadcast_date})"
        else:
            final_title = program.title

    final_artist = artist
    if final_artist is None and program:
        final_artist = program.pfm

    final_album = album
    if final_album is None and program:
        final_album = program.title

    final_date = date
    if final_date is None and program:
        final_date = program.broadcast_date

    final_desc = desc
    if final_desc is None and program:
        final_desc = program.desc

    # Apply tags
    if final_title:
        audio["\xa9nam"] = [final_title]
    if final_artist:
        audio["\xa9ART"] = [final_artist]
    if final_album:
        audio["\xa9alb"] = [final_album]
    if genre:
        audio["\xa9gen"] = [genre]
    if final_date:
        audio["\xa9day"] = [final_date]
    if final_desc:
        audio["desc"] = [final_desc]
        audio["\xa9des"] = [final_desc]

    # Resolve and embed cover image
    image_bytes = artwork_data
    if image_bytes is None:
        target_url = artwork_url or (program.img if program else None)
        if target_url:
            image_bytes = fetch_image_data(target_url, session=session)

    if image_bytes:
        img_format = _detect_image_format(image_bytes)
        audio["covr"] = [MP4Cover(image_bytes, imageformat=img_format)]

    audio.save()
    logger.debug(f"Metadata embedded successfully into {path}")
