"""Recording radiko program module."""

from __future__ import annotations

import base64
import contextlib
import datetime
import logging
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from pyradiko.exceptions import (
    RadikoAuthError,
    RadikoPlaylistError,
)
from pyradiko.metadata import embed_metadata
from pyradiko.program import get_program_by_time

logger = logging.getLogger(__name__)

URL_LOGIN = "https://radiko.jp/v4/api/member/login"
URL_LOGOUT = "https://radiko.jp/v4/api/member/logout"
URL_AUTH1 = "https://radiko.jp/v2/api/auth1"
URL_AUTH2_BASE = "https://radiko.jp/v2/api/auth2"
URL_STREAM_BASE = "https://radiko.jp/v3/station/stream/pc_html5"
AUTHKEY_VAL = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
TIMEOUT = 10
CHUNK_MAX_SEC = 300


class RadikoLoginAuth(contextlib.ContextDecorator):
    """Radiko login and authorization utility."""

    def __init__(self, mail: str, password: str, session: requests.Session | None = None) -> None:
        self.mail = mail
        self.password = password
        self.session = session or requests.Session()
        self._owns_session = session is None

        self.radiko_session: str | None = None
        self.is_areafree: bool = False
        self.authtoken: str | None = None
        self.keyoffset: str | None = None
        self.keylength: str | None = None
        self.area_id: str | None = None

    def __repr__(self) -> str:
        masked_pwd = "*" * len(self.password) if self.password else ""
        return f"RadikoLoginAuth(mail={self.mail}, password={masked_pwd})"

    def login(self) -> None:
        """Login to radiko premium."""
        try:
            res = self.session.post(
                URL_LOGIN,
                data={"mail": self.mail, "pass": self.password},
                timeout=TIMEOUT,
            )
            res.raise_for_status()
            login_json = res.json()
        except Exception as e:
            raise RadikoAuthError(f"Login failed: network or response error ({e})") from e

        self.radiko_session = login_json.get("radiko_session", "")
        self.is_areafree = login_json.get("areafree") == "1"

        if not self.radiko_session:
            raise RadikoAuthError("Login failed: invalid credentials or session not returned")
        if not self.is_areafree:
            raise RadikoAuthError("Login failed: account is not area-free premium")

    def logout(self) -> None:
        """Logout from radiko."""
        if self.radiko_session:
            try:
                self.session.post(
                    URL_LOGOUT,
                    data={"radiko_session": self.radiko_session},
                    timeout=TIMEOUT,
                )
            except Exception as e:
                logger.debug(f"Logout failed: {e}")
            self.radiko_session = None

        if self._owns_session:
            self.session.close()

    def auth1(self) -> None:
        """Get authtoken, keyoffset, keylength from radiko."""
        try:
            res = self.session.get(
                URL_AUTH1,
                headers={
                    "X-Radiko-App": "pc_html5",
                    "X-Radiko-App-Version": "0.0.1",
                    "X-Radiko-Device": "pc",
                    "X-Radiko-User": "dummy_user",
                },
                timeout=TIMEOUT,
            )
            res.raise_for_status()
            headers = res.headers
        except Exception as e:
            self.logout()
            raise RadikoAuthError(f"auth1 request failed: {e}") from e

        self.authtoken = headers.get("X-Radiko-Authtoken")
        self.keyoffset = headers.get("X-Radiko-KeyOffset")
        self.keylength = headers.get("X-Radiko-KeyLength")

        if not self.authtoken or not self.keyoffset or not self.keylength:
            self.logout()
            raise RadikoAuthError("auth1 failed: missing required response headers")

    def auth2(self) -> None:
        """Get partialkey and area_id from radiko."""
        if self.radiko_session is None:
            raise RadikoAuthError("Not logged in: radiko_session is missing")
        if not self.keyoffset or not self.keylength or not self.authtoken:
            raise RadikoAuthError("auth1 must be executed before auth2")

        try:
            offset = int(self.keyoffset)
            length = int(self.keylength)
            sub_key = AUTHKEY_VAL[offset : offset + length]
            partialkey = base64.b64encode(sub_key.encode()).decode()
        except Exception as e:
            self.logout()
            raise RadikoAuthError(f"Failed to generate partial key: {e}") from e

        url_auth2 = f"{URL_AUTH2_BASE}?radiko_session={self.radiko_session}"
        try:
            auth2_res = self.session.get(
                url_auth2,
                headers={
                    "X-Radiko-Device": "pc",
                    "X-Radiko-User": "dummy_user",
                    "X-Radiko-AuthToken": self.authtoken,
                    "X-Radiko-Partialkey": partialkey,
                },
                timeout=TIMEOUT,
            )
            if auth2_res.status_code != 200:
                self.logout()
                raise RadikoAuthError(f"auth2 failed with status code {auth2_res.status_code}")
        except Exception as e:
            self.logout()
            raise RadikoAuthError(f"auth2 request failed: {e}") from e

        self.area_id = auth2_res.text.strip().split(",")[0]

    def __enter__(self) -> RadikoLoginAuth:
        self.login()
        self.auth1()
        self.auth2()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.logout()


class RadikoRecorder:
    """Radiko recorder utility."""

    def __init__(self, mail: str | None = None, password: str | None = None) -> None:
        """Initialize RadikoRecorder.

        Args:
            mail: Radiko premium mail address. Defaults to RADIKO_MAIL env var.
            password: Radiko premium password. Defaults to RADIKO_PASSWORD env var.
        """
        if mail is None:
            mail = os.environ.get("RADIKO_MAIL")
            if not mail:
                raise ValueError("mail is not set (RADIKO_MAIL environment variable missing)")
        if password is None:
            password = os.environ.get("RADIKO_PASSWORD")
            if not password:
                raise ValueError(
                    "password is not set (RADIKO_PASSWORD environment variable missing)"
                )

        self.radiko_util = RadikoLoginAuth(mail, password)

    def __repr__(self) -> str:
        return "RadikoRecorder()"

    def gen_psuedo_hash(self) -> str:
        """Generate psuedo hash for session."""
        random_bytes = os.urandom(40)
        base64_str = base64.b64encode(random_bytes).decode("utf-8")
        return re.sub("[^0-9a-fA-F]", "", base64_str).lower()[:32]

    def _get_playlist_url(self, station_id: str, is_areafree: bool) -> str:
        """Get HLS playlist URL from station XML."""
        res = requests.get(f"{URL_STREAM_BASE}/{station_id}.xml", timeout=TIMEOUT)
        if res.status_code != 200:
            raise RadikoPlaylistError(
                f"Failed to fetch station XML for {station_id} (HTTP {res.status_code})"
            )

        root = ET.fromstring(res.content)
        areafree_val = "1" if is_areafree else "0"

        for url_elem in root.findall(".//url"):
            if url_elem.get("timefree") == "1" and url_elem.get("areafree") == areafree_val:
                playlist_url = url_elem.find("playlist_create_url")
                if playlist_url is not None and playlist_url.text:
                    return playlist_url.text.strip()

        raise RadikoPlaylistError(f"Playlist URL not found for station {station_id}")

    def _get_chunk_duration(self, chunk_file: str) -> int:
        """Get duration of audio file in seconds using ffprobe."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                chunk_file,
            ],
            capture_output=True,
            text=True,
        )
        try:
            return int(float(result.stdout.strip()) + 0.5)
        except ValueError:
            return 0

    def record(
        self,
        station_id: str,
        fromtime: str,
        totime: str,
        fname: str,
        auto_metadata: bool = True,
        metadata: dict | None = None,
    ) -> subprocess.CompletedProcess:
        """Record radiko station from fromtime to totime to fname.

        Args:
            station_id: Station ID (e.g. 'LFR', 'TBS')
            fromtime: Start time in format YYYYMMDDHHMM (12 digits)
            totime: End time in format YYYYMMDDHHMM (12 digits)
            fname: Output file name with .m4a extension
            auto_metadata: Whether to fetch timetable metadata and embed it into .m4a
            metadata: Optional dictionary of metadata overrides ('title', 'artist', etc.)

        Returns:
            subprocess.CompletedProcess: ffmpeg process result

        Raises:
            ValueError: If time arguments or format are invalid.
            RadikoAuthError: If authentication fails.
            RadikoPlaylistError: If stream playlist cannot be resolved.
        """
        if len(fromtime) != 12 or not fromtime.isdigit():
            raise ValueError(f"fromtime must be 12-digit format YYYYMMDDHHMM (got: '{fromtime}')")
        if len(totime) != 12 or not totime.isdigit():
            raise ValueError(f"totime must be 12-digit format YYYYMMDDHHMM (got: '{totime}')")
        if not fname.endswith(".m4a"):
            raise ValueError(f"fname must have .m4a extension (got: '{fname}')")

        try:
            from_dt = datetime.datetime.strptime(fromtime, "%Y%m%d%H%M")
            to_dt = datetime.datetime.strptime(totime, "%Y%m%d%H%M")
        except ValueError as e:
            raise ValueError(f"Invalid datetime format: {e}") from e

        if from_dt >= to_dt:
            raise ValueError(f"fromtime ({fromtime}) must be earlier than totime ({totime})")

        now = datetime.datetime.now()
        # Allow slight clock skew up to 10 minutes in the future
        if from_dt > now + datetime.timedelta(minutes=10):
            raise ValueError(f"fromtime ({fromtime}) cannot be in the future")

        # Radiko standard timefree is 7 days, Timefree 30 extends up to 30 days
        past_limit = now - datetime.timedelta(days=31)
        if from_dt < past_limit:
            raise ValueError(
                f"fromtime ({fromtime}) is older than 30 days limit for timefree listening"
            )

        lsid = self.gen_psuedo_hash()
        fromtime_sec = fromtime + "00"

        with self.radiko_util as radiko_util:
            playlist_url = self._get_playlist_url(station_id, radiko_util.is_areafree)
            ffmpeg_header = (
                f"X-Radiko-Authtoken: {radiko_util.authtoken}\r\n"
                f"X-Radiko-AreaId: {radiko_util.area_id}"
            )

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                chunk_files = []
                chunk_no = 0
                seek_timestamp = from_dt
                left_sec = int((to_dt - from_dt).total_seconds())

                while left_sec > 0:
                    chunk_file = tmp_path / f"chunk{chunk_no}.m4a"

                    # Chunk max 300 seconds, round up to nearest 5 seconds
                    chunk_len = CHUNK_MAX_SEC
                    if left_sec < CHUNK_MAX_SEC:
                        chunk_len = left_sec if left_sec % 5 == 0 else ((left_sec // 5) + 1) * 5

                    seek = seek_timestamp.strftime("%Y%m%d%H%M%S")
                    end_at = (seek_timestamp + datetime.timedelta(seconds=chunk_len)).strftime(
                        "%Y%m%d%H%M%S"
                    )

                    url = (
                        f"{playlist_url}?station_id={station_id}"
                        f"&start_at={fromtime_sec}&ft={fromtime_sec}"
                        f"&seek={seek}&end_at={end_at}&to={end_at}"
                        f"&l={chunk_len}&lsid={lsid}&type=c"
                    )

                    result = subprocess.run(
                        [
                            "ffmpeg",
                            "-nostdin",
                            "-loglevel",
                            "quiet",
                            "-fflags",
                            "+discardcorrupt",
                            "-headers",
                            ffmpeg_header,
                            "-http_seekable",
                            "0",
                            "-seekable",
                            "0",
                            "-i",
                            url,
                            "-acodec",
                            "copy",
                            "-vn",
                            "-bsf:a",
                            "aac_adtstoasc",
                            "-y",
                            str(chunk_file),
                        ],
                        capture_output=True,
                    )

                    if result.returncode != 0:
                        logger.error(
                            f"ffmpeg failed for chunk {chunk_no} (code {result.returncode}): "
                            f"{result.stderr.decode(errors='replace')}"
                        )
                        return result

                    chunk_files.append(chunk_file)
                    chunk_sec = self._get_chunk_duration(str(chunk_file)) or chunk_len
                    left_sec -= chunk_sec
                    seek_timestamp += datetime.timedelta(seconds=chunk_sec)
                    chunk_no += 1

                # Concat chunks
                filelist_path = tmp_path / "filelist.txt"
                with open(filelist_path, "w", encoding="utf-8") as f:
                    for chunk_file in chunk_files:
                        f.write(f"file '{chunk_file}'\n")

                res = subprocess.run(
                    [
                        "ffmpeg",
                        "-loglevel",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(filelist_path),
                        "-c",
                        "copy",
                        "-y",
                        fname,
                    ],
                    capture_output=True,
                )

        # Embed metadata if recording succeeded
        if res.returncode == 0 and Path(fname).exists() and (auto_metadata or metadata):
            try:
                prog = get_program_by_time(station_id, fromtime) if auto_metadata else None
                meta_args = metadata or {}
                embed_metadata(
                    fname,
                    program=prog,
                    title=meta_args.get("title"),
                    artist=meta_args.get("artist"),
                    album=meta_args.get("album"),
                    genre=meta_args.get("genre", "Radio"),
                    desc=meta_args.get("desc"),
                    date=meta_args.get("date"),
                    artwork_url=meta_args.get("artwork_url"),
                )
            except Exception as e:
                logger.warning(f"Failed to embed metadata: {e}")

        return res
