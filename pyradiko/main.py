"""Recording radiko program module"""

import base64
import contextlib
import datetime
import os
import re
import subprocess

import requests

URL_LOGIN = 'https://radiko.jp/v4/api/member/login'
URL_LOGOUT = 'https://radiko.jp/v4/api/member/logout'
URL_AUTH1 = 'https://radiko.jp/v2/api/auth1'
URL_AUTH2_BASE = 'https://radiko.jp/v2/api/auth2'
AUTHKEY_VAL = 'bcd151073c03b352e1ef2fd66c32209da9ca0afa'

class RadikoLoginAuth:
    """Radiko login and authorization utility"""
    def __init__(self, mail, password):
        self.mail = mail
        self.password = password
        self.radiko_session = None

    def __repr__(self) -> str:
        return f"RadikoLoginUtil(mail={self.mail}, password={'*'*len(self.password)})"

    def login(self) -> None:
        self.login_json = requests.post(
            URL_LOGIN,
            data = {
                'mail': self.mail,
                'pass': self.password
            }
        ).json()

        self.radiko_session = self.login_json['radiko_session']
        is_areafree = self.login_json['areafree'] == '1'

        if not self.radiko_session or not is_areafree:
            raise Exception('Login failed')

    def logout(self):
        requests.post(
            URL_LOGOUT,
            data = {
                'radiko_session': self.radiko_session,
            }
        )
        self.radiko_session = None

    def auth1(self):
        auth1_res = requests.get(
            URL_AUTH1,
            headers = {
                "X-Radiko-App": "pc_html5",
                "X-Radiko-App-Version": "0.0.1",
                "X-Radiko-Device": "pc",
                "X-Radiko-User": "dummy_user"
            }
        ).headers

        self.authtoken = auth1_res['X-Radiko-Authtoken']
        self.keyoffset = auth1_res['X-Radiko-KeyOffset']
        self.keylength = auth1_res['X-Radiko-KeyLength']

        if not self.authtoken or not self.keyoffset or not self.keylength:
            self.logout()
            raise Exception('auth1 failed')

    def auth2(self):
        if self.radiko_session is None:
            raise Exception('Not logged in')

        partialkey = base64.b64encode(
            # vscode autocomplete
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
            }
        )
        if auth2_res.status_code != 200:
            self.logout()
            raise Exception('auth2 failed')

    @contextlib.contextmanager
    def auto_login_logout(self):
        self.login()
        self.auth1()
        self.auth2()
        yield self
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
            except KeyError:
                raise Exception('mail is not set to environment variable')
        if password is None:
            try:
                password = os.environ['RADIKO_PASSWORD']
            except KeyError:
                raise Exception('password is not set to environment variable')
        self.radiko_util = RadikoLoginAuth(mail, password)

    def __repr__(self) -> str:
        return f"RadikoRecorder()"

    def gen_psuedo_hash(self) -> str:
        """Generate psuedo hash
        
        Returns:
            str: psuedo hash
        """
        # Read 100 bytes from /dev/random
        random_bytes = os.urandom(100)
        # Encode the bytes to base64
        # Convert the bytes to a string
        base64_str = base64.b64encode(random_bytes).decode('utf-8')
        # Remove all non-hexadecimal characters from the string
        # Convert the string to lowercase
        # Cut the string to 32 characters
        return re.sub("[^0-9a-fA-F]", "", base64_str).lower()[:32]

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
        # fromtimeとtotimeが過去一週間以内であるかをチェック
        now = datetime.datetime.now()
        week_ago = now - datetime.timedelta(days=7)
        from_dt = datetime.datetime.strptime(fromtime, '%Y%m%d%H%M')
        to_dt = datetime.datetime.strptime(totime, '%Y%m%d%H%M')
        assert week_ago <= from_dt <= now, 'fromtime must be within the past week'
        assert week_ago <= to_dt <= now, 'totime must be within the past week'

        # fnameの拡張子をチェック
        assert fname.endswith('.m4a'), 'fname must have .m4a extension'

        lsid = self.gen_psuedo_hash()
        url_download = (
            'https://radiko.jp/v2/api/ts/playlist.m3u8'
            f'?station_id={station_id}&start_at={fromtime}00&ft={fromtime}00'
            f'&end_at={totime}00&to={totime}00&seek={fromtime}00&l=15&lsid={lsid}&type=c'
        )

        with self.radiko_util.auto_login_logout() as radiko_util:
            command = [
                "ffmpeg",
                "-loglevel", "debug",
                "-fflags", "+discardcorrupt",
                "-headers", f'"X-Radiko-Authtoken: {radiko_util.authtoken}"',
                "-i", f'"{url_download}"',
                "-acodec", "copy",
                "-vn",
                "-bsf:a", "aac_adtstoasc",
                "-y",
                fname
            ]
            command = ' '.join(command)
            res = subprocess.run(command, capture_output=True, shell=True, check=False)

        return res
