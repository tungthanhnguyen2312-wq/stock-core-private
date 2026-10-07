"""Read-only qualification of the bounded official current-common-share acquisition batch."""
from __future__ import annotations

from collections import Counter
from collections import defaultdict
from datetime import datetime
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from field_temporal_contract import stable_id

CONTRACT_VERSION = "current_common_shares_official_evidence_acquisition/v1"
QUALIFIED = "CURRENT_COMMON_OUTSTANDING_QUALIFIED"
RETAINED_UNRESOLVED = "EVIDENCE_RETAINED_BUT_CURRENTNESS_UNRESOLVED"
ACTION_UNRESOLVED = "CORPORATE_ACTION_EXECUTION_UNRESOLVED"
CONFLICTING = "CONFLICTING_OFFICIAL_EVIDENCE"
NEEDS_ROUTE = "NEEDS_OWNER_SOURCE_ROUTE_APPROVAL"
NOT_FOUND = "OFFICIAL_EVIDENCE_NOT_FOUND"


def qualify_retained_common_share_note(*, materialization: Mapping[str, Any],
        document: Mapping[str, Any], assurance: Mapping[str, Any], effective_date: str,
        knowledge_available_at: str) -> dict[str, Any]:
    """Qualify a dated ordinary-outstanding note; never extend its point coverage.

    Bind the explicit outstanding parent row and its immediately following
    common-class row to the literal year-end column. Issued/listed/weighted
    quantities elsewhere in the note cannot satisfy either row.
    """
    def text(tokens):
        raw = ' '.join(t['text'] for t in sorted(tokens, key=lambda t: t['x0']))
        folded = ''.join(c for c in unicodedata.normalize('NFD', raw.lower()) if not unicodedata.combining(c))
        return folded.replace('đ', 'd')

    sha = str(document.get('sha256') or '')
    if document.get('ticker') != 'HPG':
        raise ValueError('CAPITAL_NOTE_ISSUER_BINDING_MISMATCH')
    if not re.fullmatch('[0-9a-f]{64}', sha) or materialization.get('document_sha256') != sha:
        raise ValueError('RETAINED_SOURCE_HASH_MISMATCH')
    if assurance.get('document_sha256') != sha or assurance.get('state') != 'QUALIFIED' or assurance.get('audit_or_review_status') != 'audited':
        raise ValueError('AUDITOR_EVIDENCE_NOT_QUALIFIED')
    day = datetime.strptime(effective_date, '%Y-%m-%d').date()
    if (day.month, day.day) != (12, 31) or document.get('reporting_period') != str(day.year):
        raise ValueError('EXACT_YEAR_END_IDENTITY_REQUIRED')
    known = datetime.fromisoformat(knowledge_available_at.replace('Z', '+00:00'))
    observed = datetime.fromisoformat(str(document['observed_at']).replace('Z', '+00:00'))
    if known.tzinfo is None or observed.tzinfo is None or known < observed:
        raise ValueError('KNOWLEDGE_TIME_BACKDATING_REFUSED')
    tokens = materialization.get('tokens') or []
    if not tokens or any(t.get('provenance') != 'OCR_TSV_POSITIONED_TOKEN' or not t.get('token_id') for t in tokens):
        raise ValueError('POSITIONED_SOURCE_TOKENS_REQUIRED')
    grouped = defaultdict(list)
    for token in tokens:
        hierarchy = token['tsv_hierarchy']
        grouped[tuple(hierarchy[k] for k in ('block_num', 'par_num', 'line_num'))].append(token)
    lines = sorted(grouped.values(), key=lambda ts: min(t['top'] for t in ts))
    date_cue = f'tai ngay 31 thang 12 nam {day.year}'
    if not any(date_cue in text(line) for line in lines):
        raise ValueError('EXPLICIT_NOTE_DATE_MISSING')
    parents = [i for i, line in enumerate(lines) if text(line).startswith('so luong co phieu dang luu hanh ')]
    if len(parents) != 1 or parents[0] + 1 >= len(lines):
        raise ValueError('OUTSTANDING_PARENT_ROW_NOT_UNIQUE')
    index = parents[0]
    parent, common = lines[index], lines[index + 1]
    if not text(common).startswith('co phieu pho thong '):
        raise ValueError('EXPLICIT_COMMON_CLASS_ROW_MISSING')
    if min(t['top'] for t in common) - min(t['top'] for t in parent) > 40:
        raise ValueError('COMMON_CLASS_ROW_NOT_ADJACENT')
    # The nearest preceding two-column header owns both numeric cells.
    headers = [line for line in lines[:index] if text(line) == 'so cuoi nam so dau nam']
    if not headers:
        raise ValueError('YEAR_END_COLUMN_HEADER_MISSING')
    header = sorted(headers[-1], key=lambda t: t['x0'])
    if len(header) != 6:
        raise ValueError('YEAR_END_COLUMN_HEADER_AMBIGUOUS')
    left = header[0]['x0'] - 40
    split = (header[2]['x1'] + header[3]['x0']) / 2
    selected = []
    for row in (parent, common):
        cells = [t for t in row if left <= t['x0'] < split]
        if len(cells) != 1 or not re.fullmatch(r'[1-9][0-9]{0,2}(?:\.[0-9]{3})+', cells[0]['text']):
            raise ValueError('COMMON_SHARE_NUMERIC_CELL_AMBIGUOUS')
        selected.append(cells[0])
    values = [int(t['text'].replace('.', '')) for t in selected]
    if values[0] != values[1]:
        raise ValueError('OUTSTANDING_AND_COMMON_ROWS_CONFLICT')
    observation = {
        'contract_version': 'retained_common_share_note/v1', 'ticker': document['ticker'],
        'identity': 'common_shares_outstanding', 'share_count_identity': 'common_shares_outstanding',
        'share_class': 'common_outstanding', 'value': values[0], 'unit': 'shares',
        'effective_date': effective_date, 'coverage_through': effective_date,
        'observed_at': document['observed_at'], 'knowledge_available_at': knowledge_available_at,
        'published_at': document.get('published_at'), 'source': 'official_retained_evidence',
        'source_url': document['canonical_url'], 'document_sha256': sha, 'evidence_id': document['document_id'],
        'qualification_state': 'QUALIFIED', 'lifecycle_state': 'AUDITED_PERIOD_END_OBSERVATION',
        'citation': {'pdf_page': materialization['page_number'], 'parent_label': 'Số lượng cổ phiếu đang lưu hành',
            'share_class_label': 'Cổ phiếu phổ thông', 'column_label': 'Số cuối năm',
            'source_tokens': parent + common + header, 'rendered_image_sha256': materialization['rendered_image_sha256'],
            'date_tokens': next(line for line in lines if date_cue in text(line)),
            'render_rotation': materialization['rotation']},
        'assurance_evidence': dict(assurance),
        'limitations': ['POINT_OBSERVATION_ONLY', 'SUBSEQUENT_SHARE_CHANGING_CONTINUITY_NOT_PROVEN',
                        'NO_COMPLETED_SESSION_OR_T0_BACKFILL'],
    }
    observation['citation_id'] = stable_id(observation)
    return observation


def _records(manifests: Sequence[Mapping[str, Any]], ticker: str) -> list[dict[str, Any]]:
    rows = [dict(row) for manifest in manifests for row in manifest.get("records", []) if row.get("ticker") == ticker]
    return sorted(rows, key=lambda row: (str(row.get("published_at") or ""), str(row.get("sha256") or "")))


def build_acquisition_result(*, p3f3: Mapping[str, Any], p3f4: Mapping[str, Any], p3f5: Mapping[str, Any],
                             p3f6: Mapping[str, Any], manifests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reconcile retained sources without inferring a share transition or route."""
    cohort = sorted(row["canonical_instrument"]["canonical_ticker"] for row in p3f3["current_price_authority_matrix"])
    target = p3f6["provider_proxy_coverage"]["valuation_date"]
    comparisons = list(p3f5["official_comparison_matrix"])
    common = {row["ticker"]: row["official"] for row in comparisons
              if isinstance(row.get("official"), Mapping)
              and row["official"].get("identity") == "common_shares_outstanding"}
    action_blocked = {row["ticker"]: list(row.get("blockers") or []) for row in p3f6["corporate_action_blocks"]}
    transition = p3f4["representative_proofs"]["executed_transition"]["bridge_result"]
    coverage = transition["coverage_through"]
    rows = []
    for ticker in cohort:
        evidence = _records(manifests, ticker)
        result = ACTION_UNRESOLVED if ticker in action_blocked else (RETAINED_UNRESOLVED if evidence else NOT_FOUND)
        official = common.get(ticker)
        denominator = None
        effective = None
        continuity = None
        notes = []
        if official:
            denominator, effective, continuity = official["value"], official["effective_on"], coverage
            notes.append("Executed common-share count retained; continuity does not reach valuation date.")
        if ticker in action_blocked:
            notes.append("Retained corporate-action timing/result is unresolved; no execution or resulting shares inferred.")
        if not evidence:
            notes.append("No retained official document is available for this bounded cohort item.")
        rows.append({"ticker": ticker, "result": result, "official_documents": [{
            "document_id": row.get("document_id"), "source_id": row.get("source_id"), "source_url": row.get("canonical_url"),
            "sha256": row.get("sha256"), "published_at": row.get("published_at"), "document_class": row.get("document_class"),
            "extraction_status": row.get("extraction_status"),
        } for row in evidence], "current_common_shares": denominator, "effective_date": effective,
            "continuity_through": continuity, "covered_through_valuation_date": False,
            "blockers": action_blocked.get(ticker, ["CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN"]),
            "route_requirement": "NO_OWNER_ROUTE_APPROVAL_REQUIRED; FINITE_POST_PERIOD_LOCATOR_NOT_RETAINED",
            "notes": notes})
    artifact = {"contract_version": CONTRACT_VERSION, "valuation_date": target, "cohort": cohort,
                "source_artifact_identities": {"p3f3": p3f3.get("artifact_identity"), "p3f4": p3f4.get("artifact_identity"),
                                                 "p3f5": p3f5.get("artifact_identity"), "p3f6": p3f6.get("artifact_identity")},
                "acquisition_scope": {"new_live_document": "HPG official issuer-IR listing-change notice",
                                      "previous_1024_byte_capture": "PRESERVED_NON_CITABLE_STREAM_TRUNCATION",
                                      "network_requests": 2, "retries": 0, "runtime_or_database_writes": False},
                "acquired_source_citations": [{"ticker": "HPG", "source_url": "https://www.hoaphat.com.vn/tin-tuc/thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html",
                    "document_sha256": "e7ceec0fb6b6edb9aa12fd88c45d151dbd5f0ad22d46fbe0fdf81f6bb88bc78c",
                    "retrieved_at": "2026-08-22T11:09:12.607459Z", "issuer_identity": "HPG",
                    "evidence_span": "Số lượng chứng khoán sau khi thay đổi niêm yết: 8.442.964.520 cổ phiếu; Ngày thay đổi niêm yết có hiệu lực: 02/07/2026.",
                    "status": "EXECUTED_LISTING_CHANGE", "record_date": None, "ex_date": None,
                    "effective_date": "2026-07-02", "currentness_verdict": "COVERAGE_THROUGH_2026_08_19_NOT_PROVEN"}],
                "symbol_results": rows,
                "summary": {"cohort_denominator": len(cohort), "qualified_for_valuation_date": 0,
                            "result_counts": dict(sorted(Counter(row["result"] for row in rows).items()))},
                "denominator_eligibility": [{"ticker": row["ticker"], "eligible": False,
                                               "reason": row["blockers"][0]} for row in rows],
                "boundaries": {"valuation_implemented": False, "provider_proxy_promoted": False,
                               "historical_pit_promoted": False, "raw_as_traded_promoted": False,
                               "authority_remains_fail_closed": True},
                "verdict": "NO_QUALIFYING_CURRENT_SHARE_EVIDENCE"}
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"current_common_shares_official_evidence_acquisition:{artifact['artifact_sha256']}"
    return artifact
