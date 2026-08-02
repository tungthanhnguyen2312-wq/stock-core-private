import os,unittest
from unittest.mock import patch
from eodhd_access import credential_status,sanitize
class T(unittest.TestCase):
 def test_missing(self):
  with patch.dict(os.environ,{},clear=True): self.assertFalse(credential_status()['configured'])
 def test_env_and_sanitize(self):
  with patch.dict(os.environ,{'EODHD_API_TOKEN':'secret'},clear=True): self.assertTrue(credential_status()['configured'])
  self.assertEqual(sanitize('https://x/?api_token=secret'),'https://x/')
