import hashlib

import pytest

from current_market_universe_breadth_foundation import _canonical_json, build_artifact


def qualification(records):
    artifact = {"records": records}
    built = hashlib.sha256(_canonical_json(artifact).encode()).hexdigest()
    artifact["artifact_sha256"] = built
    artifact["artifact_identity"] = f"qualification:{built}"
    return artifact


def test_membership_is_orthogonal_to_missing_incomplete_and_rejected_session_data():
    artifact = build_artifact(
        qualification_artifact=qualification({
            "AAA": {"instrument_class": "EQUITY", "listing_context": "UNKNOWN"},
            "BBB": {"instrument_class": "EQUITY", "listing_context": "UNKNOWN"},
            "CCC": {"instrument_class": "EQUITY", "listing_context": "UNKNOWN"},
            "DDD": {"instrument_class": "UNKNOWN", "listing_context": "UNKNOWN"},
        }),
        canonical_snapshot={"records": {
            "AAA": {"disposition": "EXACT_SESSION_RETAINED"},
            "BBB": {"disposition": "SESSION_MISSING"},
            "CCC": {"disposition": "PROVIDER_REJECTED"},
            "DDD": {"disposition": "PROVIDER_REJECTED"},
        }},
    )

    assert artifact["current_universe_membership"]["included_equity_candidate_count"] == 3
    assert artifact["records"]["BBB"]["membership_state"] == "INCLUDED"
    assert artifact["records"]["CCC"]["membership_state"] == "INCLUDED"
    assert artifact["records"]["DDD"]["membership_state"] == "UNKNOWN"
    assert artifact["observed_session_cohort"]["coverage_ratio"] == pytest.approx(1 / 3)
    assert artifact["session_observability"]["counts"]["INCOMPLETE"] == 0


def test_unclassified_session_disposition_is_explicitly_incomplete_and_identity_is_stable():
    inputs = {
        "qualification_artifact": qualification({"AAA": {"instrument_class": "EQUITY"}}),
        "canonical_snapshot": {"records": {"AAA": {"disposition": "MALFORMED"}}},
    }
    first = build_artifact(**inputs)
    second = build_artifact(**inputs)

    assert first["records"]["AAA"]["session_observation_state"] == "INCOMPLETE"
    assert first["records"]["AAA"]["membership_state"] == "INCLUDED"
    assert first["artifact_identity"] == second["artifact_identity"]


def test_non_equity_is_distinct_from_unknown_membership_and_session_observability():
    artifact = build_artifact(
        qualification_artifact=qualification({
            "AAA": {"instrument_class": "EQUITY"},
            "ETF1": {"instrument_class": "ETF"},
            "UNK": {"instrument_class": "UNKNOWN_SECURITY_GROUP"},
        }),
        canonical_snapshot={"records": {
            "AAA": {"disposition": "EXACT_SESSION_RETAINED"},
            "ETF1": {"disposition": "EXACT_SESSION_RETAINED"},
            "UNK": {"disposition": "SESSION_MISSING"},
        }},
    )

    assert artifact["records"]["ETF1"]["membership_state"] == "EXCLUDED"
    assert artifact["records"]["ETF1"]["breadth_screening_state"] == "NOT_APPLICABLE"
    assert artifact["records"]["UNK"]["membership_state"] == "UNKNOWN"
