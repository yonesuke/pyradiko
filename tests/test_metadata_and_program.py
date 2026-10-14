"""Unit tests for pyradiko program metadata, timetable, and validation."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pyradiko.main import RadikoRecorder
from pyradiko.metadata import embed_metadata
from pyradiko.program import (
    Program,
    calculate_program_date,
    clean_html,
    fetch_programs,
    get_program_by_time,
)

SAMPLE_STATION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<radiko>
    <stations>
        <station id="LFR">
            <name>ニッポン放送</name>
            <progs>
                <date>20261010</date>
                <prog ft="20261011010000" to="20261011030000">
                    <title>オードリーのオールナイトニッポン</title>
                    <pfm>オードリー(若林正恭/春日俊彰)</pfm>
                    <desc>オードリーの2人が&lt;br&gt;じっくり話します。</desc>
                    <info>メール: kw@allnightnippon.com</info>
                    <img>https://example.com/audrey.jpg</img>
                    <url>https://www.allnightnippon.com/audrey/</url>
                </prog>
            </progs>
        </station>
    </stations>
</radiko>
"""


class TestProgramMetadata(unittest.TestCase):
    def test_calculate_program_date(self):
        # 01:00 on Oct 11 -> program date is Oct 10 (shifted back 5 hours)
        self.assertEqual(calculate_program_date("202610110100"), "20261010")
        # 04:59 on Oct 11 -> program date is Oct 10
        self.assertEqual(calculate_program_date("202610110459"), "20261010")
        # 05:00 on Oct 11 -> program date is Oct 11
        self.assertEqual(calculate_program_date("202610110500"), "20261011")
        # 12:00 on Oct 11 -> program date is Oct 11
        self.assertEqual(calculate_program_date("202610111200"), "20261011")

    def test_clean_html(self):
        raw = "Line1<br>Line2&lt;br/&gt;&lt;a href=&quot;test&quot;&gt;Click&lt;/a&gt;"
        cleaned = clean_html(raw)
        self.assertIn("Line1\nLine2", cleaned)
        self.assertIn("Click", cleaned)
        self.assertNotIn("<a", cleaned)
        self.assertNotIn("&lt;", cleaned)

    @patch("requests.get")
    def test_fetch_programs_and_get_by_time(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = SAMPLE_STATION_XML.encode("utf-8")
        mock_get.return_value = mock_resp

        programs = fetch_programs("LFR", "20261010")
        self.assertEqual(len(programs), 1)
        prog = programs[0]
        self.assertEqual(prog.title, "オードリーのオールナイトニッポン")
        self.assertEqual(prog.pfm, "オードリー(若林正恭/春日俊彰)")
        self.assertEqual(prog.start_time, "202610110100")
        self.assertEqual(prog.end_time, "202610110300")
        self.assertEqual(prog.broadcast_date, "2026-10-11")
        self.assertIn("オードリーの2人が\nじっくり話します。", prog.desc)

        # get_program_by_time
        found = get_program_by_time("LFR", "202610110130")
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "オードリーのオールナイトニッポン")


class TestEmbedMetadata(unittest.TestCase):
    def test_embed_metadata_on_m4a(self):
        # Create a minimal dummy MP4/M4A file using ffmpeg if available
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            dummy_m4a = f.name

        try:
            # Generate a silent 1-second audio file with ffmpeg
            cmd = (
                f"ffmpeg -loglevel quiet -f lavfi -i anullsrc=r=44100:cl=mono "
                f"-t 1 -c:a aac -y {dummy_m4a}"
            )
            res = os.system(cmd)
            if res != 0:
                self.skipTest("ffmpeg not available to create dummy m4a")

            prog = Program(
                station_id="LFR",
                title="オードリーのオールナイトニッポン",
                ft="20261011010000",
                to="20261011030000",
                pfm="オードリー",
                desc="テスト概要",
                img="",
            )

            # 1x1 JPEG dummy image
            dummy_jpeg = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
                b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
                b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
                b"\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
            )

            embed_metadata(
                dummy_m4a,
                program=prog,
                artwork_data=dummy_jpeg,
            )

            try:
                from mutagen.mp4 import MP4
            except ImportError:
                self.skipTest("mutagen is not installed")

            # Inspect tags with mutagen
            audio = MP4(dummy_m4a)
            self.assertEqual(audio["\xa9nam"], ["オードリーのオールナイトニッポン (2026-10-11)"])
            self.assertEqual(audio["\xa9ART"], ["オードリー"])
            self.assertEqual(audio["\xa9alb"], ["オードリーのオールナイトニッポン"])
            self.assertEqual(audio["\xa9day"], ["2026-10-11"])
            self.assertEqual(audio["\xa9gen"], ["Radio"])
            self.assertEqual(audio["desc"], ["テスト概要"])
            self.assertEqual(len(audio["covr"]), 1)
        finally:
            if os.path.exists(dummy_m4a):
                os.unlink(dummy_m4a)

    def test_missing_mutagen_raises_friendly_error(self):
        """Verify that missing mutagen raises an informative ImportError."""
        from pyradiko.metadata import _get_mutagen_mp4

        with patch.dict("sys.modules", {"mutagen.mp4": None}):
            with self.assertRaises(ImportError) as ctx:
                _get_mutagen_mp4()
            msg = str(ctx.exception)
            self.assertIn("uv add mutagen", msg)
            self.assertIn("pyradiko[metadata]", msg)


class TestValidation(unittest.TestCase):
    def setUp(self):
        os.environ["RADIKO_MAIL"] = "dummy@example.com"
        os.environ["RADIKO_PASSWORD"] = "dummypass"

    def test_record_validation(self):
        recorder = RadikoRecorder()

        # Non-12-digit fromtime
        with self.assertRaises(ValueError):
            recorder.record("LFR", "20261011", "202610110300", "out.m4a")

        # fromtime >= totime
        with self.assertRaises(ValueError):
            recorder.record("LFR", "202610110300", "202610110100", "out.m4a")

        # non-.m4a extension
        with self.assertRaises(ValueError):
            recorder.record("LFR", "202610110100", "202610110300", "out.mp3")

        # Future time
        future = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%Y%m%d%H%M")
        with self.assertRaises(ValueError):
            recorder.record("LFR", future, future, "out.m4a")


if __name__ == "__main__":
    unittest.main()
