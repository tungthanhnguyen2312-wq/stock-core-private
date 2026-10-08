"""Representation identity stays distinct from a repaired OCR token."""
from pathlib import Path

from official_financial_representation import (
    DISPOSITION, IMAGE_ONLY, NO_ALTERNATE, NORMALIZATION, RECOVERED,
    assess_target, compare_exposed_values, empirical_assessments, extraction_preference,
    filing_identity_decision, milestone_report, packet_provenance,
)
from source_faithful_numeric_glyph_normalization import normalization_decision

ROOT = Path(__file__).resolve().parents[1]


def _doc(**kwargs):
    base = {
        "issuer": "FPT", "reporting_period": "2025", "scope": "consolidated",
        "assurance": "audited", "statement_family": "income_statement",
        "official_source": True, "identity_proof": "OFFICIAL_LANGUAGE_COUNTERPART",
        "native_text_characters": 0, "sha256": "a" * 64,
        "representation_class": "PRIMARY_OFFICIAL_PDF_SCAN",
    }
    base.update(kwargs)
    return base


def test_same_filing_keeps_distinct_representation_identity():
    original = _doc(sha256="a" * 64)
    alternate = _doc(sha256="b" * 64, representation_class="OFFICIAL_PARALLEL_LANGUAGE_PDF")
    decision = filing_identity_decision(alternate, original)
    assert decision["same_filing"] is True
    assert decision["representation_identities_distinct"] is True
    assert decision["source_document_identity"]["issuer"] == "FPT"


def test_different_period_is_rejected():
    decision = filing_identity_decision(_doc(reporting_period="2024", sha256="b" * 64), _doc())
    assert decision["same_filing"] is False
    assert "DIFFERENT_PERIOD" in decision["reasons"]


def test_different_scope_is_rejected():
    decision = filing_identity_decision(_doc(scope="separate", sha256="b" * 64), _doc())
    assert decision["same_filing"] is False
    assert "DIFFERENT_SCOPE" in decision["reasons"]


def test_official_language_counterpart_needs_an_identity_proof():
    accepted = filing_identity_decision(
        _doc(sha256="b" * 64, representation_class="OFFICIAL_PARALLEL_LANGUAGE_PDF"), _doc())
    refused = filing_identity_decision(
        _doc(sha256="b" * 64, identity_proof="SAME_LOOKING_TOTAL"), _doc())
    assert accepted["same_filing"] is True
    assert refused["same_filing"] is False
    assert "IDENTITY_PROOF_ABSENT" in refused["reasons"]


def test_unofficial_mirror_is_rejected():
    decision = filing_identity_decision(_doc(official_source=False, sha256="b" * 64), _doc())
    assert decision["same_filing"] is False
    assert "UNOFFICIAL_MIRROR" in decision["reasons"]


def test_same_ocr_pixels_are_not_independent():
    original = _doc(pixel_sha256="p" * 64, ocr_engine="tesseract-5.5.0-vie+eng-psm6")
    twin = _doc(sha256="b" * 64, pixel_sha256="p" * 64, ocr_engine="tesseract-5.5.0-vie+eng-psm6",
                representation_class="OFFICIAL_PARALLEL_LANGUAGE_PDF")
    result = assess_target({"issuer": "FPT", "fact": "attributable_net_income", "reporting_period": "2025",
                             "original": original, "alternate": twin})
    assert result["independence"]["reason"] == "SAME_OCR_PIXELS"
    assert result["outcome"] != RECOVERED
    assert result["recovered_fact"] is None


def test_native_official_representation_can_supply_the_value():
    original = _doc(raw_token="9,376,1²7,6²9,501")
    alternate = _doc(sha256="b" * 64, representation_class="PRIMARY_OFFICIAL_PDF_NATIVE_TEXT",
                     native_text_characters=40)
    exposed = {"sign": 1, "magnitude": 100, "unit": "VND", "currency": "VND",
               "reporting_period": "2025", "scope": "consolidated"}
    result = assess_target({
        "issuer": "FPT", "fact": "attributable_net_income", "reporting_period": "2025",
        "original": original, "alternate": alternate, "alternate_exposed_value": exposed,
        "original_exposed_value": exposed,
    })
    assert result["outcome"] == RECOVERED
    assert result["recovered_fact"]["citation_sha256"] == "b" * 64
    assert result["recovered_fact"]["original_raw_token_not_used"] == "9,376,1²7,6²9,501"


def test_corrupted_scan_token_stays_raw_and_superscript_normalization_stays_blocked():
    source = (ROOT / "official_financial_representation.py").read_text(encoding="utf-8")
    assert 'replace("²"' not in source and "NFKC" not in source
    decision = normalization_decision({
        "raw_token": "9,376,1²7,6²9,501", "token_class": "NUMERIC_AMOUNT",
        "row_identity_qualified": True, "column_identity_qualified": True,
        "independent_confirmation": "PARALLEL_LANGUAGE_EXACT_IDENTITY",
    })
    assert decision["normalized_token"] is None and decision["admitted"] is False
    assert decision["raw_token"] == "9,376,1²7,6²9,501"
    assert decision["disposition"] == NORMALIZATION


def test_value_comparisons_are_explicit_and_a_conflict_has_no_winner():
    amount = {"sign": 1, "magnitude": 10, "unit": "VND", "currency": "VND",
              "reporting_period": "2025", "scope": "consolidated"}
    assert compare_exposed_values(amount, dict(amount))["classification"] == "EXACT_MATCH"
    scaled = dict(amount, magnitude=10_000, unit="thousand VND")
    assert compare_exposed_values(amount, scaled)["classification"] == "PRESENTATION_SCALE_DIFFERENCE"
    assert compare_exposed_values(amount, dict(amount, currency="USD"))["classification"] == "CURRENCY_PRESENTATION_DIFFERENCE"
    conflict = compare_exposed_values(amount, dict(amount, magnitude=11))
    assert conflict == {"classification": "TRUE_CONFLICT", "winner": None}


def test_conflict_is_not_qualified_from_either_representation():
    original = _doc(raw_token="1")
    alternate = _doc(sha256="b" * 64, representation_class="OFFICIAL_SPREADSHEET", native_text_characters=8)
    left = {"sign": 1, "magnitude": 10, "unit": "VND", "currency": "VND", "reporting_period": "2025", "scope": "consolidated"}
    result = assess_target({
        "issuer": "FPT", "fact": "cash_and_equivalents", "reporting_period": "2025",
        "original": original, "alternate": alternate,
        "original_exposed_value": left, "alternate_exposed_value": dict(left, magnitude=11),
    })
    assert result["outcome"] == "TRUE_CONFLICT_PRESERVED"
    assert result["recovered_fact"] is None


def test_preference_applies_only_to_an_explicit_same_filing_parseable_copy():
    scan = _doc(sha256="a" * 64)
    native = _doc(sha256="b" * 64, representation_class="PRIMARY_OFFICIAL_PDF_NATIVE_TEXT", native_text_characters=12)
    other_period = _doc(sha256="c" * 64, reporting_period="2024", representation_class="OFFICIAL_SPREADSHEET")
    assert extraction_preference([scan, native])["prefer"] == "b" * 64
    assert extraction_preference([scan, native])["authority_changed"] is False
    assert extraction_preference([scan, _doc(sha256="d" * 64, representation_class="OFFICIAL_PARALLEL_LANGUAGE_PDF")])["prefer"] is None
    assert extraction_preference([scan, other_period])["reason"] == "SAME_FILING_NOT_EXPLICIT"


def test_october_7_cutoff_excludes_the_later_assessment():
    report = milestone_report()
    assert report["october_7_records_changed"] is False
    assert all(item["excluded_from_completed_october_7"] for item in report["assessments"])
    assert report["knowledge_available_at"].startswith("2026-10-08")


def test_packet_provenance_cites_the_supplying_representation_only():
    original = _doc(raw_token="9,376,1²7,6²9,501")
    alternate = _doc(sha256="b" * 64, representation_class="OFFICIAL_HTML_STATEMENT")
    exposed = {"sign": 1, "magnitude": 5, "unit": "VND", "currency": "VND",
               "reporting_period": "2025", "scope": "consolidated"}
    recovered = assess_target({
        "issuer": "FPT", "fact": "attributable_net_income", "reporting_period": "2025",
        "original": original, "alternate": alternate, "alternate_exposed_value": exposed,
    })
    rows = packet_provenance(recovered)
    assert rows[0]["citation_sha256"] == "b" * 64
    assert rows[0]["valuation_authority"] == "NONE"
    assert rows[0]["share_continuity"] == "NOT_INFERRED"
    assert milestone_report()["packet_rows"] == []


def test_empirical_cohort_recovers_nothing_and_does_not_widen_authority():
    report = milestone_report()
    assert report["disposition"] == DISPOSITION
    assert report["alternate_official_representations_found"] == 3
    assert report["facts_recovered"] == 0
    assert report["strict_shares"] == 0 and report["strict_valuation"] == 0
    assert report["discovery_path_changed"] is False
    assert report["issuer_by_issuer_scan_extraction_continues"] is False
    outcomes = {item["issuer"]: item["outcome"] for item in empirical_assessments()}
    assert outcomes["FPT"] == IMAGE_ONLY
    assert outcomes["PNJ"] == IMAGE_ONLY
    assert outcomes["PVD"] == IMAGE_ONLY
    assert outcomes["HPG"] == NO_ALTERNATE
    assert outcomes["QNS"] == NO_ALTERNATE
    fpt = next(item for item in empirical_assessments() if item["issuer"] == "FPT")
    assert fpt["raw_token_preserved"] == "9,376,1²7,6²9,501"
    assert fpt["superscript_repair_applied"] is False
    assert fpt["share_continuity_inferred"] is False
    hpg = next(item for item in report["assessments"] if item["issuer"] == "HPG")
    assert hpg["share_continuity_inferred"] is False
