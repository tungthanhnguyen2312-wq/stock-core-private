from pathlib import Path

from retained_official_financial_pdf_scaleout import _layout, _path_classification, discover_pdf_bytes


def test_duplicate_pdf_sha_is_one_document_with_multiple_provenance_paths(tmp_path: Path):
    first, second = tmp_path / "one.pdf", tmp_path / "two.bin"
    first.write_bytes(b"%PDF-1.4\nidentical")
    second.write_bytes(b"%PDF-1.4\nidentical")
    grouped = discover_pdf_bytes(tmp_path)
    assert len(grouped) == 1
    assert len(next(iter(grouped.values()))) == 2


def test_nonfinancial_and_unknown_path_dispositions_are_explicit():
    assert _path_classification([Path("documents/HPG/corporate_action_notice/a.pdf")]) == "NOT_FINANCIAL_STATEMENT"
    assert _path_classification([Path("raw/reviewed_interim_financial_statements/a.pdf")]) == "METADATA_INSUFFICIENT"


def test_bank_and_securities_layouts_cannot_become_corporate_layouts():
    assert _layout("bank", "ELIGIBLE_NATIVE_TEXT") == "BANK_STATEMENT"
    assert _layout("securities", "ELIGIBLE_NATIVE_TEXT") == "SECURITIES_COMPANY_STATEMENT"
    assert _layout("corporate", "ELIGIBLE_NATIVE_TEXT") == "GENERAL_CORPORATE_STANDARD"
