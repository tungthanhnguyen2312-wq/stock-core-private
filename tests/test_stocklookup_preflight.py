from __future__ import annotations
import os, subprocess
import pytest
from stocklookup_preflight import PreflightError, check
def make(tmp_path):
 p=tmp_path/'producer'; p.mkdir(); (p/'daily_analysis_pipeline.py').write_text('x'); r=tmp_path/'runtime'; r.mkdir(); t=tmp_path/'transport'; t.mkdir(); subprocess.run(['git','-C',str(t),'init','-q'],check=True); return p,r,t
def test_pass_and_replay_does_not_require_credentials(tmp_path,monkeypatch):
 p,r,t=make(tmp_path); monkeypatch.delenv('DNSE_TOKEN',raising=False); assert check(producer_root=p,runtime_root=r,transport_root=t,replay_local=True)['status']=='PASS'
def test_credentials_runtime_lock_transport_fail_closed(tmp_path,monkeypatch):
 p,r,t=make(tmp_path); monkeypatch.delenv('DNSE_TOKEN',raising=False)
 with pytest.raises(PreflightError,match='CREDENTIALS'): check(producer_root=p,runtime_root=r,transport_root=t)
 monkeypatch.setenv('DNSE_TOKEN','never-print-this');
 with pytest.raises(PreflightError,match='RUNTIME'): check(producer_root=p,runtime_root=tmp_path/'missing',transport_root=t)
 (p/'locks').mkdir(); (p/'locks'/'daily.lock').write_text('x')
 with pytest.raises(PreflightError,match='LOCK'): check(producer_root=p,runtime_root=r,transport_root=t)
 (p/'locks'/'daily.lock').unlink(); (t/'dirty').write_text('x')
 with pytest.raises(PreflightError,match='DIRTY'): check(producer_root=p,runtime_root=r,transport_root=t)
