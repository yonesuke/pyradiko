"""Radiko program timetable and metadata fetcher."""

from __future__ import annotations

import datetime
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx2

URL_STATION_DATE_BASE = "https://radiko.jp/v3/program/station/date"
TIMEOUT = 10


@dataclass
class Program:
    """Radiko program metadata."""

    station_id: str
    title: str
    ft: str  # Format: YYYYMMDDHHMMSS
    to: str  # Format: YYYYMMDDHHMMSS
    pfm: str = ""  # Performer / Personality
    desc: str = ""  # Description
    info: str = ""  # Additional information
    img: str = ""  # Artwork / thumbnail URL
    url: str = ""  # Official program URL

    @property
    def start_time(self) -> str:
        """Return 12-digit start time (YYYYMMDDHHMM)."""
        return self.ft[:12]

    @property
    def end_time(self) -> str:
        """Return 12-digit end time (YYYYMMDDHHMM)."""
        return self.to[:12]

    @property
    def broadcast_date(self) -> str:
        """Return broadcast date in YYYY-MM-DD format."""
        if len(self.ft) >= 8:
            return f"{self.ft[:4]}-{self.ft[4:6]}-{self.ft[6:8]}"
        return ""


def clean_html(raw_html: str) -> str:
    """Strip HTML tags and convert entities to plain text."""
    if not raw_html:
        return ""
    # Unescape HTML entities first (e.g. &lt;br&gt;)
    text = html.unescape(raw_html)
    # Replace <br> or <br/> with newline
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def calculate_program_date(target_time: str) -> str:
    """Calculate the Radiko timetable date for a given datetime string.

    Radiko broadcasting day runs from 05:00 to 28:59 (next day 04:59).
    Subtracting 5 hours from target_time gives the timetable date.

    Args:
        target_time: Datetime string in YYYYMMDDHHMM or YYYYMMDDHHMMSS format.

    Returns:
        Timetable date string in YYYYMMDD format.
    """
    clean_time = target_time[:12]
    dt = datetime.datetime.strptime(clean_time, "%Y%m%d%H%M")
    # Shift backward by 5 hours
    prog_dt = dt - datetime.timedelta(hours=5)
    return prog_dt.strftime("%Y%m%d")


def fetch_programs(
    station_id: str,
    date_str: str,
    client: httpx2.Client | None = None,
    session: httpx2.Client | None = None,
) -> list[Program]:
    """Fetch all programs for a station on a specific timetable date.

    Args:
        station_id: Station ID (e.g. 'LFR', 'TBS')
        date_str: Date string in YYYYMMDD format
        client: Optional httpx2.Client instance
        session: Deprecated alias for client

    Returns:
        List of Program objects
    """
    url = f"{URL_STATION_DATE_BASE}/{date_str}/{station_id}.xml"
    http_client = client or session or httpx2

    res = http_client.get(url, timeout=TIMEOUT)
    if res.status_code != 200:
        return []

    try:
        root = ET.fromstring(res.content)
    except ET.ParseError:
        return []

    programs: list[Program] = []
    station_elem = root.find(f".//station[@id='{station_id}']")
    if station_elem is None:
        return []

    for prog_elem in station_elem.findall(".//prog"):
        ft = prog_elem.get("ft", "")
        to = prog_elem.get("to", "")

        title_elem = prog_elem.find("title")
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

        pfm_elem = prog_elem.find("pfm")
        pfm = pfm_elem.text.strip() if pfm_elem is not None and pfm_elem.text else ""

        desc_elem = prog_elem.find("desc")
        desc = clean_html(desc_elem.text) if desc_elem is not None and desc_elem.text else ""

        info_elem = prog_elem.find("info")
        info = clean_html(info_elem.text) if info_elem is not None and info_elem.text else ""

        img_elem = prog_elem.find("img")
        img = img_elem.text.strip() if img_elem is not None and img_elem.text else ""

        url_elem = prog_elem.find("url")
        prog_url = url_elem.text.strip() if url_elem is not None and url_elem.text else ""

        programs.append(
            Program(
                station_id=station_id,
                title=title,
                ft=ft,
                to=to,
                pfm=pfm,
                desc=desc,
                info=info,
                img=img,
                url=prog_url,
            )
        )

    return programs


def get_program_by_time(
    station_id: str,
    target_time: str,
    client: httpx2.Client | None = None,
    session: httpx2.Client | None = None,
) -> Program | None:
    """Find the program corresponding to a target time.

    Args:
        station_id: Station ID (e.g. 'LFR')
        target_time: Start time in YYYYMMDDHHMM or YYYYMMDDHHMMSS format
        client: Optional httpx2.Client instance
        session: Deprecated alias for client

    Returns:
        Program object if found, otherwise None
    """
    target_clean = (target_time + "00") if len(target_time) == 12 else target_time[:14]
    date_str = calculate_program_date(target_clean)

    programs = fetch_programs(station_id, date_str, client=client, session=session)
    for prog in programs:
        # Check if target_clean falls within [prog.ft, prog.to) or equals prog.ft
        if prog.ft <= target_clean < prog.to or prog.ft.startswith(target_clean[:12]):
            return prog

    return None
