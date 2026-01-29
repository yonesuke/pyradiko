import unittest
import tempfile, os
import datetime
import subprocess

from pyradiko import RadikoRecorder


def get_audio_duration(filepath: str) -> float:
    """ffprobeで音源の再生時間(秒)を取得"""
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


class TestRadikoRecorder(unittest.TestCase):
    def test_record_short(self):
        """短時間(3分)の録音テスト"""
        recorder = RadikoRecorder()
        station_id = 'LFR'
        now = datetime.datetime.now()
        totime = (now - datetime.timedelta(minutes=2)).strftime('%Y%m%d%H%M')
        fromtime = (now - datetime.timedelta(minutes=5)).strftime('%Y%m%d%H%M')
        expected_duration = 3 * 60  # 3分
        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as f:
            fname = f.name
        try:
            res = recorder.record(station_id, fromtime, totime, fname)
            self.assertEqual(res.returncode, 0)
            self.assertTrue(os.path.exists(fname))
            self.assertGreater(os.path.getsize(fname), 0)
            # 再生時間のチェック（±10秒の誤差を許容）
            duration = get_audio_duration(fname)
            self.assertAlmostEqual(duration, expected_duration, delta=10,
                msg=f"再生時間が期待値と異なる: {duration:.1f}秒 (期待: {expected_duration}秒)")
        finally:
            if os.path.exists(fname):
                os.unlink(fname)


class TestAudrey(unittest.TestCase):
    """オードリーのオールナイトニッポン録音テスト

    放送時間: 土曜日 25:00-27:00 (日曜日 1:00-3:00)
    放送局: ニッポン放送 (LFR)
    """

    def _get_last_saturday_broadcast_time(self):
        """直近の土曜深夜(日曜早朝)の放送時間を取得"""
        now = datetime.datetime.now()
        # 日曜日 = 6, 土曜日 = 5
        # 直近の日曜日を探す（放送は日曜日の1:00-3:00）
        days_since_sunday = (now.weekday() + 1) % 7
        if days_since_sunday == 0 and now.hour < 3:
            # 今日が日曜で3時前なら今日の放送
            last_sunday = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif days_since_sunday == 0:
            # 今日が日曜で3時以降なら今日の放送
            last_sunday = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # 直近の日曜日
            last_sunday = now - datetime.timedelta(days=days_since_sunday)
            last_sunday = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1週間以上前なら録音不可
        if (now - last_sunday).days >= 7:
            return None, None

        # 放送開始: 日曜 1:00, 終了: 3:00
        start = last_sunday.replace(hour=1, minute=0)
        end = last_sunday.replace(hour=3, minute=0)

        return start, end

    def test_audrey_ann_first_5min(self):
        """オードリーのANN 冒頭5分の録音テスト"""
        start, end = self._get_last_saturday_broadcast_time()
        if start is None:
            self.skipTest("直近の放送が1週間以上前のためスキップ")

        recorder = RadikoRecorder()
        station_id = 'LFR'
        fromtime = start.strftime('%Y%m%d%H%M')
        totime = (start + datetime.timedelta(minutes=5)).strftime('%Y%m%d%H%M')
        expected_duration = 5 * 60  # 5分

        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as f:
            fname = f.name
        try:
            res = recorder.record(station_id, fromtime, totime, fname)
            self.assertEqual(res.returncode, 0, f"録音失敗: {res.stderr.decode() if res.stderr else ''}")
            self.assertTrue(os.path.exists(fname))
            size = os.path.getsize(fname)
            self.assertGreater(size, 100000, f"ファイルサイズが小さすぎる: {size} bytes")
            # 再生時間のチェック（±10秒の誤差を許容）
            duration = get_audio_duration(fname)
            self.assertAlmostEqual(duration, expected_duration, delta=10,
                msg=f"再生時間が期待値と異なる: {duration:.1f}秒 (期待: {expected_duration}秒)")
            print(f"録音成功: {fname}, サイズ: {size} bytes, 再生時間: {duration:.1f}秒")
        finally:
            if os.path.exists(fname):
                os.unlink(fname)

    def test_audrey_ann_full(self):
        """オードリーのANN フル(2時間)録音テスト"""
        start, end = self._get_last_saturday_broadcast_time()
        if start is None:
            self.skipTest("直近の放送が1週間以上前のためスキップ")

        recorder = RadikoRecorder()
        station_id = 'LFR'
        fromtime = start.strftime('%Y%m%d%H%M')
        totime = end.strftime('%Y%m%d%H%M')
        expected_duration = 2 * 60 * 60  # 2時間

        with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as f:
            fname = f.name
        try:
            res = recorder.record(station_id, fromtime, totime, fname)
            self.assertEqual(res.returncode, 0, f"録音失敗: {res.stderr.decode() if res.stderr else ''}")
            self.assertTrue(os.path.exists(fname))
            size = os.path.getsize(fname)
            # 2時間の録音は約40MB程度を期待
            self.assertGreater(size, 30000000, f"ファイルサイズが小さすぎる: {size} bytes")
            # 再生時間のチェック（±30秒の誤差を許容）
            duration = get_audio_duration(fname)
            self.assertAlmostEqual(duration, expected_duration, delta=30,
                msg=f"再生時間が期待値と異なる: {duration:.1f}秒 (期待: {expected_duration}秒)")
            print(f"録音成功: {fname}, サイズ: {size / 1024 / 1024:.1f} MB, 再生時間: {duration / 60:.1f}分")
        finally:
            if os.path.exists(fname):
                os.unlink(fname)


if __name__ == '__main__':
    unittest.main()
