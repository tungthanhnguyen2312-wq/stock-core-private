from __future__ import annotations

import vci_financial_statement_retention as retention


def test_period_metadata_preserves_vci_fields_without_inferring_duration():
    rows = [{"yearReport": 2026, "lengthReport": 2, "publicDate": "2026-08-01",
             "createDate": "2026-07-30", "updateDate": "2026-08-01", "ticker": "AAA"}]
    metadata = retention.period_metadata(rows, frequency="quarter")
    assert metadata["2026-Q2"]["lengthReport"] == 2
    assert retention.period_label(rows[0], frequency="quarter") == "2026-Q2"


def test_period_label_rejects_invalid_report_position_instead_of_guessing():
    assert retention.period_label({"yearReport": 2026, "lengthReport": 9}, frequency="quarter") is None
    assert retention.period_label({"yearReport": 2026, "lengthReport": 2}, frequency="year") == "2026"


def test_conflicting_metadata_is_preserved_as_conflict():
    rows = [{"yearReport": 2026, "lengthReport": 1, "publicDate": "2026-04-01"},
            {"yearReport": 2026, "lengthReport": 1, "publicDate": "2026-04-02"}]
    metadata = retention.period_metadata(rows, frequency="quarter")
    assert metadata["2026-Q1"]["metadata_conflict"] is True
