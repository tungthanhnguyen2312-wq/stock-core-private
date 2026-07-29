import sys, unittest
from subprocess_capture import run_utf8
class T(unittest.TestCase):
 def test_utf8_and_determinism(self):
  c=[sys.executable,"-c","import sys;sys.stdout.buffer.write('Tieng Viet'.encode('utf-8'))"];a=run_utf8(c);self.assertEqual(a[1],'Tieng Viet');self.assertEqual(a,run_utf8(c))
 def test_non_utf8_and_malformed_preserved(self):
  a=run_utf8([sys.executable,"-c","import sys;sys.stdout.buffer.write(bytes([129]))"]);self.assertEqual(a[0],0);self.assertIn('\ufffd',a[1])
 def test_stderr_and_exit(self):
  a=run_utf8([sys.executable,"-c","import sys;sys.stderr.buffer.write('loi'.encode());raise SystemExit(7)"]);self.assertEqual(a[0],7);self.assertEqual(a[2],'loi')
 def test_root_and_external_invocation(self):
  from pathlib import Path
  import tempfile
  root=Path(__file__).resolve().parents[1]
  self.assertEqual(run_utf8([sys.executable,'export_ai_bundle.py','--help'],cwd=root)[0],0)
  with tempfile.TemporaryDirectory() as tmp:self.assertEqual(run_utf8([sys.executable,str(root/'export_ai_bundle.py'),'--help'],cwd=tmp)[0],0)
 def test_utf8_evidence_bytes(self):
  import tempfile
  from pathlib import Path
  from subprocess_capture import write_utf8
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'evidence.log';write_utf8(p,'Ti?ng Vi?t\n');a=p.read_bytes();write_utf8(p,'Ti?ng Vi?t\n');self.assertEqual(a,p.read_bytes())
if __name__=='__main__':unittest.main()
