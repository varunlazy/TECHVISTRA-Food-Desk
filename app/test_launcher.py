import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import launcher

class StartupTests(unittest.TestCase):
 def test_symlink_environment_uses_prefix(self):
  # Typical macOS case: both executable paths resolve to the same binary.
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'.venv/bin').mkdir(parents=True)
   (root/'.venv/bin/python').symlink_to(launcher.sys.executable)
   with patch.object(launcher,'ROOT',root),patch.object(launcher.sys,'prefix','/system'),patch.object(launcher.sys,'argv',['launcher.py','--open']),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
    self.assertEqual(launcher.main(),0)
    self.assertEqual(run.call_args.args[0][0],str(root/'.venv/bin/python'))
 def test_child_failure_propagates(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'.venv/bin').mkdir(parents=True);(root/'.venv/bin/python').touch()
   with patch.object(launcher,'ROOT',root),patch.object(launcher.sys,'prefix','/system'),patch.object(launcher.sys,'argv',['launcher.py']),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
    self.assertEqual(launcher.main(),1)
 def test_errors_are_logged_without_console_traceback(self):
  for error in [RuntimeError('cryptography missing'),PermissionError('read only'),launcher.sqlite3.DatabaseError('malformed database'),OSError('Port 8787 busy'),SystemExit('failed setup')]:
   with self.subTest(error=error), tempfile.TemporaryDirectory() as d:
    output=io.StringIO()
    with patch.object(launcher,'ROOT',Path(d)),patch.object(launcher,'main',side_effect=error),contextlib.redirect_stdout(output):
     self.assertEqual(launcher.run(),1)
    self.assertTrue((Path(d)/'data/startup-error.log').exists())
    self.assertNotIn('Traceback',output.getvalue())
 def test_interrupt_is_clean(self):
  with patch.object(launcher,'main',side_effect=KeyboardInterrupt),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(launcher.run(),0)

if __name__=='__main__':unittest.main()
