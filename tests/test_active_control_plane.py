"""Structural guard for the compact ACTIVE control plane (docs only; no runtime behavior).

Asserts shape, vocabulary, coverage, relative links and the size budget of the small authoritative
reading set. It deliberately asserts no date-sensitive fact (those live in ACTIVE_STATE.md and are
re-verified by their stated commands), so it does not rot with each session.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ACTIVE_SET = ["AGENTS.md", "docs/ACTIVE_STATE.md", "docs/CAPABILITIES.md", "docs/AUTHORITY.md",
              "docs/DAILY_PIPELINE.md", "docs/ROADMAP_CURRENT.md"]
INDEXED = ACTIVE_SET + ["docs/HISTORICAL_INDEX.md"]
RUNTIME = {"ACTIVE", "ACTIVE_FAILSOFT", "FROZEN_HISTORICAL", "BLOCKED_EVIDENCE", "DEFERRED", "EXPERIMENTAL"}
AUTHORITY = {"AUTHORITATIVE", "SCOPED", "NON_VOTING", "BLOCKED", "DEFERRED"}
PRODUCTION = {"IN_DAILY_BLOCKING", "IN_DAILY_FAILSOFT", "OWNER_LAUNCHER", "OFFLINE_ONLY", "NOT_RUN"}
SIZE_BUDGET_BYTES = 100 * 1024  # a fresh agent must be able to read the whole active set


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_active_files_exist_and_fit_the_reading_budget():
    sizes = {rel: (ROOT / rel).stat().st_size for rel in ACTIVE_SET}
    assert all(size > 0 for size in sizes.values()), sizes
    assert sum(sizes.values()) <= SIZE_BUDGET_BYTES, sizes
    state_lines = len(read("docs/ACTIVE_STATE.md").splitlines())
    assert 100 <= state_lines <= 320, state_lines  # compact, not thousands


def test_relative_markdown_links_resolve():
    link = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
    missing = []
    for rel in INDEXED:
        base = (ROOT / rel).parent
        for target in link.findall(read(rel)):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (base / target).resolve().exists():
                missing.append(f"{rel} -> {target}")
    assert not missing, missing


def test_agents_reading_contract_orders_the_active_set_and_demotes_history():
    text = read("AGENTS.md")
    positions = [text.index(name) for name in (
        "docs/ACTIVE_STATE.md", "docs/CAPABILITIES.md", "docs/AUTHORITY.md",
        "docs/DAILY_PIPELINE.md", "docs/ROADMAP_CURRENT.md")]
    assert positions == sorted(positions)
    contract = text[text.index("## Reading contract"):text.index("## Current direction")]
    for legacy in ("docs/STATE.md", "docs/DECISIONS.md", "docs/ROADMAP.md", "docs/ROADMAP_STATE.json"):
        assert legacy in contract
    assert "not mandatory full" in contract and "HISTORICAL_INDEX.md" in contract
    assert "never** project authority" in contract
    # The old mandatory full read of the giant narrative file must be gone from the bootstrap.
    bootstrap = text[text.index("## Default lightweight bootstrap"):text.index("## AI context hygiene")]
    assert "docs/STATE.md`](docs/STATE.md) in full" not in bootstrap
    assert "Do **not** read `STATE.md`, `DECISIONS.md` or `ROADMAP.md` in full" in bootstrap


def test_capability_registry_blocks_are_complete_and_use_the_closed_vocabularies():
    text = read("docs/CAPABILITIES.md")
    blocks = re.split(r"(?m)^### ", text)[1:]
    assert len(blocks) >= 23
    for block in blocks:
        title = block.splitlines()[0]
        for label in ("Contract", "Runtime", "Authority", "Production", "Input", "Predecessor", "Blocker", "Next trigger"):
            assert label in block, (title, label)
        runtime = re.search(r"Runtime: `(\w+)`", block)
        authority = re.search(r"Authority: `(\w+)`", block)
        production = re.search(r"Production: `(\w+)`", block)
        assert runtime and runtime.group(1) in RUNTIME, title
        assert authority and authority.group(1) in AUTHORITY, title
        assert production and production.group(1) in PRODUCTION, title
    titles = " | ".join(re.findall(r"(?m)^### (.+)$", text)).lower()
    for needle in ("market acquisition", "listing", "calendar", "capture", "t0 decision snapshot", "seal index",
                   "technical v1", "technical v2", "relationship view", "volume & flow v1", "volume & flow v2",
                   "foreign flow", "corporate intelligence", "financial evidence", "valuation", "thesis stage 1",
                   "thesis stage 2", "outcome", "learning", "portfolio", "execution", "dashboard"):
        assert needle in titles, needle


def test_authority_map_rows_use_the_closed_vocabulary_and_cite_a_controlling_source():
    text = read("docs/AUTHORITY.md")
    rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| ---")
            and not line.startswith("| Area")]
    assert len(rows) >= 16
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 4, row
        assert cells[1].strip("`") in AUTHORITY, row
        assert cells[3], row
    areas = " ".join(r.lower() for r in rows)
    for needle in ("factual", "numerical", "ai authority", "current session", "capture completeness", "t0 snapshot",
                   "raw", "corporate actions", "listing", "calendar", "technical", "volume", "thesis",
                   "posture", "valuation", "outcomes"):
        assert needle in areas, needle


def test_daily_pipeline_lists_the_stages_in_runtime_order():
    text = read("docs/DAILY_PIPELINE.md")
    # Section B (the Daily kernel) is documented in runtime order; section A holds the Owner phases around it.
    kernel_order = ["Calendar / Phase A", "Market acquisition", "Listing + capture binding",
                    "Phase B gate", "Technical + enrichment", "Daily Producer", "T0 snapshot", "T0 seal index",
                    "Daily boundary / first marker", "Thesis T0 sidecar", "feedback #1", "Handoff bundle",
                    "Post-handoff observers", "Thesis current", "feedback #2", "Presentation projection"]
    kernel = text[text.index("## B. Canonical Daily kernel"):]
    positions = []
    for stage in kernel_order:
        assert stage in kernel, stage
        positions.append(kernel.index(stage))
    assert positions == sorted(positions), list(zip(kernel_order, positions))
    owner = text[text.index("## A. Owner launcher"):text.index("## B. Canonical Daily kernel")]
    owner_order = ["Repository preflight", "Host preflight", "Canonical Daily", "Daily completion verification",
                   "Producer state publication", "Dashboard publication", "AI handoff build", "Remote verification"]
    owner_positions = [owner.index(stage) for stage in owner_order]
    assert owner_positions == sorted(owner_positions), list(zip(owner_order, owner_positions))
    for column in ("Block/Soft", "Process", "Retained output", "Retry / recovery"):
        assert column in text


def test_current_roadmap_has_the_four_horizons_and_never_auto_starts():
    text = read("docs/ROADMAP_CURRENT.md")
    headings = [m.group(0) for m in re.finditer(r"(?m)^## (NOW|NEXT EVIDENCE GATE|AFTER FIRST-REAL ACCEPTANCE|LATER)", text)]
    assert [h[3:] for h in headings] == ["NOW", "NEXT EVIDENCE GATE", "AFTER FIRST-REAL ACCEPTANCE", "LATER"]
    assert "FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE" in text.split("## NEXT EVIDENCE GATE")[0]
    assert "Nothing below" in text and "auto-start" in text


def test_active_state_separates_fact_blocked_deferred_and_historical_and_keeps_launch_rules():
    text = " ".join(read("docs/ACTIVE_STATE.md").split())  # line wrapping must not matter
    for marker in ("CURRENT FACT", "HOST-LOCAL", "BLOCKED", "DEFERRED", "HISTORICAL"):
        assert marker in text, marker
    for phrase in ("FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE", "OWNER_DAILY_HOST_PREFLIGHT_V1", "READY",
                   "AMBER", "must not launch", "CAPTURE_COMPLETENESS_ONLY", "first marker is null"):
        assert phrase in text, phrase


def test_legacy_narrative_files_remain_and_are_indexed_not_copied():
    index = read("docs/HISTORICAL_INDEX.md")
    for legacy in ("STATE.md", "DECISIONS.md", "ROADMAP.md", "ROADMAP_STATE.json"):
        assert (DOCS / legacy).is_file() and legacy in index
    assert "git grep" in index and "preserved byte-for-byte" in index


def test_one_non_contradictory_authority_rule_across_agents_active_state_and_ai_rules():
    agents, active, rules = (" ".join(read(f).split()) for f in ("AGENTS.md", "docs/ACTIVE_STATE.md", "docs/AI_RULES.md"))
    for text in (agents, active, rules):
        assert "Authority by domain" in text
    # AGENTS.md and ACTIVE_STATE.md carry the identical four-domain rule text.
    def bullets(text):
        start = text.index("Authority by domain")
        return text[text.index("- *Milestone execution state*", start):text.index("surface the conflict and obtain an explicit owner decision.", start)]
    assert bullets(agents) == bullets(active)
    for domain in ("*Milestone execution state*", "*Capability semantics and authority limits*",
                   "*Compact current-state docs*", "*Preserved `STATE.md` / `ROADMAP.md` / `DECISIONS.md`*"):
        assert domain in bullets(agents)
    assert "no ladder" in active and "no new authority layer" in active and "add **no** authority" in active
    assert "Precedence on conflict" not in active  # the earlier ladder is gone
    assert "operational entrypoint for current state" not in agents


def test_review_corrections_wording_is_bounded():
    text = " ".join(read("docs/ACTIVE_STATE.md").split())
    # live-remote verification needs a fetch / ls-remote, not the local tracking ref alone
    assert "git fetch origin main" in text and "git ls-remote origin refs/heads/main" in text
    assert "local** remote-tracking ref" in text
    assert "Nothing else in repository authority blocks" not in text
    assert "No additional documented blocker is currently known" in text and "must still pass at launch" in text
    for doc in ("docs/ACTIVE_STATE.md", "docs/ROADMAP_CURRENT.md"):
        body = " ".join(read(doc).split())
        assert "always-blocked" not in body and "stay blocked or unknown regardless" not in body
        assert "official_verification" in body and "conditional" in body
    # untracked-path allowances are scoped to the contract that defines them, per checkout
    assert "per checkout" in text and "checkout_cleanliness_contract.py" in text
    assert "CONSUMER_APPROVED_UNTRACKED_PREFIXES" in text and "APPROVED_RUNTIME_EVIDENCE_PREFIXES" in text
    assert "untracked `data/` and `.worktrees/` are approved prefixes" not in text


def test_legacy_authority_formulations_cannot_return():
    files = ["AGENTS.md", "docs/AI_RULES.md"] + [f for f in ACTIVE_SET if f not in ("AGENTS.md",)] + ["docs/HISTORICAL_INDEX.md"]
    forbidden = ("operational cached truth", "owns sequencing", "current execution-state authority",
                 "cached current truth", "Producer operational entrypoint", "the Producer `STATE.md`",
                 "never overrides them.", "STATE.md` is cached")
    for rel in files:
        body = " ".join(read(rel).split())
        for phrase in forbidden:
            assert phrase not in body, (rel, phrase)
    rules = " ".join(read("docs/AI_RULES.md").split())
    rule_4a = rules[rules.index("4a. `docs/NORTH_STAR.md`"):rules.index("## Market-data doctrine")]
    assert "not execution authority" in rule_4a  # NORTH_STAR keeps its non-authoritative role
    assert "Milestone execution state is governed by `ROADMAP_STATE.json`" in rule_4a
    assert "preserved history, rationale and recorded invariants" in rule_4a
    assert "never overrides any of them or this file" in rule_4a
    rule_11 = rules[rules.index("11. `docs/ROADMAP_STATE.json`"):]
    assert "It governs milestone execution state only" in rule_11
    doctrine = " ".join(read("AGENTS.md").split())
    doctrine = doctrine[doctrine.index("## Stable project doctrine"):doctrine.index("## Default lightweight bootstrap")]
    assert "stable owner doctrine" in doctrine and "ACQUIRE BROADLY" in doctrine
    assert "preserved narrative" in doctrine and "Authority by domain" in doctrine
    assert "no compact current-state doc, may silently redefine the doctrine" in doctrine
    assert "surface the conflict instead of following the most recent technical thread by inertia" in doctrine
