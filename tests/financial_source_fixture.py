"""Synthetic retained-source IO for consumer tests; the real common admission still runs.

These bytes are test fixtures, never verification of the repository's retained issuer rows.
Adversarial callers mutate the returned row after the independent source is registered.
"""
from copy import deepcopy
import math

import pytest

from tests.test_official_financial_source_integrity import proved_fixture

_CONTEXTS = {}


def bind_fixture_source(template):
    row = deepcopy(template)
    period = row.get("reporting_period")
    period = period if period in {"2025", "2026-H1", "2026-Q2"} else "2026-H1"
    value = row.get("normalized_value", row.get("value", 123))
    value = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 123
    if "value" in row:
        row["value"] = value
    scale = row.get("source_unit_scale", 1)
    scale = scale if scale in (1, 1000, 1_000_000) and not isinstance(scale, bool) else 1
    if value % scale:
        scale = 1
        row["source_unit_scale"] = scale
    currency = row.get("currency") if row.get("currency") in {"VND", "USD"} else "VND"
    fixture, context = proved_fixture(period, ticker=row.get("ticker", "PNJ"),
        metric=row.get("canonical_metric", "revenue"), value=value, scale=scale, currency=currency,
        observed=row.get("observed_at") or "2026-10-07T00:00:00Z")
    row.update({key: deepcopy(fixture[key]) for key in ("document_sha256", "document_metadata", "assurance_evidence",
        "audit_or_review_status", "raw_value_text", "raw_row_label", "source_span", "citation_id")})
    row.setdefault("statement_family", fixture["statement_family"])
    row.setdefault("unit_scale", 1)
    row.setdefault("source_unit_scale", scale)
    row["source_locator"] = context["source_record"]["canonical_url"]
    row["source_family"] = "issuer_ir"
    if isinstance(row.get("reported_component_evidence"), dict):
        row["reported_component_evidence"]["citation_id"] = row["citation_id"]
    row["source_span"]["source_page"] = row.get("source_page", 1)
    context["document_pages"] = {row["source_span"]["source_page"]: context["document_pages"][1],
        1: context["document_pages"][1]}
    _CONTEXTS[row["document_sha256"]] = deepcopy(context)
    return row, deepcopy(context)


def install_synthetic_admission(monkeypatch):
    """Route retained-source IO to the registered synthetic contexts; admission itself is unchanged."""
    from official_financial_filing_evidence import admit_official_financial_fact
    from stocklookup_core.evidence import official_document_qualification as owner
    def replay(row, *, cutoff=None, intended_use="CURRENT_RESEARCH_FACTUAL_AUTHORITY", **_):
        context = deepcopy(_CONTEXTS.get(row.get("document_sha256"), {}))
        return admit_official_financial_fact(row, **context, cutoff=cutoff, intended_use=intended_use)
    monkeypatch.setattr(owner, "admit_retained_financial_fact", replay)


@pytest.fixture(autouse=True)
def synthetic_retained_source_io(monkeypatch):
    install_synthetic_admission(monkeypatch)
    yield
    _CONTEXTS.clear()
