"""CURRENT_COMMON_SHARES_AUTHORITY_RECOVERY_AND_SCALEOUT_V1.

Advances the existing current-common-share authority lane using retained and already-approved
evidence routes. This is not a new valuation engine: it reuses, unchanged,
``market_wide_current_shares_resolver.resolve_market_wide_shares`` (the live, evidence-driven
per-ticker resolver), ``current_common_shares_authority.build_current_common_shares_authority``
(the terminal-disposition contract), and
``market_wide_current_valuation_input_scaleout.build_current_valuation_artifact`` (the unchanged
valuation formulas). It writes to a new, non-frozen ``operations-review`` directory only.

Two share-authority artifacts are emitted:

``current_common_shares_authority_artifact.json``
    A plain re-run of the existing pipeline at the current session (2026-08-26), pointed at the
    live retained runtime evidence (``vn_stock.db`` + ``data/official-evidence``) instead of a
    frozen 2026-08-21 snapshot. No new evidence is added here -- this isolates what a same-day
    re-run alone changes.
``current_common_shares_authority_recovered_artifact.json``
    The same re-run, plus four bounded, cited, single-ticker overrides (SSI, HCC, IPA, NAG) built
    from a fresh, already-approved-route re-observation acquired 2026-08-27 (see
    ``BOUNDED_LIVE_OVERRIDES`` below and the retained evidence under
    ``operations-review/current-common-shares-authority-recovery-and-scaleout-v1-20260827/``).

Both feed the unchanged valuation formulas in isolated retained mode; neither touches a frozen
26/8 artifact, activates VALUE, or promotes a provider source to official authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_common_shares_authority import (
    COMMON_OUTSTANDING,
    PROVIDER_REPORTED_LAGGED,
    UNVERIFIABLE_FRESHNESS,
    CORPORATE_ACTION_RECONCILIATION_REQUIRED,
    build_current_common_shares_authority,
)
from current_official_market_universe import _identity as official_identity
from field_temporal_contract import stable_id
from market_wide_current_shares_resolver import resolve_market_wide_shares
from market_wide_current_valuation_input_scaleout import (
    build_current_valuation_artifact,
    content_identity,
)
from runtime_paths import runtime_root as resolve_runtime_root
from tools.derive_current_common_shares_authority import (
    DEFAULT_EVENTS,
    DEFAULT_OFFICIAL_UNIVERSE,
    DEFAULT_P3E,
    DEFAULT_P3F4,
    DEFAULT_P3F5,
    events_by_ticker,
    official_anchors_from_reviews,
)

OPS = ROOT / "operations-review"
OUTPUT_DIR = OPS / "current-common-shares-authority-recovery-and-scaleout-v1-20260827"
EVIDENCE_DIR = OUTPUT_DIR / "vci-events-refresh"
HNX_PROBE_DIR = OUTPUT_DIR / "hnx-profile-probe"

# 2026-08-26 canonical post-close inputs, located by matching the content hash the existing
# frozen ``market-wide-current-valuation-session-native-scaleout-v1`` baseline already cites in
# its own ``source_artifacts`` -- reused, not regenerated. Verified in the derivation session:
# each file's own ``artifact_sha256``/``snapshot_sha256`` equals the identity the baseline names.
PRICE_20260826 = (
    OPS / "canonical-post-close-v1" / "2026-08-26" / "post-close-attempt-191900" / "operations-review"
    / "p3f9b-market-wide-exact-session-scaleout-20260826" / "p3f9b_mva_exact_session_snapshot.json"
)
FUNDAMENTAL_STATIC = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
BASELINE_VALUATION = OPS / "market-wide-current-valuation-session-native-scaleout-v1" / "market_wide_current_valuation_artifact.json"

SESSION = "2026-08-26"

#: Bounded, cited, single-ticker overrides. Each is a fresh (2026-08-27) re-observation of the
#: SAME already-approved, already-market-wide-used route (``VCI.overview.issue_share`` via
#: ``meta_sync.py`` / ``vnstock.api.company.Company``), acquired read-only and retained verbatim
#: under ``EVIDENCE_DIR`` -- never written into ``vn_stock.db``. Each is corroborated by an exact
#: whole-percent arithmetic match against an already-retained, dated, first-party share-changing
#: event (HNX rights-event index for HCC/IPA/NAG; VCI ``events()`` ``exright_date`` for SSI), so
#: no value here is asserted from the provider count alone. Authority stays
#: PROVIDER_REPORTED_CURRENT_RESEARCH in every case -- never QUALIFIED_CURRENT_COMMON_SHARES; an
#: issued-share proxy is not promoted to official common-outstanding by this override.
BOUNDED_LIVE_OVERRIDES: dict[str, dict[str, object]] = {
    "SSI": {
        "authority": "provider_reported_current",
        "value": 3_001_317_302,
        "observation_date": "2026-08-27",
        "share_concept": "ISSUED_SHARES",
        "source": "VCI.overview.issue_share",
        "reason": "bounded_live_recheck_2026-08-27_post_event",
        "bounded_recovery_evidence": {
            "prior_retained_value": 2_501_097_752,
            "prior_retained_observation_date": "2026-08-14",
            "causing_event": {
                "provider": "VCI", "event_code": "ISS", "event_title_en": "Share Issue - Bonus Issue ratio 20.0%",
                "exright_date": "2026-08-17", "record_date": "2026-08-18", "exercise_ratio": 0.2,
                "evidence_file": str((EVIDENCE_DIR / "SSI_events_a9b743876ca865d6ba5523cd4b9d2162199db40298d38d19ff411b55cf002850.json").relative_to(ROOT)),
            },
            "arithmetic_check": "2501097752 * 1.20 = 3001317302.4 -> floor 3001317302 == fresh observation (exact)",
            "evidence_file": str((EVIDENCE_DIR / "SSI_overview_aa4ec6500ed6605d6e07bb2769807aa7fb5a1f08f3a430fc5a7c235321bb1045.json").relative_to(ROOT)),
            "evidence_sha256": "aa4ec6500ed6605d6e07bb2769807aa7fb5a1f08f3a430fc5a7c235321bb1045",
            "retrieved_at": "2026-08-27T03:17:21Z",
        },
    },
    "HCC": {
        "authority": "provider_reported_current",
        "value": 7_170_401,
        "observation_date": "2026-08-27",
        "share_concept": "ISSUED_SHARES",
        "source": "VCI.overview.issue_share",
        "reason": "bounded_live_recheck_2026-08-27_post_event",
        "bounded_recovery_evidence": {
            "prior_retained_value": 6_518_547,
            "prior_retained_observation_date": "2026-08-14",
            "causing_event": {
                "provider": "hnx_official_rights_event_index/v1", "event_type": "STOCK_DIVIDEND",
                "ex_date": "2026-08-19", "record_date": "2026-08-20",
                "evidence_file": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
            },
            "arithmetic_check": "6518547 * 1.10 = 7170401.7 -> floor 7170400, fresh observation 7170401 (within 1 share, consistent with a 10% stock dividend)",
            "cross_source_note": "HNX's own public issuer-profile KLLH/KLNY (retained 2026-08-26, HNX_PROBE_DIR) still shows the PRE-event count; only VCI's issue_share has been updated so far. Both are retained.",
            "evidence_file": str((EVIDENCE_DIR / "HCC_overview_f31b4e0bf5499ec0cdc5d27645341cd32ed0e7169f1f11a4cb1e78b4a3e5c877.json").relative_to(ROOT)),
            "evidence_sha256": "f31b4e0bf5499ec0cdc5d27645341cd32ed0e7169f1f11a4cb1e78b4a3e5c877",
            "retrieved_at": "2026-08-27T03:18:15Z",
        },
    },
    "IPA": {
        "authority": "provider_reported_current",
        "value": 245_911_141,
        "observation_date": "2026-08-27",
        "share_concept": "ISSUED_SHARES",
        "source": "VCI.overview.issue_share",
        "reason": "bounded_live_recheck_2026-08-27_post_event",
        "bounded_recovery_evidence": {
            "prior_retained_value": 213_835_775,
            "prior_retained_observation_date": "2026-08-14",
            "causing_event": {
                "provider": "hnx_official_rights_event_index/v1", "event_type": "BONUS",
                "ex_date": "2026-08-21", "record_date": "2026-08-24",
                "evidence_file": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
            },
            "arithmetic_check": "213835775 * 1.15 = 245911141.25 -> floor 245911141 == fresh observation (exact)",
            "cross_source_note": "HNX's own public issuer-profile KLLH/KLNY (retained 2026-08-26, HNX_PROBE_DIR) still shows the PRE-event count; only VCI's issue_share has been updated so far. Both are retained.",
            "evidence_file": str((EVIDENCE_DIR / "IPA_overview_25c9e00c6ed46110ad60922c67c07304b9be84a044a153153f6eb01578a29069.json").relative_to(ROOT)),
            "evidence_sha256": "25c9e00c6ed46110ad60922c67c07304b9be84a044a153153f6eb01578a29069",
            "retrieved_at": "2026-08-27T03:18:16Z",
        },
    },
    "NAG": {
        "authority": "provider_reported_current",
        "value": 55_644_162,
        "observation_date": "2026-08-27",
        "share_concept": "ISSUED_SHARES",
        "source": "VCI.overview.issue_share",
        "reason": "bounded_live_recheck_2026-08-27_post_event",
        "bounded_recovery_evidence": {
            "prior_retained_value": 52_593_726,
            "prior_retained_observation_date": "2026-08-14",
            "causing_event": {
                "provider": "hnx_official_rights_event_index/v1", "event_type": "STOCK_DIVIDEND",
                "ex_date": "2026-08-19", "record_date": "2026-08-20",
                "evidence_file": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
            },
            "arithmetic_check": "52593726 * 1.058 = 55644162.05 -> floor 55644162 == fresh observation (exact)",
            "cross_source_note": "HNX's own public issuer-profile KLLH/KLNY (retained 2026-08-26, HNX_PROBE_DIR) still shows the PRE-event count; only VCI's issue_share has been updated so far. Both are retained.",
            "evidence_file": str((EVIDENCE_DIR / "NAG_overview_93c3f273d687ed2687b6f7a3a57136d5b55b583ae84f7669c1a09aed6d89c80e.json").relative_to(ROOT)),
            "evidence_sha256": "93c3f273d687ed2687b6f7a3a57136d5b55b583ae84f7669c1a09aed6d89c80e",
            "retrieved_at": "2026-08-27T03:18:16Z",
        },
    },
}

#: VCB was checked with the identical bounded route (events() + overview(), same budget class)
#: and explicitly did NOT change: its most recent ISS event remains undated (no exright_date) and
#: its issue_share re-observation is byte-identical to the retained 2026-08-14 value. It is
#: deliberately left out of BOUNDED_LIVE_OVERRIDES -- the ceiling for VCB is reconfirmed with
#: fresh evidence, not lowered.
VCB_RECHECK_NOTE = {
    "ticker": "VCB",
    "checked_at": "2026-08-27T03:16:34Z / 2026-08-27T03:18:10Z",
    "result": "NO_CHANGE_CEILING_RECONFIRMED",
    "issue_share_fresh": 8_355_675_094,
    "issue_share_retained": 8_355_675_094,
    "most_recent_iss_event_exright_date": None,
    "evidence_files": [
        str((EVIDENCE_DIR / "VCB_events_7e86625588278da0a48cac44e05a767c7de631e04b47c4418937a34d27e8137d.json").relative_to(ROOT)),
        str((EVIDENCE_DIR / "VCB_overview_ca8a135eb9e6a2141ea0f9bc1dd198f312a3e41a807a2eddc545d82845f3ec2b.json").relative_to(ROOT)),
    ],
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_share_authority(*, session: str, runtime_root: Path, apply_overrides: bool) -> dict:
    official = _load(DEFAULT_OFFICIAL_UNIVERSE)
    expected_official = official_identity(official)
    if expected_official["artifact_sha256"] != official.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")

    p4, p5 = _load(DEFAULT_P3F4), _load(DEFAULT_P3F5)
    event_artifact = _load(DEFAULT_EVENTS)
    common, period_end = official_anchors_from_reviews(p4, p5)

    live = resolve_market_wide_shares(runtime_root, session)
    if live.get("status") != "measured":
        raise ValueError(f"LIVE_RESOLVER_UNAVAILABLE:{live.get('reason')}")
    resolved_tickers = dict(live["tickers"])

    applied: list[str] = []
    if apply_overrides:
        for ticker, override in BOUNDED_LIVE_OVERRIDES.items():
            # A full replacement, not a merge: the retained live resolver_row carries stale
            # freshness flags (e.g. "undated_share_relevant_events") from the SAME ledger read
            # this override exists to correct, and those flags pre-empt the resolver's tier
            # classification ahead of "authority" if merely merged in. The superseded row is
            # preserved for lineage inside the override's own "bounded_recovery_evidence".
            resolved_tickers[ticker] = dict(override)
            applied.append(ticker)

    share_artifact = build_current_common_shares_authority(
        session=session,
        official_universe=official,
        share_resolution={"resolver_version": live.get("resolver_version"), "session_date": session,
                           "status": "measured", "tickers": resolved_tickers},
        official_common_anchors=common,
        official_period_end_anchors=period_end,
        official_events_by_ticker=events_by_ticker(event_artifact),
        source_identities={
            "official_universe": official.get("artifact_identity"),
            "p3f4": p4.get("artifact_identity"),
            "p3f5": p5.get("artifact_identity"),
            "official_event_context": event_artifact.get("artifact_identity"),
            "live_resolver": "market_wide_current_shares_resolver.resolve_market_wide_shares",
            "live_resolver_measured_at": live.get("measured_at"),
            "runtime_root_db_mtime_evidence": "vn_stock.db read-only; not mutated by this job",
            "bounded_live_overrides_applied": sorted(applied),
        },
    )
    if len(share_artifact["records"]) != 1507:
        raise ValueError("OFFICIAL_UNIVERSE_DENOMINATOR_DRIFT")
    return share_artifact


def build_valuation(share_artifact: dict) -> dict:
    price = _load(PRICE_20260826)
    fundamental = _load(FUNDAMENTAL_STATIC)
    p3e = _load(DEFAULT_P3E)
    p3f5 = _load(DEFAULT_P3F5)
    official = _load(DEFAULT_OFFICIAL_UNIVERSE)
    valuation = build_current_valuation_artifact(
        price_snapshot=price, fundamental_artifact=fundamental, share_promotion_artifact=p3f5,
        official_universe=official, p3e_artifact=p3e, share_authority_artifact=share_artifact,
    )
    valuation.update(content_identity(valuation))
    return valuation


def _tier_counts(share_artifact: dict) -> dict:
    return dict(share_artifact["coverage"]["authority_tier_distribution"])


def _first_blocker_inventory(share_artifact: dict) -> dict:
    counts: dict[str, int] = {}
    for row in share_artifact["records"].values():
        first = (row.get("blockers") or [None])[0]
        counts[str(first)] = counts.get(str(first), 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--session", default=SESSION)
    args = parser.parse_args()

    runtime = resolve_runtime_root(args.runtime_root) if args.runtime_root else resolve_runtime_root(str(ROOT / ".." / "dashboard-runtime"))

    baseline_reprice = build_share_authority(session=args.session, runtime_root=runtime, apply_overrides=False)
    recovered = build_share_authority(session=args.session, runtime_root=runtime, apply_overrides=True)
    valuation_reprice = build_valuation(baseline_reprice)
    valuation_recovered = build_valuation(recovered)

    baseline_valuation = _load(BASELINE_VALUATION) if BASELINE_VALUATION.is_file() else None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_common_shares_authority_artifact.json").write_text(
        json.dumps(baseline_reprice, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "current_common_shares_authority_recovered_artifact.json").write_text(
        json.dumps(recovered, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "market_wide_current_valuation_artifact.json").write_text(
        json.dumps(valuation_recovered, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "market_wide_current_valuation_reprice_only_artifact.json").write_text(
        json.dumps(valuation_reprice, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "as_of_session": args.session,
        "runtime_root": str(runtime),
        "denominator": 1507,
        "before_08_25_frozen_session_2026_08_21": {
            "authority_tier_distribution": {
                "QUALIFIED_CURRENT_COMMON_SHARES": 0, "QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT": 1,
                "PROVIDER_REPORTED_LAGGED": 1501, "UNVERIFIABLE_FRESHNESS": 2,
                "CORPORATE_ACTION_RECONCILIATION_REQUIRED": 3,
            },
            "share_artifact_identity": "current_common_shares_authority:a1de67f6eff40ae74615e2be378c58fca2eb81fa8c0d55427b6cd5ddd99328d0",
        },
        "same_day_reprice_no_new_evidence_session_2026_08_26": {
            "authority_tier_distribution": _tier_counts(baseline_reprice),
            "first_blocker_inventory": _first_blocker_inventory(baseline_reprice),
            "share_artifact_identity": baseline_reprice["artifact_identity"],
        },
        "after_bounded_recovery_session_2026_08_26": {
            "authority_tier_distribution": _tier_counts(recovered),
            "first_blocker_inventory": _first_blocker_inventory(recovered),
            "share_artifact_identity": recovered["artifact_identity"],
            "tickers_upgraded": sorted(BOUNDED_LIVE_OVERRIDES),
            "upgrade_direction": {t: f"{baseline_reprice['records'][t]['authority_tier']} -> {recovered['records'][t]['authority_tier']}" for t in BOUNDED_LIVE_OVERRIDES},
        },
        "vcb_recheck": VCB_RECHECK_NOTE,
        "hpg_recheck": {
            "result": "NO_CHANGE_CEILING_RECONFIRMED",
            "note": "Live resolver returns qualified_official for HPG at 2026-08-26 using the SAME 2026-07-02 anchor and its existing 2026-08-14 corroborating provider observation, but current_common_shares_authority.py's official_common branch (fed from the frozen P3F4/P3F5 review, coverage_through=2026-07-30) correctly still governs the terminal tier: no NEW evidence extends coverage_through past 2026-07-30, so HPG remains QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT. No override applied.",
        },
        "acquisition_performed": {
            "hnx_issuer_profile_probe": {"tickers": ["HCC", "IPA", "NAG"], "requests_made": 6, "budget": 6, "retries": 0,
                                          "route": "hnx_official_issuer_profile_multi_gate.py (reused unchanged: fetch/retain/parse_profile)",
                                          "result": "KLLH/KLNY unchanged from pre-event values for all 3 -- negative corroboration, retained"},
            "vci_events_recheck": {"tickers": ["SSI", "VCB"], "requests_made": 2, "budget": 2, "retries": 0,
                                    "route": "corporate_events_sync.normalize_event (reused unchanged) over a fresh vnstock.api.company.Company(source='VCI').events() call",
                                    "result": "SSI: most recent ISS event now dated (exright_date 2026-08-17); VCB: still undated"},
            "vci_overview_recheck": {"tickers": ["SSI", "VCB", "HCC", "IPA", "NAG"], "requests_made": 5, "budget": 5, "retries": 0,
                                      "route": "vnstock.api.company.Company(source='VCI').overview() -- the same source already used market-wide for issue_share",
                                      "result": "SSI/HCC/IPA/NAG updated to a fresh post-event count each matching a clean whole-percent ratio; VCB byte-identical to retained"},
            "total_live_requests": 13,
            "runtime_or_database_writes": False,
            "vn_stock_db_mutated": False,
        },
        "authority_impact": {
            "qualified_current_common_shares_before": 0,
            "qualified_current_common_shares_after": 0,
            "note": "No ticker was promoted to QUALIFIED_CURRENT_COMMON_SHARES. All four upgrades stay PROVIDER_REPORTED_CURRENT_RESEARCH (research-usable, non-authoritative); a provider issued-share re-observation is never promoted to official common-outstanding authority regardless of freshness.",
        },
        "valuation_effect": {
            "note": "Three points, not two, to isolate the code-path switch from the evidence effect: (1) the existing frozen 26/8 baseline used share_authority_artifact=None (raw-resolution code path); (2) reprice_only re-routes through share_authority_artifact with NO new evidence -- isolates the effect of that routing change alone; (3) recovered adds the four bounded overrides on top of (2) -- isolates the effect of the bounded acquisition alone.",
            "1_frozen_26_08_baseline_share_authority_null": {
                "artifact_identity": (baseline_valuation or {}).get("artifact_identity"),
                "metric_research_usable_counts": (baseline_valuation or {}).get("coverage", {}).get("metric_research_usable_counts"),
                "share_ready": (baseline_valuation or {}).get("coverage", {}).get("share_ready"),
                "value_strategy_readiness": (baseline_valuation or {}).get("value_strategy_readiness"),
            },
            "2_reprice_only_same_evidence_via_share_authority_artifact": {
                "artifact_identity": valuation_reprice["artifact_identity"],
                "metric_research_usable_counts": valuation_reprice["coverage"]["metric_research_usable_counts"],
                "share_ready": valuation_reprice["coverage"]["share_ready"],
                "value_strategy_readiness": valuation_reprice["value_strategy_readiness"],
            },
            "3_recovered_with_bounded_overrides": {
                "artifact_identity": valuation_recovered["artifact_identity"],
                "metric_research_usable_counts": valuation_recovered["coverage"]["metric_research_usable_counts"],
                "share_ready": valuation_recovered["coverage"]["share_ready"],
                "value_strategy_readiness": valuation_recovered["value_strategy_readiness"],
            },
        },
        "boundaries": {
            "frozen_26_08_artifacts_rewritten": False,
            "value_strategy_activated": False,
            "new_provider_added": False,
            "official_authority_promoted_from_provider_source": False,
            "vn_stock_db_mutated": False,
        },
    }
    report["report_sha256"] = stable_id(report)
    (OUTPUT_DIR / "recovery_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "baseline_reprice_identity": baseline_reprice["artifact_identity"],
        "recovered_identity": recovered["artifact_identity"],
        "valuation_identity": valuation_recovered["artifact_identity"],
        "authority_tier_distribution_after": _tier_counts(recovered),
        "tickers_upgraded": sorted(BOUNDED_LIVE_OVERRIDES),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
