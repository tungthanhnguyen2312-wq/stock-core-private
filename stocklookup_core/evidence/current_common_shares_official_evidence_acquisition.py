"""Read-only qualification of the bounded official current-common-share acquisition batch."""
from __future__ import annotations

from collections import Counter
from collections import defaultdict
from datetime import datetime
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from stocklookup_core.evidence.field_identity import stable_id

CONTRACT_VERSION = "current_common_shares_official_evidence_acquisition/v1"
QUALIFIED = "CURRENT_COMMON_OUTSTANDING_QUALIFIED"
RETAINED_UNRESOLVED = "EVIDENCE_RETAINED_BUT_CURRENTNESS_UNRESOLVED"
ACTION_UNRESOLVED = "CORPORATE_ACTION_EXECUTION_UNRESOLVED"
CONFLICTING = "CONFLICTING_OFFICIAL_EVIDENCE"
NEEDS_ROUTE = "NEEDS_OWNER_SOURCE_ROUTE_APPROVAL"
NOT_FOUND = "OFFICIAL_EVIDENCE_NOT_FOUND"


def qualify_retained_share_capital_note(*, document, materialization, assurance,
                                      knowledge_available_at):
    """Finite, visually reviewed capital-note layouts; historical research only.

    These three exact originals are field-level extensions of the retained-note
    owner, not templates for future filings. No caller supplies a value, scope,
    date or lifecycle. Native words / literal TSV cells remain the citations.
    """
    from stocklookup_core.evidence.official_document_qualification import retained_assurance_is_bound
    sha = document.get('sha256')
    if not re.fullmatch('[0-9a-f]{64}', str(sha)) or materialization.get('document_sha256') != sha:
        raise ValueError('RETAINED_SOURCE_HASH_MISMATCH')
    if document.get('acquisition_status') != 'retained' or document.get('source_id') != 'issuer_ir':
        raise ValueError('RETAINED_FIRST_PARTY_RECEIPT_REQUIRED')
    known = datetime.fromisoformat(knowledge_available_at.replace('Z', '+00:00'))
    observed = datetime.fromisoformat(document['observed_at'].replace('Z', '+00:00'))
    published = document.get('published_at')
    if known.utcoffset() is None or observed.utcoffset() is None or known < observed:
        raise ValueError('KNOWLEDGE_TIME_BACKDATING_REFUSED')
    if published is not None:
        pub = datetime.fromisoformat(published.replace('Z', '+00:00'))
        if pub.utcoffset() is None or pub > observed:
            raise ValueError('SOURCE_CLOCK_ORDER_INVALID')
    tokens = materialization.get('tokens') or []
    if not tokens or any(not t.get('token_id') or t.get('provenance') not in
            {'OCR_TSV_POSITIONED_TOKEN', 'NATIVE_PDF_POSITIONED_WORD'} for t in tokens):
        raise ValueError('POSITIONED_SOURCE_TOKENS_REQUIRED')

    def region(box):
        x0, y0, x1, y1 = box
        return [t for t in tokens if x0 <= t['x0'] < x1 and y0 <= t['top'] < y1]

    def require(box, phrase):
        raw = ' '.join(t['text'] for t in sorted(region(box), key=lambda t: t['raw_token_order']))
        if phrase not in raw:
            raise ValueError('EXPLICIT_CAPITAL_LABEL_OR_DATE_MISSING')

    issuer, page = document.get('ticker'), materialization.get('page_number')
    # Coordinates belong only to these byte-pinned pages, with the retained
    # renderer (TSV) or native PDF points. No font/OCR character repair.
    if sha == '309f86836d9f00b37e3cccb25da9e7ffd0dab6c531be995618542004acccdf1d':
        expected = ('PNJ', 89, '2025')
        require((0, 1780, 1200, 1840), 'Number of ordinary shares')
        require((0, 2080, 1200, 2150), 'Number of shares issued')
        require((0, 2150, 1200, 2210), 'Number of shares repurchased')
        require((0, 2210, 1200, 2290), 'Number of existing shares in circulation')
        # Existing metadata-only heading fold; amounts never pass through it.
        from stocklookup_core.evidence.financial_document_text import _normalize
        header = region((1200, 1870, 1900, 1940))
        if [_normalize(t['text']) for t in sorted(header, key=lambda t: t['x0'])] != ['2025', '2024']:
            raise ValueError('EXPLICIT_CAPITAL_LABEL_OR_DATE_MISSING')
        columns, dates = [(1200, 1500), (1550, 1900)], ['2025-12-31', '2024-12-31']
        rows = [('ISSUED_SHARES', 2100, 2145), ('TREASURY_SHARES', 2150, 2200),
                ('OUTSTANDING_SHARES', 2230, 2290)]
        scope, share_class, separator = 'issuer', 'ordinary', ','
    elif sha == 'a7360d2fc9a8a67a1535820813cda2bb8ef288466cd36c949e050c2f2a1b290a':
        expected = ('PVD', 34, '2026-H1')
        require((0, 1480, 1950, 1540), 'Tai ngay 30 thang 06 năm 2026')
        require((0, 1800, 800, 1860), 'cổ phan da phat hanh')
        require((0, 1940, 1000, 1990), 'mua lai cua chinh minh')
        require((0, 2120, 1000, 2160), 'cổ phan hién dang Lưu hanh')
        require((0, 2270, 1900, 2320), 'chi co mot loai')
        columns, dates = [(800, 1010), (1330, 1540)], ['2026-06-30', '2025-12-31']
        rows = [('ISSUED_SHARES', 1870, 1910), ('TREASURY_SHARES', 1990, 2025),
                ('OUTSTANDING_SHARES', 2160, 2200)]
        scope, share_class, separator = 'issuer_self_held_treasury', 'ordinary', '.'
    elif sha == '53ec367048e5fc6b5e34620b3d1f9f08d2026309c37f847cbee9a10d573bfb58':
        expected = ('SSI', 2, '2026')
        require((0, 95, 630, 125), 'Previous Change After')
        require((0, 390, 800, 425), '15/6/2026.')
        require((630, 150, 800, 235), '18/8/2026)')
        require((0, 175, 320, 225), 'Total number of shares')
        require((0, 235, 320, 275), 'Number of treasury stock')
        require((0, 275, 320, 335), 'Number of outstanding voting shares')
        support = materialization.get('supporting_native_pages') or {}
        if ('SSI SECURITIES CORPORATION' not in support.get('1', '')
                or 'August 18th, 2026' not in support.get('1', '')
                or 'August 27th, 2026' not in support.get('3', '')):
            raise ValueError('ISSUER_NOTICE_DATE_BINDING_MISSING')
        columns, dates = [(320, 425), (530, 635)], ['2026-06-15', '2026-08-18']
        rows = [('CHARTER_CAPITAL', 140, 155), ('TOTAL_SHARES', 188, 200),
                ('TREASURY_SHARES', 235, 250), ('VOTING_SHARES', 295, 312)]
        scope, share_class, separator = 'issuer_notice', 'all_reported_classes', '.'
        if assurance is not None:
            raise ValueError('ISSUER_NOTICE_IS_NOT_AUDITOR_ASSURANCE')
    else:
        raise ValueError('CAPITAL_NOTE_LAYOUT_NOT_REVIEWED')
    if (issuer, page, document.get('reporting_period')) != expected:
        raise ValueError('CAPITAL_NOTE_ISSUER_PAGE_PERIOD_MISMATCH')
    if issuer != 'SSI' and not retained_assurance_is_bound(
            'audited' if issuer == 'PNJ' else 'reviewed', assurance, document_sha256=sha):
        raise ValueError('AUDITOR_EVIDENCE_NOT_QUALIFIED')
    claims = []

    def claim(kind, value, day, selected, *, state='DATED_OBSERVATION', consideration=None):
        citation = dict(pdf_page=page, selected_tokens=selected,
            rendered_image_sha256=materialization['rendered_image_sha256'])
        row = dict(ticker=issuer, kind=kind, state=state, subject=kind.lower(), value=value,
            unit='VND' if kind == 'CHARTER_CAPITAL' else 'shares', scope=scope,
            share_class=share_class, denominator_basis='EXPLICIT_'+kind,
            effective_date=day, consideration=consideration, source_owner='retained_common_share_note',
            source_identity=document['document_id'], source_locator=document['canonical_url'],
            source_page=page, document_sha256=sha, published_at=published,
            observed_at=document['observed_at'], knowledge_available_at=knowledge_available_at,
            qualification_state='QUALIFIED', field_qualification='QUALIFIED',
            coverage_kind='REAL_RETAINED_INPUT', historical_pit_eligible=False,
            assurance_evidence=assurance, source_citation=citation,
            limitations=['POINT_OBSERVATION_ONLY', 'LATER_CONTINUITY_UNKNOWN',
                         'NO_STRICT_VALUATION_OR_FACTOR_AUTHORITY', 'NO_HISTORICAL_PIT'])
        if kind == 'ISSUANCE':
            row.update(execution_evidence_qualified=True, event_id='SSI_BONUS_20260818',
                       issuance_end_date=day, effective_date_type='ISSUANCE_END')
        row['citation_id'] = stable_id(row)
        claims.append(row)

    for kind, y0, y1 in rows:
        for (x0, x1), day in zip(columns, dates):
            selected = region((x0, y0, x1, y1))
            if len(selected) != 1:
                raise ValueError('CAPITAL_NUMERIC_CELL_AMBIGUOUS')
            literal = selected[0]['text']
            # Parentheses denote a treasury subtraction, not negative shares.
            if kind == 'TREASURY_SHARES' and literal.startswith('(') and literal.endswith(')'):
                literal = literal[1:-1]
            if not re.fullmatch(r'[1-9][0-9]{0,2}(?:' + re.escape(separator) + r'[0-9]{3})+', literal):
                raise ValueError('CAPITAL_NUMERIC_CELL_AMBIGUOUS')
            claim(kind, int(literal.replace(separator, '')), day, selected)
    if issuer == 'SSI':
        require((630, 150, 800, 305), 'Completed the issuance of')
        require((630, 150, 800, 305), 'owner’s')
        selected = region((635, 160, 700, 175))
        if len(selected) != 1 or selected[0]['text'] != '500.204.581':
            raise ValueError('EXECUTED_ISSUANCE_QUANTITY_AMBIGUOUS')
        claim('ISSUANCE', 500204581, '2026-08-18', selected,
              state='EXECUTED', consideration='BONUS_FROM_EQUITY')
    note = dict(contract_version='retained_share_capital_note/v1', document=dict(document),
        materialization=dict(materialization), assurance=assurance,
        knowledge_available_at=knowledge_available_at, ticker=issuer, claims=claims)
    note['citation_id'] = stable_id(note)
    return note


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
