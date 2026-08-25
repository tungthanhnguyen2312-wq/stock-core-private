"""Foreground operational runner for the Level-2 current-session package.

Produces all governed current-session components and materializes the Level-2
manifest and brief for any completed trading session (e.g. 2026-08-25).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPS = ROOT / "operations-review"


def run_cmd(cmd: list[str]) -> None:
    print(f"--> {' '.join(cmd)}")
    subprocess.run([sys.executable] + cmd, cwd=str(ROOT), check=True)


def materialize_level2(session: str, runtime_root: Path, workers: int = 12) -> Path:
    session_nodash = session.replace("-", "")
    p3f9b_dir = OPS / f"p3f9b-market-wide-exact-session-scaleout-{session_nodash}"
    p3f9b_snapshot = p3f9b_dir / "p3f9b_mva_exact_session_snapshot.json"
    
    # 1. Exact-session data acquisition
    if not p3f9b_snapshot.exists():
        run_cmd([
            "tools/run_p3f9b_market_wide_exact_session_scaleout.py",
            "--session", session,
            "--runtime-root", str(runtime_root),
            "--out-dir", str(p3f9b_dir),
            "--workers", str(workers),
        ])
    
    # 2. Breadth Foundation
    breadth_out = OPS / f"current-market-universe-breadth-foundation-v1-{session_nodash}" / "current_market_universe_breadth_foundation_artifact.json"
    if not breadth_out.exists():
        run_cmd([
            "tools/build_current_market_universe_breadth_foundation.py",
            "--snapshot", str(p3f9b_snapshot),
            "--output", str(breadth_out),
        ])
        
    # 3. Universe Resolution
    ur_out = OPS / f"current-universe-status-and-session-coverage-resolution-v1-{session_nodash}" / "current_universe_status_and_session_coverage_resolution_artifact.json"
    if not ur_out.exists():
        run_cmd([
            "tools/run_current_universe_status_and_session_coverage_resolution.py",
            "--snapshot", str(p3f9b_snapshot),
            "--output", str(ur_out),
        ])
        
    # 4. Liquidity Research
    liq_dir = OPS / f"market-wide-current-liquidity-research-v1-{session_nodash}"
    liq_out = liq_dir / "market_wide_current_liquidity_research_artifact.json"
    if not liq_out.exists():
        snapshot_data = json.loads(p3f9b_snapshot.read_text(encoding="utf-8"))
        num_candidates = len(snapshot_data.get("records", {}))
        num_batches = math.ceil(num_candidates / 100)
        for i in range(num_batches):
            run_cmd([
                "tools/run_market_wide_current_liquidity_research.py",
                "--universe-snapshot", str(p3f9b_snapshot),
                "--out-dir", str(liq_dir),
                "--session", session,
                "--batch-index", str(i),
                "--batch-size", "100",
                "--workers", str(workers),
            ])
        run_cmd([
            "tools/run_market_wide_current_liquidity_research.py",
            "--universe-snapshot", str(p3f9b_snapshot),
            "--out-dir", str(liq_dir),
            "--session", session,
            "--consolidate",
        ])

    # 5. Technical Coverage Recovery Scaleout
    tech_dir = OPS / f"market-wide-current-technical-coverage-scaleout-v1-{session_nodash}"
    tech_out = tech_dir / "market_wide_current_technical_coverage_recovery_artifact.json"
    baseline_desc = OPS / "market-wide-current-descriptive-research-v1-20260824" / "market_wide_current_descriptive_research_artifact.json"
    if not tech_out.exists():
        from market_wide_current_technical_coverage_scaleout import recovery_candidates
        b_data = json.loads(baseline_desc.read_text(encoding="utf-8"))
        s_data = json.loads(p3f9b_snapshot.read_text(encoding="utf-8"))
        candidates = recovery_candidates(baseline_artifact=b_data, p3f9b_snapshot=s_data)
        num_batches = math.ceil(len(candidates) / 10)
        for i in range(num_batches):
            run_cmd([
                "tools/run_market_wide_current_technical_coverage_scaleout.py",
                "--baseline", str(baseline_desc),
                "--snapshot", str(p3f9b_snapshot),
                "--out-dir", str(tech_dir),
                "--batch", str(i),
                "--batch-size", "10",
            ])
        run_cmd([
            "tools/run_market_wide_current_technical_coverage_scaleout.py",
            "--baseline", str(baseline_desc),
            "--snapshot", str(p3f9b_snapshot),
            "--out-dir", str(tech_dir),
            "--consolidate",
            "--batch-size", "10",
        ])

    # 6. Descriptive Research
    desc_out = OPS / f"market-wide-current-descriptive-research-v1-{session_nodash}" / "market_wide_current_descriptive_research_artifact.json"
    if not desc_out.exists():
        run_cmd([
            "tools/run_market_wide_current_descriptive_research.py",
            "--universe-resolution-artifact", str(ur_out),
            "--p3f9b-snapshot", str(p3f9b_snapshot),
            "--liquidity-artifact", str(liq_out),
            "--technical-history-recovery-artifact", str(tech_out),
            "--output", str(desc_out),
        ])

    # 7. Screening Foundation
    screen_out = OPS / f"current-market-screening-opportunity-comparison-foundation-v1-{session_nodash}" / "current_market_screening_opportunity_comparison_foundation_artifact.json"
    if not screen_out.exists():
        run_cmd([
            "tools/run_current_market_screening_opportunity_comparison_foundation.py",
            "--source", str(desc_out),
            "--out", str(screen_out),
        ])

    # 8. Tactical Entry Classifier
    tactical_dir = OPS / f"watchlist-tactical-entry-decision-v1-{session_nodash}"
    tactical_out = tactical_dir / "watchlist_tactical_entry_classifier_artifact.json"
    fundamental_retained = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
    if not tactical_out.exists():
        run_cmd([
            "tools/run_watchlist_tactical_entry_classifier.py",
            "--descriptive-path", str(desc_out),
            "--screening-path", str(screen_out),
            "--fundamental-path", str(fundamental_retained),
            "--out-dir", str(tactical_dir),
        ])

    # 9. Corporate Intelligence
    ci_out = OPS / f"market-wide-current-corporate-intelligence-v1-{session_nodash}" / "market_wide_current_corporate_intelligence_artifact.json"
    if not ci_out.exists():
        run_cmd([
            "tools/run_market_wide_current_corporate_intelligence.py",
            "--session", session,
            "--descriptive", str(desc_out),
            "--fundamental", str(fundamental_retained),
            "--output", str(ci_out),
        ])

    # 10. Valuation Scaleout
    val_dir = OPS / f"market-wide-current-valuation-v1-{session_nodash}-session{session_nodash}"
    val_out = val_dir / "market_wide_current_valuation_artifact.json"
    if not val_out.exists():
        run_cmd([
            "tools/derive_market_wide_current_valuation_input_scaleout.py",
            "--runtime-root", str(runtime_root),
            "--price", str(p3f9b_snapshot),
            "--output", str(val_out),
            "--report", str(val_dir / "market_wide_current_valuation_research_scaleout_report.json"),
        ])

    # 11. Sector Leadership
    leadership_out = OPS / f"current-market-sector-leadership-context-v1-{session_nodash}" / "current_market_sector_leadership_context_artifact.json"
    official_u = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
    if not leadership_out.exists():
        run_cmd([
            "tools/run_current_market_sector_leadership_context.py",
            "--current-descriptive-artifact", str(desc_out),
            "--current-screening-artifact", str(screen_out),
            "--current-official-universe-artifact", str(official_u),
            "--output", str(leadership_out),
        ])

    # 12. Sector-aware Relative Research
    peer_out = OPS / f"sector-aware-relative-research-v1-{session_nodash}" / "sector_aware_relative_research_artifact.json"
    if not peer_out.exists():
        run_cmd([
            "tools/run_sector_aware_relative_research.py",
            "--descriptive", str(desc_out),
            "--tactical", str(tactical_out),
            "--fundamental", str(fundamental_retained),
            "--valuation", str(val_out),
            "--output", str(peer_out),
        ])

    # 13. Evidence Bound Scenario
    sc_out = OPS / f"current-evidence-bound-scenario-v1-{session_nodash}" / "current_evidence_bound_scenario_artifact.json"
    if not sc_out.exists():
        from current_evidence_bound_scenario import build as build_scenario
        cat = json.loads((OPS / "catalyst-event-research-context-v1-20260820" / "catalyst_event_research_context_artifact.json").read_text("utf-8"))
        tri = json.loads((OPS / "full-universe-entry-candidate-triage-20260824" / "full_universe_entry_candidate_triage_20260824.json").read_text("utf-8"))
        scenario_art = build_scenario(
            descriptive=json.loads(desc_out.read_text("utf-8")),
            tactical=json.loads(tactical_out.read_text("utf-8")),
            peer_relative=json.loads(peer_out.read_text("utf-8")),
            fundamental=json.loads(fundamental_retained.read_text("utf-8")),
            valuation=json.loads(val_out.read_text("utf-8")),
            triage=tri,
            catalyst=cat,
            screening=json.loads(screen_out.read_text("utf-8")),
            corporate_intelligence=json.loads(ci_out.read_text("utf-8")),
        )
        sc_out.parent.mkdir(parents=True, exist_ok=True)
        sc_out.write_text(json.dumps(scenario_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 14. Polymorphic Strategy Classification
    strategy_out = OPS / f"polymorphic-current-strategy-classification-v1-{session_nodash}" / "polymorphic_current_strategy_classification_artifact.json"
    if not strategy_out.exists():
        from polymorphic_current_strategy_classification import build as build_strategy
        strategy_art = build_strategy(
            descriptive=json.loads(desc_out.read_text("utf-8")),
            tactical=json.loads(tactical_out.read_text("utf-8")),
            peer_relative=json.loads(peer_out.read_text("utf-8")),
            fundamental=json.loads(fundamental_retained.read_text("utf-8")),
            valuation=json.loads(val_out.read_text("utf-8")),
            scenario=json.loads(sc_out.read_text("utf-8")),
            corporate_intelligence=json.loads(ci_out.read_text("utf-8")),
        )
        strategy_out.parent.mkdir(parents=True, exist_ok=True)
        strategy_out.write_text(json.dumps(strategy_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 15. Opportunity Prioritization
    opp_out = OPS / f"current-opportunity-prioritization-v1-{session_nodash}" / "current_opportunity_prioritization_artifact.json"
    if not opp_out.exists():
        from current_opportunity_prioritization import build as build_opp, content_identity as opp_id
        ev = json.loads((OPS / "current-official-event-context-integration-v1-20260824" / "current_official_event_context_artifact.json").read_text("utf-8"))
        opp_art = build_opp(
            official_universe=json.loads(official_u.read_text("utf-8")),
            screening=json.loads(screen_out.read_text("utf-8")),
            tactical=json.loads(tactical_out.read_text("utf-8")),
            strategy=json.loads(strategy_out.read_text("utf-8")),
            scenario=json.loads(sc_out.read_text("utf-8")),
            fundamental=json.loads(fundamental_retained.read_text("utf-8")),
            peer=json.loads(peer_out.read_text("utf-8")),
            event_context=ev,
            descriptive=json.loads(desc_out.read_text("utf-8")),
        )
        opp_art.update(opp_id(opp_art))
        opp_out.parent.mkdir(parents=True, exist_ok=True)
        opp_out.write_text(json.dumps(opp_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 16. Research Risk Register
    risk_out = OPS / f"current-research-risk-register-v1-{session_nodash}" / "current_research_risk_register_artifact.json"
    if not risk_out.exists():
        run_cmd([
            "tools/run_current_research_risk_register.py",
            "--leadership-context", str(leadership_out),
            "--valuation-context", str(val_out),
            "--output", str(risk_out),
        ])

    # 17. Decision Packet
    packet_out = OPS / f"current-research-decision-packet-v1-{session_nodash}" / "current_research_decision_packet_artifact.json"
    if not packet_out.exists():
        run_cmd([
            "tools/run_current_research_decision_packet.py",
            "--opportunity", str(opp_out),
            "--scenario", str(sc_out),
            "--risk-register", str(risk_out),
            "--market-sector", str(leadership_out),
            "--valuation", str(val_out),
            "--output", str(packet_out),
        ])

    # 18. Decision Cockpit Projection
    cockpit_dir = OPS / f"current-research-decision-packet-dashboard-shadow-v1-{session_nodash}"
    if not (cockpit_dir / "market_wide_product_validation.json").exists():
        run_cmd([
            "tools/run_current_research_decision_packet_dashboard.py",
            "--packet-path", str(packet_out),
            "--output-dir", str(cockpit_dir),
        ])

    # 19. Same Session Technical Coverage Disposition
    disp_dir = OPS / f"same-session-technical-coverage-recovery-v1-{session_nodash}"
    disp_out = disp_dir / "same_session_technical_coverage_disposition_artifact.json"
    if not disp_out.exists():
        from same_session_technical_coverage_disposition import build as build_disp, content_identity as disp_id
        disp_art = build_disp(
            descriptive=json.loads(desc_out.read_text("utf-8")),
            official_universe=json.loads(official_u.read_text("utf-8")),
            p3f9b_snapshot=json.loads(p3f9b_snapshot.read_text("utf-8")),
            universe_status=json.loads(ur_out.read_text("utf-8")),
            tactical=json.loads(tactical_out.read_text("utf-8")),
            recovery=json.loads(tech_out.read_text("utf-8")),
        )
        disp_art.update(disp_id(disp_art))
        disp_dir.mkdir(parents=True, exist_ok=True)
        disp_out.write_text(json.dumps(disp_art, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pkg_dir = OPS / f"daily-session-{session}-level2-package"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nSUCCESS: Level-2 Governed Component Package for {session} is complete in {pkg_dir}")
    return pkg_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="2026-08-25", help="Target completed market session (YYYY-MM-DD)")
    parser.add_argument("--runtime-root", type=Path, default=Path("../dashboard-runtime"))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args(argv)
    materialize_level2(args.session, args.runtime_root, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
