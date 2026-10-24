"""Read-only explicit retained-input replay. Outputs are confined to this worktree's scratch."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def baseline_projection(base_ref, module, driver, inputs):
    """Run the pinned pure baseline in a separate Python process, without dynamic imports."""
    source = subprocess.check_output(["git", "show", base_ref + ":" + module], cwd=ROOT).decode("utf-8")
    scratch = ROOT / ".stocklookup/scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shareholder-baseline-", dir=scratch) as directory:
        script = Path(directory) / "baseline.py"
        script.write_text(source + "\n" + driver, encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(script)],
            input=json.dumps(inputs), text=True, encoding="utf-8", capture_output=True, check=True, cwd=ROOT,
            env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8"))
    return json.loads(result.stdout)


def replay(*, fundamental, valuation, universe, events, operation, output, base_ref):
    from current_corporate_intelligence_axis import build_artifact
    from ai_research_session_delivery import financial_research_card
    from stocklookup_core.research.shareholder_economics import VERSION
    scratch = (ROOT / ".stocklookup/scratch").resolve()
    if not output.resolve().is_relative_to(scratch):
        raise ValueError("REPLAY_OUTPUT_MUST_BE_IN_WORKTREE_SCRATCH")
    paths = [fundamental, valuation, universe, events, operation / "ai_research_session_bundle.json",
             operation / "current_research_valuation_context_artifact.json",
             operation / "current_research_decision_packet_artifact.json",
             operation / "current_decision_cockpit_projection.json"]
    before = {str(p): digest(p) for p in paths}
    f, v, u, e = [json.loads(p.read_bytes()) for p in paths[:4]]
    bundle = json.loads(paths[4].read_bytes())
    session = bundle["session"]
    if f.get("research_session") not in (None, session) or v.get("valuation_session") != session:
        raise ValueError("REPLAY_INPUT_SESSION_MISMATCH")
    if e.get("research_session") != session:
        raise ValueError("REPLAY_EVENT_SESSION_MISMATCH")
    # Execute the verified base's existing pure projection beside the new one. No checkout,
    # temporary Git refs, network, Daily, output discovery or retrospective receipt adoption.
    kwargs = dict(official_universe=u, official_event_context=e, root=ROOT,
                  research_session=session, include_supplemental_events=False)
    prior = baseline_projection(base_ref, "current_corporate_intelligence_axis.py",
        "import sys\nprint(json.dumps(build_artifact(**json.load(sys.stdin))))", kwargs | {"root": str(ROOT)})
    current = build_artifact(**kwargs, financial_records=f["records"], valuation_records=v["records"])
    assert prior["coverage"] == current["coverage"]
    assert set(prior["records"]) == set(current["records"])
    for t, row in current["records"].items():
        restored = {k: value for k, value in row.items() if k != "shareholder_economics_context"}
        assert restored == prior["records"][t], t
    cards, counts = {}, {}
    source_cards = bundle["ticker_research_contexts"]
    old_cards = baseline_projection(base_ref, "ai_research_session_delivery.py", """
import sys
replay_inputs = json.load(sys.stdin)
print(json.dumps({t: financial_research_card(card, replay_inputs['fundamentals'].get(t),
    card.get('integrated_decision_v1') or {}, cutoff=replay_inputs['cutoff'])
    for t, card in replay_inputs['cards'].items()}))
""", {"cards": source_cards, "fundamentals": f["records"], "cutoff": f"{session}T15:00:00+07:00"})
    for t, original in sorted(source_cards.items()):
        integrated = original.get("integrated_decision_v1") or {}
        args = (original, f["records"].get(t), integrated)
        old = old_cards[t]
        new = financial_research_card(*args, cutoff=f"{session}T15:00:00+07:00")
        context = new.pop("shareholder_economics_context")
        assert new == old, t
        counts[context["status"]] = counts.get(context["status"], 0) + 1
        if t in {"PNJ", "NVL", "SSI", "HPG", "PAN"}:
            cards[t] = {"existing_decision": copy.deepcopy(integrated.get("research_action_posture")),
                        "existing_valuation": copy.deepcopy(integrated.get("valuation_context_summary")),
                        "shareholder_economics_context": context,
                        "corporate_axis_context": current["records"][t]["shareholder_economics_context"]}
    assert set(cards) == {"PNJ", "NVL", "SSI", "HPG", "PAN"}
    after = {str(p): digest(p) for p in paths}
    assert after == before
    result = dict(contract_version=VERSION, session=session, base_ref=base_ref,
        corporate_records_parity=len(current["records"]), primary_card_parity=len(source_cards),
        context_status_counts=counts, actual_issuer_contexts=cards,
        source_sha256_before=before, source_sha256_after=after, sealed_bytes_unchanged=True,
        production_writes=0, authority_effect="NONE", candidate_evidence_used=False)
    output.mkdir(parents=True, exist_ok=True)
    (output / "acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {k: value for k, value in result.items() if k not in {"actual_issuer_contexts", "source_sha256_before", "source_sha256_after"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fundamental", "valuation", "universe", "events", "operation", "output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--inspect", action="store_true", help="Offline/opt-in issuer research inspection; never a Daily stage")
    parser.add_argument("--candidate-index", type=Path)
    parser.add_argument("--share-note", type=Path, action="append")
    parser.add_argument("--original-root", type=Path, action="append")
    parser.add_argument("--original-manifest", type=Path, action="append")
    parser.add_argument("--cutoff")
    parser.add_argument("--tickers", default="HPG,PNJ,SSI,PVD,POW,QNS")
    args = vars(parser.parse_args())
    if args.pop("inspect"):
        if not args["candidate_index"] or not args["output"] or not args["cutoff"]:
            parser.error("--inspect requires --candidate-index, --output and --cutoff")
        result = inspect_research(**{k: args[k] for k in ("candidate_index", "share_note", "original_root",
            "original_manifest", "cutoff", "tickers", "output")})
    else:
        required = ("fundamental", "valuation", "universe", "events", "operation", "output", "base_ref")
        if any(args[k] is None for k in required):
            parser.error("retained replay requires "+", ".join("--"+k.replace("_", "-") for k in required))
        result = replay(**{k: args[k] for k in required})
    print(json.dumps(result, indent=2))


def inspect_research(*, candidate_index, output, cutoff, tickers="HPG,PNJ,SSI,PVD,POW,QNS",
                     share_note=None, original_root=None, original_manifest=None):
    """Inspect explicit files only; match originals by issuer + URL + byte hash.

    A matched PDF confirms retained bytes, not the CSV extraction or its FACT label.
    Existing qualified note receipts are rechecked by their original owner in memory.
    """
    from stocklookup_core.research.shareholder_economics import project_context, candidate_discovery_context, _identity
    scratch = (ROOT / ".stocklookup/scratch").resolve()
    if not Path(output).resolve().is_relative_to(scratch):
        raise ValueError("REPLAY_OUTPUT_MUST_BE_IN_WORKTREE_SCRATCH")
    if bool(original_root) != bool(original_manifest):
        raise ValueError("EXPLICIT_ORIGINAL_ROOT_AND_MANIFEST_REQUIRED_TOGETHER")
    def many(value):
        return list(value) if isinstance(value, (list, tuple)) else [value] if value else []
    roots, manifests, note_paths = map(many, (original_root, original_manifest, share_note))
    if len(roots) != len(manifests):
        raise ValueError("EXPLICIT_ORIGINAL_ROOT_AND_MANIFEST_REQUIRED_TOGETHER")
    paths = [Path(candidate_index)]+[Path(p) for p in note_paths+manifests]
    before = {str(p.resolve()): digest(p) for p in paths}
    index = json.loads(Path(candidate_index).read_bytes())
    notes = []
    for path in note_paths:
        data = json.loads(Path(path).read_bytes())
        if 'qualification_inputs' in data:
            from stocklookup_core.evidence.current_common_shares_official_evidence_acquisition import qualify_retained_share_capital_note
            notes.extend(qualify_retained_share_capital_note(**row) for row in data['qualification_inputs'])
        else:
            notes.extend(data['notes'] if 'notes' in data else [data])
    records = [(r, Path(root)) for root, manifest in zip(roots, manifests)
        for r in json.loads(Path(manifest).read_bytes()).get("records", [])]
    verifications, matched_records = {}, {}
    originals_before = {}
    for doc in index["source_manifest"]["documents"]:
        key = doc.get("source_id")
        matches = [(r, root) for r, root in records if r.get("ticker") == doc.get("issuer")
            and str(r.get("canonical_url")).replace(' ', '%20') == str(doc.get("url")).replace(' ', '%20')
            and r.get("sha256") == doc.get("sha256")
            and r.get("acquisition_status") == "retained"]
        reasons = ["RETAINED_ORIGINAL_BYTES_NOT_VERIFIED"]
        if len(matches) == 1:
            record, root = matches[0]
            path = (root/record["relative_path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                reasons = ["ORIGINAL_PATH_OUTSIDE_EXPLICIT_ROOT"]
            elif path.is_file():
                actual = digest(path)
                originals_before[str(path)] = actual
                reasons = [] if actual == doc["sha256"] else ["ORIGINAL_BYTE_HASH_MISMATCH"]
                if not reasons:
                    matched_records[(record["ticker"], record["sha256"], record["canonical_url"])] = record
            else:
                reasons = ["ORIGINAL_BYTES_MISSING"]
        verifications[key] = dict(status="RAW_BYTES_AND_MANIFEST_MATCHED" if not reasons else "UNVERIFIED",
            sha256=doc.get("sha256"), reason_codes=reasons,
            retained_manifest_observed_at=matches[0][0].get("observed_at") if len(matches) == 1 else None,
            retained_manifest_published_at=matches[0][0].get("published_at") if len(matches) == 1 else None)
    accepted_notes, note_blockers = [], []
    for note in notes:
        source = note.get('document') if note.get('contract_version') == 'retained_share_capital_note/v1' else dict(
            ticker=note.get('ticker'), sha256=note.get('document_sha256'), canonical_url=note.get('source_url'),
            observed_at=note.get('observed_at'), published_at=note.get('published_at'))
        match = matched_records.get((source.get('ticker'), source.get('sha256'), source.get('canonical_url')))
        if match is not None and all(match.get(k) == source.get(k) for k in ('observed_at', 'published_at')):
            accepted_notes.append(note)
        else:
            note_blockers.append(dict(citation_id=note.get("citation_id"), reason="EXISTING_NOTE_ORIGINAL_BYTES_OR_MANIFEST_NOT_VERIFIED"))
    cards = {}
    for ticker in sorted(set(t.strip().upper() for t in tickers.split(",") if t.strip())):
        qualified = project_context(ticker=ticker, cutoff=cutoff,
            retained_common_share_notes=[n for n in accepted_notes if n.get("ticker") == ticker])
        candidates = candidate_discovery_context(ticker=ticker, cutoff=cutoff,
            report_known_at=index["report_known_at"], source_manifest=index["source_manifest"],
            event_rows=index["events"], continuity_rows=index["continuity_points"], gap_rows=index["unresolved_gaps"],
            original_verifications=verifications)
        cards[ticker] = dict(shareholder_economics_context=qualified, candidate_discovery=candidates)
    packet = dict(contract_version="shareholder_economics_offline_inspection/v1", cutoff=cutoff,
        is_actionable=False, authority_effect="NONE", vote_effect="NONE", runtime_activation=False,
        hub_commit=index.get("hub_commit"), input_sha256=before, original_sha256=originals_before,
        original_verifications=verifications, note_blockers=note_blockers, issuer_cards=cards)
    packet["context_identity"] = _identity(packet)
    lines = ["# Shareholder economics and dilution research", "", "OFFLINE / NON-VOTING / no strict share or price authority.",
        "Candidate discovery is not official evidence, even where the Hub labels a row FACT or a raw PDF matches.",
        "Issued, outstanding, treasury, listed, tradeable, basic/diluted EPS and charter capital are different bases.",
        "No ex-date, share continuity, market cap or valuation denominator is inferred.", ""]
    for ticker, card in cards.items():
        context, discovery = card["shareholder_economics_context"], card["candidate_discovery"]
        lines += ["## "+ticker, "", f"Admitted observations: {len(context['claims'])}; candidate report: {discovery['status']}."]
        for claim in context["claims"]:
            lines.append(f"- QUALIFIED HISTORICAL {claim['state']}: {claim['kind']} {claim['value']} {claim['unit']} at {claim.get('effective_date')}; scope {claim.get('scope')}; citation {claim['citation_id']}. Later continuity remains UNKNOWN.")
        for change in context['share_capital_research']['endpoint_changes']:
            ratio = change['change_ratio']
            percent = f' ({ratio:+.2%})' if ratio is not None else ''
            lines.append(f"- ENDPOINT RESEARCH {change['kind']} ({change['scope']}): "
                f"{change['prior_value']:,} at {change['prior_date']} to {change['current_value']:,} at {change['current_date']}; "
                f"change {change['change']:+,} shares{percent}. Continuity and ownership dilution remain UNKNOWN.")
        for finding in discovery.get("research_findings", []):
            lines.append(f"- {finding['classification']}: {finding['text']}"+(
                f" Reported legal/accounting basis {finding['reported_legal_basis_count']}; EPS basis {finding['reported_eps_basis_count']}; difference {finding['eps_minus_legal_count']} shares ({', '.join(finding['source_rows'])})."
                if "source_rows" in finding else ""))
        for item in discovery["continuity_points"]:
            row = item["candidate_payload"]
            lines.append(f"- CANDIDATE {row.get('chain_id')}: {row.get('date')} | {row.get('share_definition')} | {row.get('count')} | source {row.get('source_id')}, {row.get('locator')}. Report assertion only: {row.get('evidence_status')}.")
        for item in discovery["events"]:
            row = item["candidate_payload"]
            lines.append(f"- CANDIDATE {row.get('event_id')}: {row.get('event')} | {row.get('stage')} | {row.get('count_shares')} | {row.get('event_date')} ({row.get('date_type')}). {row.get('note')}")
        for item in discovery["unresolved_gaps"]:
            row = item["candidate_payload"]
            lines.append(f"- UNKNOWN {row.get('gap_id')}: {row.get('missing_fact')}. Required original: {row.get('exact_locator_to_fetch')}.")
        for source in discovery["sources"]:
            doc = source["candidate_source"]
            lines.append(f"- SOURCE {source['source_id']}: {doc.get('url')}; sha256 {doc.get('sha256')}; blockers: {', '.join(source['blocker_reason_codes'])}.")
        lines += ["- Research limit: approval does not prove completion; EPS restatement does not prove legal outstanding; treasury scope differences are not automatically conflicts; absence of completion evidence is not zero execution.", ""]
    assert {str(p.resolve()): digest(p) for p in paths} == before
    assert {path: digest(Path(path)) for path in originals_before} == originals_before
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rendered = {output/"research_packet.json": json.dumps(packet, ensure_ascii=False, indent=2)+"\n",
                output/"research_cards.md": "\n".join(lines)+"\n"}
    for path, text in rendered.items():
        if not path.resolve().is_relative_to(scratch):
            raise ValueError("REPLAY_OUTPUT_MUST_BE_IN_WORKTREE_SCRATCH")
        if str(path.resolve()) in before or str(path.resolve()) in originals_before:
            raise ValueError("RESEARCH_OUTPUT_OVERLAPS_INPUT")
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise ValueError("REFUSING_TO_OVERWRITE_DISTINCT_RESEARCH")
    for path, text in rendered.items():
        if not path.exists():
            path.write_text(text, encoding="utf-8")
    return dict(output=str(output), issuers=len(cards), admitted_observations=sum(len(c["shareholder_economics_context"]["claims"]) for c in cards.values()),
        verified_raw_documents=sum(v["status"] == "RAW_BYTES_AND_MANIFEST_MATCHED" for v in verifications.values()),
        source_hashes_unchanged=True, authority_effect="NONE", runtime_activation=False)


if __name__ == "__main__":
    main()
