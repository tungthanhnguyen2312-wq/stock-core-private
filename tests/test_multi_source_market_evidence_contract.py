import pytest

from multi_source_market_evidence_contract import (
    DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD,
    DNSE_HEALTH_EXACT_AND_CORROBORATED,
    DNSE_HEALTH_EXACT_BUT_UNCORROBORATED,
    DNSE_HEALTH_MATERIAL_CONFLICT,
    MultiSourceEvidenceError,
    RESOLUTION_ALL_MISSING,
    RESOLUTION_CONFLICT,
    RESOLUTION_CORROBORATED,
    RESOLUTION_CORROBORATED_NON_DNSE,
    RESOLUTION_SINGLE_SOURCE,
    STATUS_EXACT_SESSION_OBSERVED,
    STATUS_MALFORMED,
    STATUS_NOT_APPLICABLE,
    STATUS_SESSION_MISSING,
    STATUS_SOURCE_REJECTED,
    STATUS_TRANSPORT_FAILED,
    build_source_observation,
    classify_dnse_provider_health,
    resolve_ticker,
    resolve_ticker_degraded_dnse,
)

SESSION = "2026-09-03"


def obs(source, status, *, native=None, unit_scale=None, ticker="HPG"):
    return build_source_observation(
        ticker=ticker, requested_session=SESSION, observed_session=SESSION if native else None,
        source=source, provider_interface="test", retrieved_at="2026-09-03T20:00:00+07:00",
        status=status, native=native, unit_scale=unit_scale,
    )


# ---- source observation normalization ----

def test_dnse_native_scale_is_identity():
    o = obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native={"open": 22.0, "high": 22.4, "low": 22.0, "close": 22.2, "volume": 100})
    assert o["unit_scale"] == 1
    assert o["normalized"] == {"open_vnd": 22.0, "high_vnd": 22.4, "low_vnd": 22.0, "close_vnd": 22.2, "volume": 100}


def test_vci_scale_multiplies_by_1000():
    o = obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native={"open": 22.0, "high": 22.4, "low": 22.0, "close": 22.2, "volume": 100})
    assert o["unit_scale"] == 1000
    assert o["normalized"] == {"open_vnd": 22000.0, "high_vnd": 22400.0, "low_vnd": 22000.0, "close_vnd": 22200.0, "volume": 100}


def test_kbs_scale_multiplies_by_1000():
    o = obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native={"open": 79.5, "high": 79.5, "low": 77.6, "close": 77.6, "volume": 917000})
    assert o["unit_scale"] == 1000
    assert o["normalized"]["close_vnd"] == 77600.0


def test_explicit_unit_scale_overrides_default():
    o = obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native={"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}, unit_scale=1)
    assert o["unit_scale"] == 1
    assert o["normalized"]["close_vnd"] == 1.0


def test_non_observed_status_has_no_normalized_block():
    o = obs("VCI", STATUS_SESSION_MISSING)
    assert o["normalized"] is None
    assert o["native"] is None


def test_observed_status_requires_complete_native_fields():
    with pytest.raises(MultiSourceEvidenceError):
        build_source_observation(
            ticker="HPG", requested_session=SESSION, observed_session=SESSION, source="VCI",
            provider_interface="test", retrieved_at="t", status=STATUS_EXACT_SESSION_OBSERVED,
            native={"open": 1, "high": 1, "low": 1},  # close/volume missing
        )


def test_unknown_status_rejected():
    with pytest.raises(MultiSourceEvidenceError):
        build_source_observation(
            ticker="HPG", requested_session=SESSION, observed_session=None, source="VCI",
            provider_interface="test", retrieved_at="t", status="NOT_A_REAL_STATUS",
        )


# ---- session exactness / source dispositions ----

@pytest.mark.parametrize("status", [
    STATUS_EXACT_SESSION_OBSERVED, STATUS_SESSION_MISSING, STATUS_SOURCE_REJECTED,
    STATUS_TRANSPORT_FAILED, STATUS_MALFORMED, STATUS_NOT_APPLICABLE,
])
def test_all_six_statuses_accepted(status):
    native = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} if status == STATUS_EXACT_SESSION_OBSERVED else None
    o = obs("VCI", status, native=native)
    assert o["status"] == status


# ---- resolution policy: missing ----

def test_no_observed_source_is_all_missing():
    result = resolve_ticker("HPG", [obs("DNSE", STATUS_SESSION_MISSING), obs("VCI", STATUS_SESSION_MISSING), obs("KBS", STATUS_TRANSPORT_FAILED)])
    assert result["resolution"] == RESOLUTION_ALL_MISSING
    assert result["resolved_source"] is None
    assert result["contributing_sources"] == ["DNSE", "VCI", "KBS"]


def test_not_applicable_stubs_alone_are_all_missing():
    result = resolve_ticker("HPG", [obs("VCI", STATUS_NOT_APPLICABLE), obs("KBS", STATUS_NOT_APPLICABLE)])
    assert result["resolution"] == RESOLUTION_ALL_MISSING


# ---- resolution policy: single source (the default/common case) ----

def test_single_observed_source_resolves_single_source():
    native = {"open": 22.0, "high": 22.4, "low": 22.0, "close": 22.2, "volume": 100}
    result = resolve_ticker("HPG", [
        obs("DNSE", STATUS_SESSION_MISSING),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=native),
        obs("KBS", STATUS_NOT_APPLICABLE),
    ])
    assert result["resolution"] == RESOLUTION_SINGLE_SOURCE
    assert result["resolved_source"] == "VCI"
    assert result["resolved_normalized"]["close_vnd"] == 22200.0
    assert result["cross_source_volume_comparability"] == "NOT_APPLICABLE_SINGLE_SOURCE"
    assert result["cross_source_conflict"] is False


# ---- resolution policy: cross-source agreement (corroborated) ----

def test_agreeing_vci_and_kbs_are_corroborated_with_volume_agree():
    native = {"open": 79.5, "high": 79.5, "low": 77.6, "close": 77.6, "volume": 917000}
    result = resolve_ticker("GMD", [
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=native, ticker="GMD"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=native, ticker="GMD"),
    ])
    assert result["resolution"] == RESOLUTION_CORROBORATED
    assert result["cross_source_conflict"] is False
    assert result["cross_source_volume_comparability"] == "AGREE"
    assert set(result["contributing_sources"]) == {"VCI", "KBS"}


def test_agreeing_prices_but_different_volume_within_family_is_corroborated_with_disagree_volume():
    a = {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000}
    b = {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 5000}
    result = resolve_ticker("X", [
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=a, ticker="X"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=b, ticker="X"),
    ])
    assert result["resolution"] == RESOLUTION_CORROBORATED
    assert result["cross_source_volume_comparability"] == "DISAGREE"


# ---- resolution policy: conflict, tie-break, tick tolerance ----

def test_real_empirical_dnse_vs_vci_mwg_divergence_is_conflict_dnse_wins_tiebreak():
    """Real 2026-09-03 qualification-probe values: DNSE and VCI agree on open/high but
    diverge on low/close by more than one HOSE tick, and volume differs ~30x."""
    dnse_native = {"open": 74, "high": 74.6, "low": 73.8, "close": 74.5, "volume": 80000}
    vci_native = {"open": 74.0, "high": 74.6, "low": 73.2, "close": 73.2, "volume": 2383900}
    result = resolve_ticker("MWG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="MWG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=vci_native, unit_scale=1000, ticker="MWG"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT
    assert result["resolved_source"] == "DNSE"  # tie-break per SOURCE_PREFERENCE_ORDER
    assert result["cross_source_conflict"] is True
    assert result["cross_source_volume_comparability"] == "NOT_ESTABLISHED"  # different provider families


def test_one_tick_price_difference_still_agrees():
    a = {"open": 100, "high": 100, "low": 100, "close": 100.0, "volume": 1000}
    b = {"open": 100, "high": 100, "low": 100, "close": 100.1, "volume": 1000}  # +100 VND = 1 tick at 100k
    result = resolve_ticker("X", [
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=a, ticker="X"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=b, ticker="X"),
    ])
    assert result["resolution"] == RESOLUTION_CORROBORATED


def test_three_tick_price_difference_conflicts():
    a = {"open": 100, "high": 100, "low": 100, "close": 100.0, "volume": 1000}
    b = {"open": 100, "high": 100, "low": 100, "close": 100.3, "volume": 1000}  # +300 VND = 3 ticks at 100k
    result = resolve_ticker("X", [
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=a, ticker="X"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=b, ticker="X"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT


def test_vci_preferred_over_kbs_on_tie_break_when_dnse_absent():
    a = {"open": 100, "high": 100, "low": 100, "close": 100.0, "volume": 1000}
    b = {"open": 100, "high": 100, "low": 100, "close": 105.0, "volume": 1000}  # genuine conflict
    result = resolve_ticker("X", [
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=a, ticker="X"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=b, ticker="X"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT
    assert result["resolved_source"] == "VCI"


def test_resolve_ticker_never_mutates_input():
    native = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    observations = [obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=native)]
    snapshot_before = [dict(o) for o in observations]
    resolve_ticker("HPG", observations)
    assert observations == snapshot_before


# ---- resolution policy: DNSE conflicts with a corroborated VCI==KBS pair ----
# (this milestone's own correction: session-date equality alone never proves DNSE's bar is
# right; a genuinely corroborated non-DNSE pair must override DNSE's tie-break priority)

def test_dnse_conflicts_with_corroborated_vci_and_kbs_resolves_non_dnse_current_research():
    """Real 2026-09-03 empirical shape (GMD): DNSE has an exact-session bar for the target
    date, open/high approximately match VCI/KBS, but low/close materially diverge (>1 HOSE
    tick) and volume differs by orders of magnitude. VCI and KBS -- independently observed --
    materially agree with each other. Expected: no silent DNSE preference; SOURCE_CONFLICT-
    grade disagreement is retained via cross_source_conflict; the resolved Current Research
    basis is the corroborated non-DNSE pair, explicitly labeled (never RAW_AS_TRADED, never
    PIT); DNSE's own observation is never dropped."""
    dnse_native = {"open": 79.5, "high": 79.5, "low": 79.0, "close": 79.2, "volume": 20800}
    vci_native = {"open": 79.5, "high": 79.5, "low": 77.6, "close": 77.6, "volume": 917000}
    kbs_native = {"open": 79.5, "high": 79.5, "low": 77.6, "close": 77.6, "volume": 917000}
    observations = [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="GMD"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=vci_native, unit_scale=1000, ticker="GMD"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=kbs_native, unit_scale=1000, ticker="GMD"),
    ]
    result = resolve_ticker("GMD", observations)

    assert result["resolution"] == RESOLUTION_CORROBORATED_NON_DNSE
    assert result["resolved_source"] != "DNSE"
    assert result["resolved_source"] == "VCI"  # VCI ahead of KBS per SOURCE_PREFERENCE_ORDER
    assert result["resolved_normalized"]["close_vnd"] == 77600.0
    assert result["cross_source_conflict"] is True  # never silently absorbed
    assert set(result["contributing_sources"]) == {"DNSE", "VCI", "KBS"}

    dnse_ob = next(o for o in observations if o["source"] == "DNSE")
    assert dnse_ob["normalized"]["close_vnd"] == 79.2  # DNSE's own observation never erased

    vci_ob = next(o for o in observations if o["source"] == "VCI")
    assert vci_ob["price_basis"] == "CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED"
    assert vci_ob["fitness"] == "CURRENT_RESEARCH_DESCRIPTIVE_ONLY"


def test_dnse_vs_uncorroborated_conflict_still_stays_plain_conflict():
    """Only DNSE+VCI observed (no KBS) and they disagree: there is no independent pair to
    corroborate against DNSE, so this must stay the plain (pre-existing) SOURCE_CONFLICT
    tie-break, never RESOLUTION_CORROBORATED_NON_DNSE."""
    dnse_native = {"open": 74, "high": 74.6, "low": 73.8, "close": 74.5, "volume": 80000}
    vci_native = {"open": 74.0, "high": 74.6, "low": 73.2, "close": 73.2, "volume": 2383900}
    result = resolve_ticker("MWG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="MWG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=vci_native, unit_scale=1000, ticker="MWG"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT
    assert result["resolved_source"] == "DNSE"


def test_dnse_vs_vci_and_kbs_that_disagree_with_each_other_stays_plain_conflict():
    """DNSE, VCI, and KBS all observed, but VCI and KBS do NOT agree with each other either --
    there is no clean corroborated pair, so this stays plain SOURCE_CONFLICT with the existing
    tie-break, never a non-DNSE override built on a disagreement that isn't actually there."""
    dnse_native = {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100}
    vci_native = {"open": 10, "high": 10, "low": 8, "close": 8, "volume": 900}
    kbs_native = {"open": 10, "high": 10, "low": 6, "close": 6, "volume": 900}
    result = resolve_ticker("X", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="X"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=vci_native, unit_scale=1, ticker="X"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=kbs_native, unit_scale=1, ticker="X"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT
    assert result["resolved_source"] == "DNSE"


# ---- DNSE same-date provider-health classification (bounded sentinel cohort) ----

def test_dnse_health_all_corroborated_is_healthy():
    native = {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100}
    sentinel = {"AAA": [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=native, unit_scale=1, ticker="AAA"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=native, unit_scale=1, ticker="AAA"),
    ]}
    health = classify_dnse_provider_health(sentinel)
    assert health["state"] == DNSE_HEALTH_EXACT_AND_CORROBORATED
    assert health["conflict_count"] == 0
    assert health["corroborated_count"] == 1


def test_dnse_health_no_corroboration_available_is_uncorroborated():
    native = {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100}
    sentinel = {"AAA": [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=native, unit_scale=1, ticker="AAA"),
        obs("VCI", STATUS_TRANSPORT_FAILED, ticker="AAA"),
        obs("KBS", STATUS_TRANSPORT_FAILED, ticker="AAA"),
    ]}
    health = classify_dnse_provider_health(sentinel)
    assert health["state"] == DNSE_HEALTH_EXACT_BUT_UNCORROBORATED
    assert health["dnse_assessed_count"] == 0
    assert health["uncorroborated_count"] == 1


def test_dnse_health_isolated_conflict_never_trips_broad_by_itself():
    """A single conflicting ticker is 100% by ratio but must never be classified as
    provider-wide/systemic on its own -- exactly this milestone's own real MWG/GMD shape:
    a couple of isolated names, not a broad DNSE failure."""
    dnse_native = {"open": 79.5, "high": 79.5, "low": 79.0, "close": 79.2, "volume": 20800}
    other_native = {"open": 79.5, "high": 79.5, "low": 77.6, "close": 77.6, "volume": 917000}
    sentinel = {"GMD": [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="GMD"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=other_native, unit_scale=1, ticker="GMD"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=other_native, unit_scale=1, ticker="GMD"),
    ]}
    health = classify_dnse_provider_health(sentinel)
    assert health["state"] == DNSE_HEALTH_MATERIAL_CONFLICT
    assert health["conflict_count"] == 1
    assert health["dnse_assessed_count"] == 1


def test_dnse_health_majority_conflict_at_sufficient_sample_is_broad_stale_or_incomplete():
    dnse_native = {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 100}
    other_native = {"open": 10, "high": 10, "low": 8, "close": 8, "volume": 9000}
    sentinel = {}
    for i in range(4):
        ticker = f"C{i}"
        sentinel[ticker] = [
            obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker=ticker),
            obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=other_native, unit_scale=1, ticker=ticker),
            obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=other_native, unit_scale=1, ticker=ticker),
        ]
    sentinel["D0"] = [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="D0"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="D0"),
    ]
    health = classify_dnse_provider_health(sentinel)
    assert health["dnse_assessed_count"] == 5
    assert health["conflict_count"] == 4
    assert health["state"] == DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD


def test_dnse_health_ticker_dnse_did_not_resolve_is_excluded_from_assessment():
    """A DNSE-missing ticker is a coverage gap, not a DNSE quality question -- must never count
    toward assessed/conflict/corroborated/uncorroborated."""
    sentinel = {"AAA": [obs("DNSE", STATUS_SESSION_MISSING, ticker="AAA")]}
    health = classify_dnse_provider_health(sentinel)
    assert health["dnse_assessed_count"] == 0
    assert health["uncorroborated_count"] == 0
    assert health["per_ticker_resolution"] == {}


# ---- resolve_ticker_degraded_dnse: P0 DEFECT B (DNSE quarantined once broadly degraded) ----
# DAILY_GOVERNED_PREVIOUS_SESSION_AND_DEGRADED_SOURCE_FINAL_HARDENING_V1. DNSE's own value is
# NEVER a resolution candidate here -- these tests deliberately construct DNSE observations that
# would win under plain resolve_ticker's tie-break (agreeing with, or preferred over, a lone
# secondary) to prove the quarantine actually changes the outcome, not merely that it doesn't
# regress an already-non-DNSE case.

_DNSE_NATIVE = {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1000}
_SECONDARY_NATIVE_A = {"open": 8000.0, "high": 8000.0, "low": 8000.0, "close": 8000.0, "volume": 500000}
_SECONDARY_NATIVE_B = {"open": 9000.0, "high": 9000.0, "low": 9000.0, "close": 9000.0, "volume": 700000}


def test_degraded_vci_kbs_agree_resolves_non_dnse_even_when_dnse_also_agrees():
    """Required regression 4: VCI+KBS corroborate -> non-DNSE result, even when DNSE's own value
    would ALSO have agreed (passive agreement is not evidence DNSE is trustworthy this session --
    plain resolve_ticker would pick DNSE by tie-break here since nothing conflicts)."""
    dnse_native = dict(_SECONDARY_NATIVE_A, open=8000.0, high=8000.0, low=8000.0, close=8000.0)
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=dnse_native, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_CORROBORATED_NON_DNSE
    assert result["resolved_source"] == "VCI"
    assert result["resolved_under_quarantine"] is True
    assert "DNSE" in result["contributing_sources"]  # retained as evidence, never dropped


def test_degraded_vci_kbs_agree_resolves_non_dnse_when_dnse_conflicts():
    """Same rule, the more obvious direction: DNSE materially conflicts with a corroborated
    VCI==KBS pair."""
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_CORROBORATED_NON_DNSE
    assert result["resolved_source"] == "VCI"


def test_degraded_vci_only_resolves_single_source_vci_never_dnse():
    """Required regression 5: exactly one usable secondary (VCI) -> single-source VCI Current
    Research; DNSE retained as evidence but never the winner, even though plain resolve_ticker
    would pick DNSE here (2 observed, no conflict -> RESOLUTION_CORROBORATED, DNSE preferred)."""
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
        obs("KBS", STATUS_SESSION_MISSING, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_SINGLE_SOURCE
    assert result["resolved_source"] == "VCI"
    assert result["resolved_under_quarantine"] is True
    assert "DNSE" in result["contributing_sources"]


def test_degraded_kbs_only_resolves_single_source_kbs_never_dnse():
    """Required regression 6: same semantics with KBS as the sole usable secondary."""
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_TRANSPORT_FAILED, ticker="HPG"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_SINGLE_SOURCE
    assert result["resolved_source"] == "KBS"
    assert result["resolved_under_quarantine"] is True


def test_degraded_vci_kbs_conflict_is_unresolved_never_tiebroken_to_either():
    """Required regression 7: VCI and KBS themselves materially conflict -> SOURCE_CONFLICT,
    resolved_source/resolved_normalized both None -- never tie-broken to VCI, KBS, or DNSE."""
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
        obs("KBS", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_B, unit_scale=1, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_CONFLICT
    assert result["resolved_source"] is None
    assert result["resolved_normalized"] is None
    assert result["cross_source_conflict"] is True
    assert result["resolved_under_quarantine"] is True


def test_degraded_no_secondary_is_unresolved_all_sources_missing_despite_dnse_value():
    """Required regression 8: no usable secondary exact source -> SESSION_MISSING_ALL_SOURCES,
    unresolved -- DNSE having a same-dated bar counts for nothing once quarantined."""
    result = resolve_ticker_degraded_dnse("HPG", [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_SESSION_MISSING, ticker="HPG"),
        obs("KBS", STATUS_TRANSPORT_FAILED, ticker="HPG"),
    ])
    assert result["resolution"] == RESOLUTION_ALL_MISSING
    assert result["resolved_source"] is None
    assert result["resolved_under_quarantine"] is True
    assert "DNSE" in result["contributing_sources"]


def test_degraded_never_mutates_input():
    observations = [
        obs("DNSE", STATUS_EXACT_SESSION_OBSERVED, native=_DNSE_NATIVE, unit_scale=1, ticker="HPG"),
        obs("VCI", STATUS_EXACT_SESSION_OBSERVED, native=_SECONDARY_NATIVE_A, unit_scale=1, ticker="HPG"),
    ]
    snapshot_before = [dict(o) for o in observations]
    resolve_ticker_degraded_dnse("HPG", observations)
    assert observations == snapshot_before
