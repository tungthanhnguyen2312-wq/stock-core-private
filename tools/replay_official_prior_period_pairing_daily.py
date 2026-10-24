"""Explicit read-only prior-pairing replay; outputs only in this worktree's scratch."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
SESSIONS = ("2026-10-20", "2026-10-22", "2026-10-23")
NEW_SESSION = "2026-10-26"
BASE = "829500e7c132e4289147e5fa61764da47f3dce67"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stripped(projection):
    value = copy.deepcopy(projection)
    for row in value["records"].values():
        (row.get("official_income_research_context") or {}).pop("prior_period_pairing", None)
    value["source_artifacts"].pop("official_income_prior_period_inputs", None)
    value.pop("artifact_identity", None); value.pop("artifact_sha256", None)
    return value


def replay(*, runtime_root, retained_root, sealed_root, baseline, output):
    if not output.resolve().is_relative_to((ROOT / ".stocklookup/scratch").resolve()):
        raise ValueError("REPLAY_OUTPUT_MUST_BE_WORKTREE_SCRATCH")
    os.environ["STOCK_LOOKUP_RUNTIME_ROOT"] = str(runtime_root)
    os.environ["STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT"] = str(retained_root)
    from financial_evidence_currency_refresh import load_public_official_fact_rows, PUBLIC_ARTIFACT_DIR
    from market_wide_current_fundamental_research import project_session
    from stocklookup_core.financial.official_income_prior_period_pairing import load_prior_period_inputs, qualified_prior_inputs_at_cutoff
    from ai_research_session_delivery import financial_research_card
    # Same producer code as merged main: plain replay differences cannot be attributed to this milestone.
    source = ROOT / "market_wide_current_fundamental_research.py"
    assert source.read_bytes().replace(b"\r\n", b"\n") == subprocess.check_output(
        ["git", "show", BASE + ":market_wide_current_fundamental_research.py"], cwd=ROOT).replace(b"\r\n", b"\n")
    registry = json.loads((sealed_root / "config/daily_research_session_input_registry.json").read_bytes())
    sealed = {session: Path(registry["sessions"][session]["fundamental"]["path"]) for session in SESSIONS}
    paths = {baseline, sealed_root / "config/daily_research_session_input_registry.json"}
    for session in SESSIONS:
        for entry in registry["sessions"][session].values():
            if isinstance(entry, dict) and entry.get("path"):
                candidate = Path(entry["path"])
                paths.add(candidate if candidate.is_absolute() else sealed_root / candidate)
        # Conservation inventory only, not latest-file input selection: every sealed output
        # under each explicitly requested session is hashed, including multiple retained attempts.
        directory = retained_root / "operations-review/daily-research-session-operations-v1" / session
        if not directory.is_dir():
            raise ValueError("EXPLICIT_SEALED_SESSION_DIRECTORY_UNAVAILABLE:" + session)
        paths.update(p for p in directory.rglob("*") if p.is_file())
    public = ROOT / PUBLIC_ARTIFACT_DIR
    paths.update(public / name for name in ("qualified_official_facts.jsonl", "cohort_report.json", "comparative_column_observations.jsonl"))
    paths.update(runtime_root / "data/official-evidence" / name for name in ("financial_identity_citations.jsonl", "manifest.json"))
    before = {str(p): digest(p) for p in sorted(paths)}
    baseline_data = json.loads(baseline.read_bytes())
    official = load_public_official_fact_rows(ROOT)
    report = json.loads((public / "cohort_report.json").read_bytes())
    inputs = load_prior_period_inputs(runtime_root=runtime_root, repo_root=ROOT, public_root=public)
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=sealed_root, text=True).strip() == BASE
    # Execute the clean merged-main producer in its own read-only process, with identical inputs.
    main_driver = """
import sys,json
sys.path.insert(0, sys.argv[1])
from market_wide_current_fundamental_research import project_session
args = json.load(sys.stdin)
print(json.dumps({s: project_session(**args['kwargs'], session=s,
    cutoff=s+'T15:00:00+07:00')['artifact_identity'] for s in args['sessions']}))
"""
    main_run = subprocess.run([sys.executable, "-B", "-c", main_driver, str(sealed_root)],
        input=json.dumps({"kwargs": {"baseline": baseline_data, "official_rows": official, "cohort_report": report},
                          "sessions": [*SESSIONS, NEW_SESSION]}), text=True, encoding="utf-8",
        capture_output=True, check=True, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    main_identities = json.loads(main_run.stdout)
    results, cards = {}, {}
    for session in (*SESSIONS, NEW_SESSION):
        cutoff = session + "T15:00:00+07:00"
        kwargs = dict(baseline=baseline_data, official_rows=official, cohort_report=report, session=session, cutoff=cutoff)
        plain = project_session(**kwargs)
        assert plain["artifact_identity"] == main_identities[session], session
        enriched = project_session(**kwargs, prior_period_inputs=qualified_prior_inputs_at_cutoff(inputs, cutoff=cutoff))
        assert stripped(enriched) == stripped(plain), session
        hpg = enriched["records"]["HPG"]["official_income_research_context"]["prior_period_pairing"]
        pairs = {row["metric"]: row for row in hpg["comparisons"]}
        assert round(100 * pairs["revenue"]["growth_ratio"], 2) == 12.43
        assert round(100 * pairs["net_income"]["growth_ratio"], 2) == 29.08
        assert pairs["net_income"]["accounting_identity"] == "TOTAL_PROFIT_AFTER_TAX"
        assert all(row["statement_scope"] == "consolidated" and row["current_assurance"] == row["prior_assurance"] == "audited" for row in pairs.values())
        if session == NEW_SESSION:
            assert pairs["revenue"]["restatement_check"] == "COMPARATIVE_COLUMN_MATCHES_ORIGINAL"
            assert pairs["net_income"]["restatement_check"] == "COMPARATIVE_CROSS_CHECK_OCR_AMBIGUOUS"
        else:
            assert all(row["restatement_check"] == "COMPARATIVE_CROSS_CHECK_NOT_AVAILABLE" for row in pairs.values())
        for ticker, row in enriched["records"].items():
            ctx = row["official_income_research_context"]["prior_period_pairing"]
            assert all(ctx[k] == "NONE" for k in ("vote_effect", "strict_valuation_effect", "ttm_effect"))
            assert ctx["ttm_inputs"]["status"] == "UNAVAILABLE"
            assert not ctx["owner_gated_preview"]["enabled_gates"]
        unknown = {}
        for ticker in ("FPT", "PNJ", "VRE", "PVD", "POW", "QNS", "PAN"):
            ctx = enriched["records"][ticker]["official_income_research_context"]["prior_period_pairing"]
            reasons = sorted(set(ctx["blocker_reason_codes"]) | {code for r in ctx["rejected"] for code in r["reason_codes"]})
            assert ctx["direction_status"] == "UNKNOWN" and not ctx["comparisons"]
            expected = ("PRIOR_CURRENCY_DIFFERS_NO_FX" if ticker == "PVD" else
                "NO_ADMITTED_CURRENT_OFFICIAL_INCOME_FACT" if ticker in {"POW", "QNS", "PAN"} else
                "NO_INDEPENDENTLY_QUALIFIED_PRIOR_PERIOD_FACT")
            assert expected in reasons
            unknown[ticker] = reasons
        prior_sealed = json.loads(sealed[session].read_bytes())["artifact_identity"] if session in sealed else None
        results[session] = dict(plain_identity=plain["artifact_identity"], paired_identity=enriched["artifact_identity"],
            sealed_identity=prior_sealed, sealed_identity_reproduced=plain["artifact_identity"] == prior_sealed,
            merged_main_plain_identity=main_identities[session], merged_main_parity=True,
            additive_only_parity=True, hpg_pairs=pairs, unknown_reason_codes=unknown)
        if session == NEW_SESSION:
            for ticker in ("HPG", *unknown):
                card = financial_research_card({"ticker": ticker}, enriched["records"][ticker], {}, cutoff=cutoff)
                context = card["fundamental_research_context"]["official_income"]["prior_period_pairing"]
                assert context == enriched["records"][ticker]["official_income_research_context"]["prior_period_pairing"]
                cards[ticker] = card
    # Pre-PR181/183 seals are never rewritten to match the newer main's additive contexts.
    after = {str(p): digest(p) for p in sorted(paths)}
    assert after == before
    result = dict(base=BASE, prospective_acceptance_session=NEW_SESSION, sessions=results,
        source_hashes_unchanged=True, retained_file_count=len(paths), source_sha256_before=before,
        source_sha256_after=after, no_historical_receipt_adoption=True, authority_effect="NONE", production_writes=0)
    output.mkdir(parents=True, exist_ok=True)
    (output / "acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "historical_research_cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {k: result[k] for k in ("base", "prospective_acceptance_session", "retained_file_count", "source_hashes_unchanged", "production_writes")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-root", "retained-root", "sealed-root", "baseline", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(replay(**vars(parser.parse_args())), indent=2))


if __name__ == "__main__": main()
