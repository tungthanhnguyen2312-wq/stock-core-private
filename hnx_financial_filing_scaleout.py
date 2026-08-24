"""Bounded, retained-RSS HNX financial-filing acquisition and exact-text projection."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

import hnx_disclosure_feed_parser as feed_parser
import official_document_store as store
from official_source_registry import ADMITTED, admit, load_registry

CONTRACT_VERSION = "hnx_official_financial_filing_scaleout/v1"
SOURCE_ID = "hnx"
MAX_FILINGS = 11
_NUMBER = r"(?:\(?\d{1,3}(?:[,.]\d{3})+\)?|\(?\d+\)?)"
_METRICS = {
    "revenue": (r"doanh thu bán hàng và cung cấp dịch vụ", r"revenue"),
    "parent_net_income": (r"lợi nhuận sau thuế .*cổ đông công ty mẹ", r"profit after tax .*owners of the parent"),
    "total_assets": (r"tổng cộng tài sản", r"total assets"),
    "total_liabilities": (r"nợ phải trả", r"liabilities"),
    "cash_and_equivalents": (r"tiền và các khoản tương đương tiền", r"cash and cash equivalents"),
    "operating_cash_flow": (r"lưu chuyển tiền thuần từ hoạt động kinh doanh", r"net cash flows? from operating activities"),
    "interest_expense": (r"chi phí lãi vay", r"interest expense"),
}

GAP_METRICS = ("revenue", "parent_net_income", "total_assets", "total_liabilities", "parent_equity", "cash_and_equivalents", "operating_cash_flow", "capital_expenditure", "interest_bearing_debt", "interest_expense", "weighted_average_basic_shares")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data: raise ValueError("IMMUTABLE_CONTENT_CONFLICT:" + str(path))
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data); temporary = Path(tmp.name)
    temporary.replace(path)


def _publication(raw: str | None) -> str | None:
    try:
        return parsedate_to_datetime(raw or "").date().isoformat()
    except (TypeError, ValueError):
        pass
    parsed = feed_parser.parse_vietnamese_date(raw or "") if raw else None
    if parsed: return parsed
    match = re.search(r"(\d{4})", raw or "")
    return match.group(1) if match else None


def discover(feed_payload: bytes, registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    parsed = feed_parser.parse_disclosure_rss(feed_payload, feed_url="https://www.hnx.vn/vi-vn/3/vi_vn/thong-tin-cong-bo-tu-to-chuc-phat-hanh.rss", source_id=SOURCE_ID, registry=registry)
    rows=[]
    for item in parsed["items"]:
        title=str(item.get("title") or ""); lowered=title.lower()
        if "báo cáo tài chính" not in lowered or not item.get("canonical_url"): continue
        year=re.search(r"năm\s*(20\d{2})", lowered)
        if not year: continue
        interim="bán niên" in lowered or "quý" in lowered
        rows.append({"title": title, "detail_url": item["canonical_url"], "published_at": _publication(item.get("pub_date_raw")), "reporting_period": f"{year.group(1)}-H1" if "bán niên" in lowered else year.group(1), "document_type": "reviewed_interim_financial_statements" if interim else "audited_annual_financial_statements", "title_scope": "separate" if "công ty mẹ" in lowered else "UNKNOWN"})
    return rows[:MAX_FILINGS]


def _fetch(url: str, document_type: str, registry: Mapping[str, Any]) -> dict[str, Any]:
    decision=admit(SOURCE_ID, url, document_type, registry=registry)
    if decision["decision"] != ADMITTED: return {"state":"REFUSED", "reason":decision["reason"], "url":url}
    try:
        with urlopen(Request(url,headers={"Accept":"application/pdf,text/html;q=0.9", "User-Agent":"StockLookup-HNX-Filing-Scaleout/1.0"}), timeout=15) as response:
            data=response.read(); status=response.status; content_type=response.headers.get_content_type(); final_url=response.geturl()
    except Exception as exc: return {"state":"FAILED", "reason":type(exc).__name__, "url":url}
    if not 200 <= status < 300: return {"state":"HTTP_ERROR", "http_status":status, "url":url}
    if not data or content_type not in {"application/pdf","text/html","application/octet-stream"}: return {"state":"INVALID_CONTENT", "content_type":content_type, "url":url}
    if not (data.startswith(b"%PDF") or b"<html" in data[:4096].lower()): return {"state":"INVALID_CONTENT", "content_type":content_type, "url":url}
    return {"state":"RETAINED", "url":final_url, "http_status":status, "content_type":content_type, "data":data}


def _pdf_metadata(data: bytes, reporting_period: str, title_scope: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        from pypdf import PdfReader
        import io
        pages=[page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]
    except Exception: return ({"scope":"UNKNOWN", "audit_review_status":"UNKNOWN", "currency":"UNKNOWN", "unit_scale":None, "parser_status":"NEEDS_OCR"}, [])
    text="\n".join(pages).lower()
    scope="consolidated" if "hợp nhất" in text or "consolidated" in text else title_scope
    audit="REVIEWED" if "soát xét" in text or "reviewed" in text else ("AUDITED" if "kiểm toán" in text or "audited" in text else "UNKNOWN")
    unit_match=re.search(r"(?:đơn vị tính|unit)\s*[:\-]?\s*([^\n]{1,80})", text)
    unit_text=unit_match.group(1).strip() if unit_match else ""
    scale=1 if re.search(r"\b(vnd|đồng)\b", unit_text) and "nghìn" not in unit_text and "triệu" not in unit_text else (1000 if "nghìn" in unit_text else (1000000 if "triệu" in unit_text else None))
    facts=[]
    for metric, labels in _METRICS.items():
        matches=[]
        for page_no, page in enumerate(pages, 1):
            for line in page.splitlines():
                if any(re.search(label, line, re.I) for label in labels):
                    values=re.findall(_NUMBER, line)
                    if len(values)==1: matches.append((page_no,line,values[0]))
        if len(matches)==1 and scale is not None and scope in {"consolidated","separate"}:
            page,line,value=matches[0]; facts.append({"canonical_metric":metric,"raw_value_text":value,"value":int(value.replace(",","").replace(".","").replace("(","-").replace(")",""))*scale,"source_page":page,"citation_text":line,"reporting_period":reporting_period,"statement_scope":scope,"currency":"VND","unit_scale":scale,"qualification_state":"QUALIFIED_OFFICIAL_EXACT_SINGLE_VALUE_LINE"})
    return ({"scope":scope,"audit_review_status":audit,"currency":"VND" if scale else "UNKNOWN","unit_scale":scale,"parser_status":"DIRECT_TEXT"}, facts)

def _attachment_token(url: str) -> str | None:
    match=re.search(r"(?:^|_)([A-Z]{3})_",url.rsplit("/",1)[-1])
    return match.group(1) if match else None


def run(*, feed_path: Path, destination: Path) -> dict[str, Any]:
    registry=load_registry(); feed=feed_path.read_bytes(); candidates=discover(feed, registry); raw_dir=destination/"raw"; store_root=destination/"store"; documents=[]; facts=[]; failures=[]
    for candidate in candidates:
        detail=_fetch(candidate["detail_url"], candidate["document_type"], registry)
        if detail["state"] != "RETAINED": failures.append({"stage":"detail",**detail}); continue
        detail_sha=_sha(detail["data"]); detail_path=raw_dir/"details"/(detail_sha+".html"); _atomic(detail_path,detail["data"])
        parsed=feed_parser.parse_disclosure_detail(detail["data"],url=candidate["detail_url"]); ticker=parsed.get("ticker")
        attachments=[url for url in (parsed.get("attachment_urls") or []) if re.search(r"financialstatements|baocaotaichinh",url,re.I)]
        if not attachments: failures.append({"stage":"detail_schema", "url":candidate["detail_url"], "ticker":ticker, "attachment_count":0}); continue
        filing=_fetch(attachments[0], candidate["document_type"], registry)
        if filing["state"] != "RETAINED": failures.append({"stage":"filing",**filing}); continue
        suffix=".pdf" if filing["data"].startswith(b"%PDF") else ".html"; filing_path=raw_dir/"filings"/(_sha(filing["data"])+suffix); _atomic(filing_path,filing["data"])
        token=_attachment_token(attachments[0]); retained_ticker=ticker or "UNRESOLVED"
        adopted=store.adopt_retained_document(store_root,filing_path,ticker=retained_ticker,document_type=candidate["document_type"],source_url=attachments[0],source_authority="Hanoi Stock Exchange",observed_at=_now(),published_at=candidate["published_at"],execute=True)
        metadata, extracted=_pdf_metadata(filing["data"],candidate["reporting_period"],candidate["title_scope"])
        if ticker is None: extracted=[]
        record={**candidate,"ticker":ticker,"attachment_ticker_token":token,"ticker_identity_status":"QUALIFIED_DETAIL_FIELD" if ticker else "UNRESOLVED_ATTACHMENT_FILENAME_TOKEN","detail_sha256":detail_sha,"document_id":adopted["document_id"],"document_sha256":adopted["content_sha256"],"filing_url":attachments[0],"metadata":metadata,"facts":extracted}
        documents.append(record)
        for fact in extracted: facts.append({**fact,"ticker":ticker,"document_id":adopted["document_id"],"document_sha256":adopted["content_sha256"]})
    resolved=sorted({str(row["ticker"]) for row in documents if row.get("ticker")})
    artifact={"schema_version":"1.0.0","contract_version":CONTRACT_VERSION,"feed":{"path":str(feed_path),"sha256":_sha(feed),"candidate_count":len(candidates)},"documents":documents,"facts":facts,"failures":failures,"coverage":{"documents_discovered":len(candidates),"documents_retained":len(documents),"resolved_tickers":resolved,"ticker_unresolved_documents":sum(1 for row in documents if not row.get("ticker")),"canonical_observations":len(facts)},"authority_boundary":{"provider_used_as_substitute":False,"canonical_store_mutated":False,"is_actionable":False}}
    identity=hashlib.sha256(json.dumps(artifact,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest(); artifact["artifact_identity"]="hnx_official_financial_filing_scaleout:"+identity; artifact["artifact_sha256"]=identity
    return artifact

def data_gap_matrix(artifact: Mapping[str, Any]) -> dict[str, Any]:
    facts=list(artifact.get("facts") or [])
    return {"schema_version":"1.0.0","contract_version":"official_financial_data_gap_matrix/v1","source_artifact_identity":artifact.get("artifact_identity"),"periods":{"2026-H1":{"documents_retained":len(artifact.get("documents") or []),"resolved_tickers":len((artifact.get("coverage") or {}).get("resolved_tickers") or []),"ticker_unresolved_documents":sum(1 for row in artifact.get("documents") or [] if not row.get("ticker"))}},"canonical_facts":[{"metric":metric,"available":sum(1 for fact in facts if fact.get("canonical_metric")==metric),"blocked_reason":"TICKER_IDENTITY_AND_EXACT_CITED_VALUE_NOT_BOTH_QUALIFIED"} for metric in GAP_METRICS],"downstream":{"fundamental":"UNCHANGED","peer":"UNCHANGED","scenario":"UNCHANGED","valuation":"UNCHANGED"},"missing_is_zero":False}
