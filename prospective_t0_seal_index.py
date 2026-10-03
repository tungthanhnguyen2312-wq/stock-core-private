"""Verified compact T0 projection. Snapshot/write receipt remain the authority.

Normal lookup reads only compact companions and stats the immutable snapshot.
Explicit recovery streams the original once; it never seals a later recomputation.
"""
from __future__ import annotations

import json
from pathlib import Path
import prospective_market_snapshot_contract as market
import prospective_decision_retention as retention
import contextual_technical_dispatch as dispatch
from atomic_io import retain_immutable_bytes

CONTRACT_VERSION = "prospective_t0_seal_index/v1"
WRITE_RECEIPT_VERSION = "prospective_t0_snapshot_write_receipt/v1"


def identified(body, kind):
    body.update(market.content_identity(body, kind=kind))
    return body


def verify(value, kind):
    if value.get("contract_version") != kind+"/v1" or any(value.get(k) != v for k,v in market.content_identity(value,kind=kind).items()):
        raise ValueError("T0_SEAL_INDEX_IDENTITY_INVALID:"+kind)
    return value


def fingerprint(path):
    stat = path.stat()
    return {"bytes":stat.st_size,"mtime_ns":stat.st_mtime_ns,"ctime_ns":stat.st_ctime_ns,
            "device":stat.st_dev,"inode":stat.st_ino}


def entry(ticker, row):
    if row.get("ticker") != ticker or row.get("prospective_snapshot_record_identity") != retention.RECORD_PREFIX+retention._hash({k:v for k,v in row.items() if k!="prospective_snapshot_record_identity"}):
        raise ValueError("T0_INDEX_RECORD_INVALID")
    context = ((row.get("integrated_decision_at_t0") or {}).get("contextual_technical_context") or {}).get("projection")
    version = dispatch.verify_context(context,ticker=ticker,session=row["decision_session"]) if context else None
    return {"ticker":ticker,"session":row["decision_session"],"technical_contract_version":version,
            "context_identity":context["artifact_identity"] if context else None,"snapshot_record_identity":row["prospective_snapshot_record_identity"],
            "integrated_decision_identity":row["integrated_decision_identity"],
            "source_decision_artifact_identity":row["source_decision_artifact_identity"]}


def publish(path, metadata, entries, *, created_at, file_sha256, diagnostic=False):
    path = Path(path)
    session = metadata["session"]
    if metadata.get("contract_version") != retention.CONTRACT_VERSION or not metadata.get("decision_count"):
        raise ValueError("NONEMPTY_ORIGINAL_T0_REQUIRED")
    if session < dispatch.PRODUCTION_V2_START_SESSION and not diagnostic:
        raise ValueError("HISTORICAL_INDEX_REQUIRES_REPLAY_DIAGNOSTIC")
    index_path = path.parent/"prospective_t0_seal_index.json"
    receipt_path = path.parent/"prospective_t0_snapshot_write_receipt.json"
    if index_path.exists() and receipt_path.exists():
        index = json.loads(index_path.read_bytes()); receipt = json.loads(receipt_path.read_bytes())
        ref = {"path":str(index_path),"artifact_identity":index["artifact_identity"],"write_receipt_identity":receipt["artifact_identity"]}
        load_verified(ref,expected_snapshot_identity=metadata["snapshot_identity"],session=session)
        return ref
    if receipt_path.exists():
        prior = verify(json.loads(receipt_path.read_bytes()),"prospective_t0_snapshot_write_receipt")
        created_at = prior["index_created_at"]
    body = identified({"contract_version":CONTRACT_VERSION,"session":session,
        "snapshot_identity":metadata["snapshot_identity"],"snapshot_file":path.name,"snapshot_file_sha256":file_sha256,
        "source_integrated_decision_artifact":metadata["source_integrated_decision_artifact"],
        "operation_identity":metadata["daily_session_operation_identity"],"index_created_at":created_at,
        "evaluation_scope":"REPLAY_DIAGNOSTIC" if diagnostic else "ORIGINAL_T0_VERIFIED_PROJECTION",
        "authority_status":"NON_AUTHORITATIVE" if diagnostic else "SNAPSHOT_DERIVED_INDEX_ONLY",
        "records":dict(sorted(entries.items())),"authority_effect":"NONE"},"prospective_t0_seal_index")
    receipt = identified({"contract_version":WRITE_RECEIPT_VERSION,"session":session,
        "snapshot_identity":metadata["snapshot_identity"],"snapshot_file_sha256":file_sha256,
        "snapshot_fingerprint":fingerprint(path),"index_identity":body["artifact_identity"],
        "index_sha256":body["artifact_sha256"],"index_created_at":created_at,"authority_effect":"NONE"},"prospective_t0_snapshot_write_receipt")
    # Receipt first permits index-only recovery with the original creation time.
    if receipt_path.exists():
        original = verify(json.loads(receipt_path.read_bytes()),"prospective_t0_snapshot_write_receipt")
        if original != receipt: raise ValueError("T0_INDEX_PARTIAL_PUBLICATION_CONFLICT")
    retain_immutable_bytes(receipt_path,market.canonical(receipt))
    retain_immutable_bytes(index_path,market.canonical(body))
    return {"path":str(index_path),"artifact_identity":body["artifact_identity"],"write_receipt_identity":receipt["artifact_identity"]}


def from_snapshot(snapshot, path, *, created_at, file_sha256, diagnostic=False):
    if not retention.validate_snapshot(snapshot): raise ValueError("T0_INDEX_SNAPSHOT_INVALID")
    entries = {t:e for t,row in snapshot["records"].items() if (e:=entry(t,row))}
    return publish(path,snapshot,entries,created_at=created_at,file_sha256=file_sha256,diagnostic=diagnostic)


def recover(path, *, created_at, diagnostic=False):
    from bounded_artifact_stream import stream_artifact, source_hash
    path = Path(path); entries = {}
    def extract(t,row):
        e = entry(t,row)
        if e: entries[t]=e
    metadata,digest,count = stream_artifact(path,excluded={"snapshot_identity"},on_record=extract)
    if metadata.get("snapshot_identity") != retention.SNAPSHOT_PREFIX+digest or count != metadata.get("decision_count"):
        raise ValueError("T0_INDEX_SNAPSHOT_BINDING_INVALID")
    return publish(path,metadata,entries,created_at=created_at,file_sha256=source_hash(path),diagnostic=diagnostic)


class SealedBindings:
    def __init__(self,index,receipt_identity=None):
        self.snapshot_identity=index["snapshot_identity"]
        self.identity=self.snapshot_identity
        self.index_identity=index["artifact_identity"]
        self.write_receipt_identity=receipt_identity
        self.records=index["records"]
        self.source_integrated_decision_artifact=index["source_integrated_decision_artifact"]
        self.bindings={t:(r["session"],r["technical_contract_version"],r["context_identity"]) for t,r in self.records.items() if r["context_identity"]}

    def contains_integrated_decision(self,ticker,session,decision_identity):
        row=self.records.get(ticker) or {}
        return bool(decision_identity and row.get("session")==session and row.get("integrated_decision_identity")==decision_identity)

    def contains_technical_context(self,ticker,session,contract_version,context_identity):
        return bool(context_identity and self.bindings.get(ticker)==(session,contract_version,context_identity))

    def contains(self,ticker,session,identity):
        row=self.records.get(ticker) or {}
        return self.contains_integrated_decision(ticker,session,identity) or bool(identity and row.get("session")==session and row.get("context_identity")==identity)

    def verify(self,item):
        if item["knowledge_stage"]=="T0_SEALED" and (item["seal_reference"]!=self.identity or not self.contains(
            item["subject"]["ticker"],item["subject"]["session"],item["source"]["identity"])):
            raise ValueError("THESIS_T0_SOURCE_NOT_SEALED")


def load_verified(ref, *, expected_snapshot_identity, session):
    path = Path(ref["path"])
    if path.stat().st_size > 8*1024*1024: raise ValueError("T0_INDEX_SIZE_LIMIT")
    index = verify(json.loads(path.read_bytes()),"prospective_t0_seal_index")
    receipt = verify(json.loads((path.parent/"prospective_t0_snapshot_write_receipt.json").read_bytes()),"prospective_t0_snapshot_write_receipt")
    if (index["artifact_identity"] != ref["artifact_identity"] or receipt["artifact_identity"] != ref["write_receipt_identity"] or
        index["snapshot_identity"] != expected_snapshot_identity or index["session"] != session or receipt["session"] != session or
        receipt["snapshot_identity"] != expected_snapshot_identity or receipt["index_identity"] != index["artifact_identity"] or
        receipt["index_sha256"] != index["artifact_sha256"] or receipt["snapshot_file_sha256"] != index["snapshot_file_sha256"] or
        index["snapshot_file"] != "prospective_decision_snapshot.json" or
        fingerprint(path.parent/index["snapshot_file"]) != receipt["snapshot_fingerprint"]):
        raise ValueError("T0_INDEX_SNAPSHOT_OR_RECEIPT_BINDING_INVALID")
    for t,row in index["records"].items():
        if (row["ticker"] != t or row["session"] != session or
            (row["context_identity"] and row["technical_contract_version"] not in dispatch.SUPPORTED_VERSIONS) or
            (not row["context_identity"] and row["technical_contract_version"] is not None)):
            raise ValueError("T0_INDEX_ENTRY_INVALID")
    return SealedBindings(index,receipt["artifact_identity"]) if index["evaluation_scope"] != "REPLAY_DIAGNOSTIC" and session >= dispatch.PRODUCTION_V2_START_SESSION else None
