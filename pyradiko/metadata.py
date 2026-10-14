"""Metadata embedding utility for recorded audio files using mutagen."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from pyradiko.program import Program

logger = logging.getLogger(__name__)


def _get_mutagen_mp4():
    """Import MP4 and MP4Cover from mutagen with friendly error message."""
    try:
        from mutagen.mp4 import MP4, MP4Cover

        return MP4, MP4Cover
    except ImportError as e:
        raise ImportError(
            "Metadata embedding requires the 'mutagen' library.\n"
            "Please install it using:\n"
            "  uv add mutagen\n"
            "or:\n"
            "  pip install 'pyradiko[metadata]'"
        ) from e


def _detect_image_format(data: bytes, mp4_cover_cls) -> int:
    """Detect image format for MP4Cover."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return mp4_cover_cls.FORMAT_PNG
    return mp4_cover_cls.FORMAT_JPEG


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

    Requires the optional dependency 'mutagen'.

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

    mp4_cls, mp4_cover_cls = _get_mutagen_mp4()
    audio = mp4_cls(path)

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
        img_format = _detect_image_format(image_bytes, mp4_cover_cls)
        audio["covr"] = [mp4_cover_cls(image_bytes, imageformat=img_format)]

    audio.save()
    logger.debug(f"Metadata embedded successfully into {path}")
