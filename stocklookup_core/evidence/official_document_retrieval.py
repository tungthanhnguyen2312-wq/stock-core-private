"""Deterministic, citation-bound retrieval over retained official PDFs; Producer research only."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from pypdf import PdfReader

VERSION="1.0.0"
SELECTED=("HPG", "VNM", "VCB")
TOKEN=re.compile(r"[\wÀ-ỹ]+", re.UNICODE)

def _hash_bytes(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""): h.update(block)
    return h.hexdigest()

def _tokens(value: str) -> list[str]: return [x.lower() for x in TOKEN.findall(value)]
def _chunk_id(sha: str, page: int, text: str) -> str: return hashlib.sha256(f"{sha}|{page}|{text}".encode()).hexdigest()
def _load_jsonl(path: Path) -> list[dict[str,Any]]: return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []

def build_index(evidence_root: Path) -> dict[str,Any]:
    """Extract only pages named by existing direct citation metadata, validating every PDF hash."""
    root=Path(evidence_root); manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    citations=_load_jsonl(root/"qualification_citations.jsonl")
    records=[x for x in manifest.get("records",[]) if x.get("ticker") in SELECTED and x.get("reporting_period")=="2024" and x.get("qualification_state")=="qualified" and "consolidated" in str(x.get("evidence_type", "")) and (root / str(x.get("filename") or "")).is_file()]
    chunks=[]; documents=[]
    for doc in sorted(records,key=lambda x:(x["ticker"],x["evidence_id"])):
        path=root/doc["filename"]
        actual=_hash_bytes(path)
        if actual != doc["sha256"]: raise ValueError(f"source_hash_mismatch:{doc['evidence_id']}")
        direct=[c for c in citations if c.get("evidence_id")==doc["evidence_id"] and isinstance(c.get("citation"),dict) and isinstance(c["citation"].get("pdf_page"),int)]
        by_page: dict[int,list[dict[str,Any]]]={}
        for citation in direct: by_page.setdefault(citation["citation"]["pdf_page"],[]).append(citation)
        reader=PdfReader(str(path)); documents.append({"document_id":doc["evidence_id"],"sha256":actual,"ticker":doc["ticker"],"period":doc["reporting_period"],"published_at":doc.get("publication_date"),"observed_at":doc.get("observed_at") or doc.get("retrieved_at"),"pages":len(reader.pages)})
        for page, page_citations in sorted(by_page.items()):
            if not 1 <= page <= len(reader.pages): continue
            text=" ".join((reader.pages[page-1].extract_text() or "").split())
            if not text:
                # Scanned retained PDFs may lack a text layer. Use only existing direct-citation labels as a minimal, source-supported passage; never OCR or infer a financial fact.
                text=" ".join(str(c.get("citation", {}).get(key) or "") for c in page_citations for key in ("line_label_vi", "line_label_en", "form_code", "note_number")).strip()
            if not text: continue
            # 240-token sections are stable, but each result keeps only citations on its exact PDF page.
            words=text.split()
            for offset in range(0,len(words),240):
                body=" ".join(words[offset:offset+240])
                if not body: continue
                chunks.append({"chunk_id":_chunk_id(actual,page,body),"document_id":doc["evidence_id"],"document_sha256":actual,"ticker":doc["ticker"],"period":doc["reporting_period"],"page":page,"section":f"page_{page}_tokens_{offset}_{offset+len(body.split())}","published_at":doc.get("publication_date"),"observed_at":doc.get("observed_at") or doc.get("retrieved_at"),"text":body,"citations":sorted([{ "citation_id":c["citation_id"],"metric":c.get("raw_item_id"),"location":c["citation"]} for c in page_citations],key=lambda x:x["citation_id"])})
    return {"schema_version":VERSION,"documents":documents,"chunks":sorted(chunks,key=lambda x:x["chunk_id"])}

def search(index: Mapping[str,Any], *, ticker: str, period: str, metric: str|None=None, keyword: str|None=None, limit: int=3) -> dict[str,Any]:
    if ticker not in SELECTED or not period or limit < 1: return {"state":"unavailable","reason":"unsupported_query","results":[]}
    terms=set(_tokens(" ".join(x for x in (metric,keyword) if x)))
    if not terms: return {"state":"unavailable","reason":"query_terms_missing","results":[]}
    ranked=[]
    for chunk in index.get("chunks",[]):
        if chunk.get("ticker")!=ticker or chunk.get("period")!=period or not chunk.get("citations"): continue
        score=sum(token in _tokens(chunk["text"]) for token in terms)
        citation_metric={str(c.get("metric","")).lower() for c in chunk["citations"]}
        score += sum(term in citation_metric for term in terms)*2
        if score: ranked.append((score,chunk))
    ranked.sort(key=lambda item:(-item[0],item[1]["chunk_id"]))
    results=[{**chunk,"score":score} for score,chunk in ranked[:limit]]
    return {"state":"available" if results else "unavailable","reason":None if results else "no_source_supported_passage","results":results}