import unittest
from ocr_sidecar_encoding import decode_utf8,diagnostic,stable_json
class T(unittest.TestCase):
 def test_utf8_and_bom(self):self.assertEqual(decode_utf8('đ'.encode(),kind='ocr'),'đ');self.assertEqual(decode_utf8(b'\xef\xbb\xbf'+'đ'.encode(),kind='ocr'),'đ')
 def test_diagnostic_and_malformed(self):self.assertIsNone(diagnostic(b'\x9d')['text']);self.assertRaisesRegex(ValueError,'ocr_utf8_invalid_at_0',decode_utf8,b'\x9d',kind='ocr')
 def test_json(self):self.assertEqual(stable_json({'b':1,'a':'đ'}),stable_json({'a':'đ','b':1}))
if __name__=='__main__':unittest.main()