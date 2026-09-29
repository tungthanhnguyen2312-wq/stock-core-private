"""Literal period / currency / scale claims from retained official statement text.

Additive recognizer used by the currency-refresh path.  Annual Vietnamese
Circular-200 phrasing already handled by ``official_financial_pdf_page_evidence``
remains the default; this module only adds H1/Q2 2026 and unit-scale variants.
It never infers that a filing should exist merely because a period ended.
"""
from __future__ import annotations

import re
from typing import Any

ANNUAL = "annual"
INTERIM_H1 = "interim_h1"
INTERIM_Q2 = "quarterly_q2"

_ANNUAL_VI = re.compile(
    r"n[ăa]m t[àa]i ch[íi]nh k[ếe]t th[úu]c ng[àa]y\s+31\s+th[áa]ng\s+12\s+n[ăa]m\s+(20\d{2})",
    re.IGNORECASE,
)
_ANNUAL_EN = re.compile(
    r"(?:year|financial year|fiscal year)\s+ended\s+31\s+december\s+(20\d{2})",
    re.IGNORECASE,
)
_H1_VI = re.compile(
    r"(?:k[ỳy]\s+(?:k[ếe]\s+to[áa]n\s+)?(?:6|s[áa]u)\s+th[áa]ng|b[áa]n\s+ni[êe]n|gi[ữu]a\s+ni[êe]n\s+[đd][ộo])"
    r".{0,80}?30\s+th[áa]ng\s+6\s+n[ăa]m\s+(20\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_H1_EN = re.compile(
    r"(?:six[-\s]month|interim|half[-\s]year).{0,80}?30\s+june\s+(20\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_Q2_VI = re.compile(
    r"qu[ýy]\s*(?:2|II(?!I)|ii(?!i)).{0,60}?n[ăa]m\s+(20\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_Q2_VI_LOSSY = re.compile(
    r"quy\s*(?:2|II(?!I)|ii(?!i))\s*nam\s+(20\d{2})",
    re.IGNORECASE,
)
_H1_VI_LOSSY = re.compile(
    r"(?:30\s*thang\s*06\s*nam|30/06/|30-06-)(20\d{2})",
    re.IGNORECASE,
)
_Q2_EN = re.compile(
    r"(?:second quarter|quarter\s*2|q2).{0,40}?(20\d{2})",
    re.IGNORECASE | re.DOTALL,
)
_Q3_VI = re.compile(r"qu[ýy]\s*(?:3|III|iii).{0,40}?n[ăa]m\s+2026", re.IGNORECASE)
_Q3_EN = re.compile(r"(?:third quarter|quarter\s*3|q3).{0,40}?2026", re.IGNORECASE)

_SCALE_MILLION = re.compile(
    r"(?:[đd][ơo]n\s+v[ịi]\s+t[íi]nh\s*:\s*(?:tri[ệe]u\s+[đd][ồo]ng|1,000,000\s*vnd|million\s*vnd)"
    r"|unit\s*:\s*(?:vnd\s*million|million\s*dong))",
    re.IGNORECASE,
)
_SCALE_UNIT = re.compile(
    r"[đd][ơo]n\s+v[ịi]\s+t[íi]nh\s*:\s*(?:vnd|vn[đd]|[đd][ồo]ng)\b",
    re.IGNORECASE,
)
_CURRENCY_VND = re.compile(r"\b(?:vnd|vn[đd]|[đd][ồo]ng vi[ệe]t nam)\b", re.IGNORECASE)
_CONSOLIDATED_VI = re.compile(
    r"(?:h[ợo]p\s+nh[ấa]t|h[o0q]'?p\s*nhat|dn/hn)",
    re.IGNORECASE,
)
_STANDALONE_VI = re.compile(r"(?:ri[êe]ng\s+l[ẻe]|b[áa]o\s+c[áa]o\s+t[àa]i\s+ch[íi]nh\s+ri[êe]ng)", re.IGNORECASE)
_AUDITED = re.compile(r"(?:ki[ểe]m\s+to[áa]n\s+[đd][ộo]c\s+l[ậa]p|audited)", re.IGNORECASE)
_REVIEWED = re.compile(r"(?:so[áa]t\s+x[ée]t|reviewed)", re.IGNORECASE)


def recognize_statement_period(text: str) -> dict[str, Any]:
    blob = str(text or "")
    for pattern, period_fn, periodicity in (
        (_ANNUAL_VI, lambda m: m.group(1), ANNUAL),
        (_ANNUAL_EN, lambda m: m.group(1), ANNUAL),
        (_H1_VI, lambda m: f"{m.group(1)}-H1", INTERIM_H1),
        (_H1_EN, lambda m: f"{m.group(1)}-H1", INTERIM_H1),
        (_Q2_VI, lambda m: f"{m.group(1)}-Q2", INTERIM_Q2),
        (_Q2_VI_LOSSY, lambda m: f"{m.group(1)}-Q2", INTERIM_Q2),
        (_H1_VI_LOSSY, lambda m: f"{m.group(1)}-H1", INTERIM_H1),
        (_Q2_EN, lambda m: f"{m.group(1)}-Q2", INTERIM_Q2),
    ):
        found = pattern.search(blob)
        if found:
            return {
                "period": period_fn(found), "periodicity": periodicity,
                "status": "EXPLICIT", "evidence": found.group(0)[:240],
            }
    if _Q3_VI.search(blob) or _Q3_EN.search(blob):
        return {
            "period": None, "periodicity": None, "status": "OUT_OF_SCOPE_Q3_2026",
            "evidence": "Q3 2026 is out of scope for this milestone",
        }
    return {"period": None, "periodicity": None, "status": "UNKNOWN", "evidence": None}


def recognize_unit_scale(text: str) -> dict[str, Any]:
    blob = str(text or "")
    million = _SCALE_MILLION.search(blob)
    if million:
        return {"unit_scale": 1_000_000, "status": "EXPLICIT", "evidence": million.group(0)[:180]}
    unit = _SCALE_UNIT.search(blob)
    if unit:
        return {"unit_scale": 1, "status": "EXPLICIT", "evidence": unit.group(0)[:180]}
    # VAS statement pages often print column headers as "VND VND" without a
    # "Đơn vị tính" line once encoding is lossy; a literal VND header plus no
    # million marker is still an explicit unit-scale-1 claim.
    if re.search(r"\bVND\s+VND\b", blob) and not _SCALE_MILLION.search(blob):
        return {"unit_scale": 1, "status": "EXPLICIT", "evidence": "VND VND"}
    return {"unit_scale": None, "status": "UNKNOWN", "evidence": None}


def recognize_currency(text: str) -> dict[str, Any]:
    found = _CURRENCY_VND.search(str(text or ""))
    if found:
        return {"currency": "VND", "status": "EXPLICIT", "evidence": found.group(0)}
    return {"currency": None, "status": "UNKNOWN", "evidence": None}


def recognize_scope(text: str) -> dict[str, Any]:
    blob = str(text or "")
    if _CONSOLIDATED_VI.search(blob) or re.search(r"\bconsolidated\b", blob, re.IGNORECASE):
        return {"statement_scope": "consolidated", "status": "EXPLICIT"}
    if _STANDALONE_VI.search(blob) or re.search(r"\bstandalone\b|\bseparate\b", blob, re.IGNORECASE):
        return {"statement_scope": "standalone", "status": "EXPLICIT"}
    return {"statement_scope": None, "status": "UNKNOWN"}


def recognize_audit_or_review(text: str) -> dict[str, Any]:
    blob = str(text or "")
    if _AUDITED.search(blob):
        return {"audit_or_review_status": "audited", "status": "EXPLICIT"}
    if _REVIEWED.search(blob):
        return {"audit_or_review_status": "reviewed", "status": "EXPLICIT"}
    return {"audit_or_review_status": None, "status": "UNKNOWN"}


def period_bounds(period: str) -> tuple[str, str]:
    period = str(period)
    if period.isdigit() and len(period) == 4:
        return f"{period}-01-01", f"{period}-12-31"
    if period.endswith("-H1"):
        year = period[:4]
        return f"{year}-01-01", f"{year}-06-30"
    if period.endswith("-Q2"):
        year = period[:4]
        return f"{year}-04-01", f"{year}-06-30"
    if period.endswith("-Q1"):
        year = period[:4]
        return f"{year}-01-01", f"{year}-03-31"
    raise ValueError(f"unsupported_period:{period}")
