"""Recording radiko program module"""

import base64
import contextlib
import datetime
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

URL_LOGIN = 'https://radiko.jp/v4/api/member/login'
URL_LOGOUT = 'https://radiko.jp/v4/api/member/logout'
URL_AUTH1 = 'https://radiko.jp/v2/api/auth1'
URL_AUTH2_BASE = 'https://radiko.jp/v2/api/auth2'
URL_STREAM_BASE = 'https://radiko.jp/v3/station/stream/pc_html5'
AUTHKEY_VAL = 'bcd151073c03b352e1ef2fd66c32209da9ca0afa'
TIMEOUT = 10
CHUNK_MAX_SEC = 300

class RadikoLoginAuth(contextlib.ContextDecorator):
    """Radiko login and authorization utility"""
    def __init__(self, mail, password):
        self.mail = mail
        self.password = password
        self.radiko_session = None
        self.is_areafree = False

        self.authtoken = None
        self.keyoffset = None
        self.keylength = None
        self.area_id = None

    def __repr__(self) -> str:
        return f"RadikoLoginUtil(mail={self.mail}, password={'*'*len(self.password)})"

    def login(self) -> None:
        """Login to radiko"""
        login_json = requests.post(
            URL_LOGIN,
            data = {
                'mail': self.mail,
                'pass': self.password
            },
            timeout=TIMEOUT
        ).json()

        self.radiko_session = login_json.get('radiko_session', '')
        self.is_areafree = login_json.get('areafree') == '1'

        if not self.radiko_session or not self.is_areafree:
            raise PermissionError('Login failed')

    def logout(self):
        """Logout from radiko"""
        requests.post(
            URL_LOGOUT,
            data = {
                'radiko_session': self.radiko_session,
            },
            timeout=TIMEOUT
        )
        self.radiko_session = None

    def auth1(self):
        """Get authtoken, keyoffset, keylength from radiko"""
        auth1_res = requests.get(
            URL_AUTH1,
            headers = {
                "X-Radiko-App": "pc_html5",
                "X-Radiko-App-Version": "0.0.1",
                "X-Radiko-Device": "pc",
                "X-Radiko-User": "dummy_user"
            },
            timeout=TIMEOUT
        ).headers

        self.authtoken = auth1_res['X-Radiko-Authtoken']
        self.keyoffset = auth1_res['X-Radiko-KeyOffset']
        self.keylength = auth1_res['X-Radiko-KeyLength']

        if not self.authtoken or not self.keyoffset or not self.keylength:
            self.logout()
            raise PermissionError('auth1 failed')

    def auth2(self):
        """Get partialkey and area_id from radiko"""
        if self.radiko_session is None:
            raise PermissionError('Not logged in')

        partialkey = base64.b64encode(
            AUTHKEY_VAL[int(self.keyoffset):int(self.keyoffset) + int(self.keylength)].encode()
        )

        url_auth2 = URL_AUTH2_BASE + '?radiko_session=' + self.radiko_session
        auth2_res = requests.get(
            url_auth2,
            headers = {
                "X-Radiko-Device": "pc",
                "X-Radiko-User": "dummy_user",
                "X-Radiko-AuthToken": self.authtoken,
                "X-Radiko-Partialkey": partialkey,
            },
            timeout=TIMEOUT
        )
        if auth2_res.status_code != 200:
            self.logout()
            raise PermissionError('auth2 failed')

        self.area_id = auth2_res.text.strip().split(',')[0]

    def __enter__(self):
        self.login()
        self.auth1()
        self.auth2()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.logout()

class RadikoRecorder:
    """Radiko recorder"""
    def __init__(self, mail = None, password = None) -> None:
        """Initialize RadikoRecorder
        
        Args:
            mail (str, optional): mail address. Defaults to None.
            password (str, optional): password. Defaults to None.
            
        Raises:
            Exception: if mail or password is not set
        """
        if mail is None:
            try:
                mail = os.environ['RADIKO_MAIL']
            except KeyError as e:
                raise ValueError('mail is not set to environment variable') from e
        if password is None:
            try:
                password = os.environ['RADIKO_PASSWORD']
            except KeyError as e:
                raise ValueError('password is not set to environment variable') from e
        self.radiko_util = RadikoLoginAuth(mail, password)

    def __repr__(self) -> str:
        return "RadikoRecorder()"

    def gen_psuedo_hash(self) -> str:
        """Generate psuedo hash

        Returns:
            str: psuedo hash
        """
        random_bytes = os.urandom(40)
        base64_str = base64.b64encode(random_bytes).decode('utf-8')
        return re.sub("[^0-9a-fA-F]", "", base64_str).lower()[:32]

    def _get_playlist_url(self, station_id: str, is_areafree: bool) -> str:
        """Get HLS playlist URL from station XML

        Args:
            station_id (str): station id
            is_areafree (bool): whether areafree is enabled

        Returns:
            str: playlist URL
        """
        res = requests.get(
            f'{URL_STREAM_BASE}/{station_id}.xml',
            timeout=TIMEOUT
        )
        root = ET.fromstring(res.content)
        areafree_val = '1' if is_areafree else '0'

        for url_elem in root.findall('.//url'):
            if url_elem.get('timefree') == '1' and url_elem.get('areafree') == areafree_val:
                playlist_url = url_elem.find('playlist_create_url')
                if playlist_url is not None and playlist_url.text:
                    return playlist_url.text.strip()

        raise ValueError(f'Playlist URL not found for station {station_id}')

    def _get_chunk_duration(self, chunk_file: str) -> int:
        """Get duration of audio file in seconds using ffprobe"""
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', chunk_file],
            capture_output=True, text=True
        )
        try:
            return int(float(result.stdout.strip()) + 0.5)
        except ValueError:
            return 0

    def record(
        self, station_id: str, fromtime: str, totime: str, fname: str
    ) -> subprocess.CompletedProcess:
        """Record radiko station from fromtime to totime to fname

        This function uses ffmpeg to record a radiko station
        for a specified duration and save it as an m4a file.

        Args:
            station_id (str): station id
            fromtime (str): start time in format YYYYMMDDHHMM
            totime (str): end time in format YYYYMMDDHHMM
            fname (str): output file name of the recording with .m4a extension

        Returns:
            subprocess.CompletedProcess: ffmpeg process

        """

        assert len(fromtime) == 12, 'fromtime must be in format YYYYMMDDHHMM'
        assert len(totime) == 12, 'totime must be in format YYYYMMDDHHMM'
        now = datetime.datetime.now()
        week_ago = now - datetime.timedelta(days=7)
        from_dt = datetime.datetime.strptime(fromtime, '%Y%m%d%H%M')
        to_dt = datetime.datetime.strptime(totime, '%Y%m%d%H%M')
        assert week_ago <= from_dt <= now, 'fromtime must be within the past week'
        assert week_ago <= to_dt <= now, 'totime must be within the past week'
        assert fname.endswith('.m4a'), 'fname must have .m4a extension'

        lsid = self.gen_psuedo_hash()
        fromtime_sec = fromtime + '00'
        totime_sec = totime + '00'

        with self.radiko_util as radiko_util:
            playlist_url = self._get_playlist_url(station_id, radiko_util.is_areafree)
            ffmpeg_header = f'X-Radiko-Authtoken: {radiko_util.authtoken}\r\nX-Radiko-AreaId: {radiko_util.area_id}'

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                chunk_files = []
                chunk_no = 0
                seek_timestamp = from_dt
                left_sec = int((to_dt - from_dt).total_seconds())

                while left_sec > 0:
                    chunk_file = tmp_path / f'chunk{chunk_no}.m4a'

                    # Chunk max 300 seconds, round up to nearest 5 seconds
                    l = CHUNK_MAX_SEC
                    if left_sec < CHUNK_MAX_SEC:
                        l = left_sec if left_sec % 5 == 0 else ((left_sec // 5) + 1) * 5

                    seek = seek_timestamp.strftime('%Y%m%d%H%M%S')
                    end_at = (seek_timestamp + datetime.timedelta(seconds=l)).strftime('%Y%m%d%H%M%S')

                    url = (
                        f'{playlist_url}?station_id={station_id}'
                        f'&start_at={fromtime_sec}&ft={fromtime_sec}'
                        f'&seek={seek}&end_at={end_at}&to={end_at}'
                        f'&l={l}&lsid={lsid}&type=c'
                    )

                    result = subprocess.run([
                        'ffmpeg',
                        '-nostdin',
                        '-loglevel', 'quiet',
                        '-fflags', '+discardcorrupt',
                        '-headers', ffmpeg_header,
                        '-http_seekable', '0',
                        '-seekable', '0',
                        '-i', url,
                        '-acodec', 'copy',
                        '-vn',
                        '-bsf:a', 'aac_adtstoasc',
                        '-y',
                        str(chunk_file)
                    ], capture_output=True)

                    if result.returncode != 0:
                        return result

                    chunk_files.append(chunk_file)
                    chunk_sec = self._get_chunk_duration(str(chunk_file)) or l
                    left_sec -= chunk_sec
                    seek_timestamp += datetime.timedelta(seconds=chunk_sec)
                    chunk_no += 1

                # Concat chunks
                filelist_path = tmp_path / 'filelist.txt'
                with open(filelist_path, 'w') as f:
                    for chunk_file in chunk_files:
                        f.write(f"file '{chunk_file}'\n")

                res = subprocess.run([
                    'ffmpeg',
                    '-loglevel', 'error',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(filelist_path),
                    '-c', 'copy',
                    '-y',
                    fname
                ], capture_output=True)

        return res
