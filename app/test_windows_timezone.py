"""Windows compatibility when the IANA timezone database is unavailable."""
import io
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError
import test_qr_year
import server
import offline_qr

class WindowsTimezone(unittest.TestCase):
 def test_no_timezone_database_required(self):
  with patch('zoneinfo.ZoneInfo',side_effect=ZoneInfoNotFoundError('No timezone database')), patch.object(offline_qr,'ZoneInfo',side_effect=ZoneInfoNotFoundError('No timezone database'),create=True), patch.object(server,'ZoneInfo',side_effect=ZoneInfoNotFoundError('No timezone database'),create=True):
   result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(test_qr_year.QRYear))
   self.assertTrue(result.wasSuccessful())
   self.assertEqual(server.format_ist('2026-11-15T20:45:09+00:00'),'16 Nov 2026, 02:15:09 AM IST')

if __name__=='__main__':unittest.main()
