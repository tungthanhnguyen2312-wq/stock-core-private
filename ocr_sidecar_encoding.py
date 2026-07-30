from __future__ import annotations
import hashlib,json

def decode_utf8(data:bytes,*,kind:str)->str:
 if data.startswith(b'\xef\xbb\xbf'): data=data[3:]
 try:return data.decode('utf-8')
 except UnicodeDecodeError as e: raise ValueError(f'{kind}_utf8_invalid_at_{e.start}') from e

def diagnostic(data:bytes)->dict:
 try:return {'encoding':'utf-8','text':decode_utf8(data,kind='diagnostic'),'raw_sha256':hashlib.sha256(data).hexdigest()}
 except ValueError:return {'encoding':'binary_unavailable','text':None,'raw_sha256':hashlib.sha256(data).hexdigest()}

def stable_json(value)->bytes:return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')