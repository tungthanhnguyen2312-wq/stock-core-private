"""Pin a research-only provider monetary-basis verdict from retained citations and facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_fact_store as store
import provider_financial_semantic_basis as semantic

CONTRACT = "provider_financial_monetary_basis_verdict/v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(runtime_root: Path) -> dict:
    citations = store.load_official_citations(runtime_root)
    # The canonical loader owns metric and stock-period aliasing. Its serving shape omits
    # statement scope, so attach that retained citation field by exact citation ID here.
    # This affects reconciliation eligibility only; canonical facts are unchanged.
    citation_scopes = {}
    for name in ("ebitda_component_citations.jsonl", "financial_identity_citations.jsonl"):
        path = runtime_root / "data" / "official-evidence" / name
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                citation_scopes[record.get("citation_id")] = record.get("statement_scope")
    citations = {key: {**value, "statement_scope": citation_scopes.get(value.get("citation_id"))}
                 for key, value in citations.items()}
    tickers = sorted({key[0] for key in citations})
    profiles_path = ROOT / "config" / "ticker_entity_profiles.csv"
    profiles = store.load_entity_profiles(profiles_path)
    facts_by_ticker = {
        ticker: store.build_ticker_facts(runtime_root, ticker, profiles=profiles,
                                         official_citations=citations)["facts"]
        for ticker in tickers
    }
    reconciliation = semantic.reconcile_official_anchors(facts_by_ticker, citations)
    registry = semantic.build_semantic_basis_registry(reconciliation)
    qualified = [key for key, row in registry["contracts"].items()
                 if row["verdict"] == semantic.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED]
    if qualified != ["VCI:balance_sheet"]:
        raise ValueError(f"UNEXPECTED_QUALIFIED_PROVIDER_SHAPES:{qualified}")
    evidence_files = [profiles_path, *(store.shard_path(runtime_root, ticker) for ticker in tickers),
                      *(runtime_root / "data" / "official-evidence" / name
                        for name in ("ebitda_component_citations.jsonl", "financial_identity_citations.jsonl"))]
    payload = {
        "contract_version": CONTRACT, "schema_version": "1.0.0",
        "source_reconciliation": reconciliation, "semantic_basis_registry": registry,
        "qualified_shapes": qualified,
        "input_sha256": {str(path.relative_to(runtime_root if path.is_relative_to(runtime_root) else ROOT)).replace("\\", "/"):
                         _sha(path) for path in evidence_files if path.is_file()},
        "authority_boundary": {"current_research_only": True, "official_financial": False,
                               "historical_pit": False, "exact_valuation": False,
                               "target_price": False, "actionable": False},
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    payload["artifact_sha256"] = digest
    payload["artifact_identity"] = f"{CONTRACT}:{digest}"
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    artifact = build(args.runtime_root.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "provider_financial_monetary_basis_verdict.json"
    path.write_bytes(json.dumps(artifact, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8") + b"\n")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"],
                      "qualified_shapes": artifact["qualified_shapes"],
                      "vci_balance_sheet_anchors": artifact["source_reconciliation"]["shapes"].get("('VCI', 'balance_sheet')", {}).get("classification_counts")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
