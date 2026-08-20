import inspect
from official_route_ownership_evidence import qualify
REG={"sources":[{"source_id":"issuer_ir","activation":"approved","allowed_hosts":["issuer.example"]}]}
def test_bound_approved_host_qualifies():
 assert qualify({"candidate_locator":"https://issuer.example/x","issuer_legal_identity":"X","profile_locator":"https://issuer.example/x","raw_document_sha256":"a"*64,"ownership_evidence":"retained_official_document_locator"},REG)["route_approval_eligible"]
def test_mirror_and_missing_identity_block():
 assert not qualify({"candidate_locator":"https://mirror.example/x","issuer_legal_identity":"X"},REG)["route_approval_eligible"]
def test_no_ticker_branch(): assert "if ticker ==" not in inspect.getsource(qualify)
