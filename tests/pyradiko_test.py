import unittest
import tempfile, os
import datetime

from pyradiko import RadikoRecorder

class TestRadikoRecorder(unittest.TestCase):
    def test_record(self):
        recorder = RadikoRecorder()
        station_id = 'LFR'
        now = datetime.datetime.now()
        totime = (now - datetime.timedelta(minutes=2)).strftime('%Y%m%d%H%M')
        fromtime = (now - datetime.timedelta(minutes=5)).strftime('%Y%m%d%H%M')
        with tempfile.NamedTemporaryFile(suffix='.m4a') as f:
            recorder.record(station_id, fromtime, totime, f.name)
            self.assertTrue(os.path.exists(f.name))
            self.assertGreater(os.path.getsize(f.name), 0)

if __name__ == '__main__':
    unittest.main()