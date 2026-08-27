"""official_financial_structural_table/v1 -- structural recognizer for GENERAL-CORPORATE
bilingual / non-form-code financial statement PDFs.

This is a versioned extension of ``official_financial_pdf_page_evidence`` /
``financial_statement_template_recognizer``, not a new architecture.  It is dispatched
only as a FALLBACK when the existing exact-form recognizer (``official_financial_pdf_
page_evidence.discover_tables``, gated on the literal Circular-200 form-code strings
B01-DN/HN, B02-DN/HN, B03-DN/HN) finds zero tables in a retained native-text corporate
PDF -- the stable AAA exact-form path is never touched or reordered.

Real retained evidence (VNM/HPG/PAN 2022-2025 annual reports) shows the blocked
corporate corpus splits into distinct, evidenced structural families rather than one
generic "bilingual" shape:

* ``ROW_MAJOR_WITH_LINE_CODES`` -- one physical row carries label + VAS line code +
  optional note + current/comparative values together (e.g. PAN: "1. Gross revenue ...
  01 32 16,757,498,726,518 13,716,602,098,224").
* ``COLUMN_MAJOR_WITH_LINE_CODES`` -- the PDF's text layer was drawn column-by-column:
  all row labels, then all line codes, then all note refs, then all current-year
  values, then all comparative-year values, as separate parallel runs of equal length
  (e.g. HPG: 19 label lines, then 19 code lines "01".."60", then two 19-line value
  runs).  A naive per-line row walker silently mispairs labels and values on this
  family; it requires positional run reconstruction instead.
* ``ROW_MAJOR_NO_LINE_CODES`` -- IFRS-style bilingual statements with no VAS line code
  at all, label + current + comparative only (e.g. VNM: "Total assets 56,993,245
  54,232,491").

Recognition is evidence-driven and deterministic throughout: statement-family / period-
column / unit-scale recognition reuse the existing generic, already-tested
``financial_statement_template_recognizer`` functions unchanged; only row/value
extraction -- genuinely unhandled by the existing form-code-table-fragment pipeline --
is new here.  Every extracted value still passes through the existing governed
``annual_financial_ocr_materialization.verified_extraction`` citation-proof contract
(raw label and raw value must be literal substrings of the source page text).

TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0.  No logic here is keyed on ticker symbol,
issuer name, hostname, or document SHA; layout-family and anchor tables are keyed only
on canonical-metric name and structural evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from annual_financial_ocr_materialization import parse_accounting_integer, verified_extraction
from financial_statement_template_recognizer import (
    GENERIC_METRIC_RULES,
    RecognizedUnitScale,
    STATEMENT_PATTERNS,
    StatementType,
    _normalize_text,
    recognize_period_column_layout,
    recognize_statement_type,
    recognize_unit_and_scale,
)


VERSION = "official_financial_structural_table/v2"
EXTRACTION_METHOD = "pypdf_native_text_structural_v2"
GEOMETRY_RECOGNIZER_VERSION = "column_major_geometry/v1"

#: The 7-metric AAA/P3-F13 corporate contract, minus total_interest_bearing_debt.
#: Debt's two-component aggregation (GENERIC_DEBT_COMPONENTS) is Vietnamese-anchor-only
#: and its verified_debt_extraction label qualification is stricter than a single-row
#: match; extending it needs its own evidenced anchors and is out of this bounded pass.
CORPORATE_METRICS = (
    "total_assets", "shareholders_equity", "cash_and_equivalents",
    "revenue", "net_income", "operating_cash_flow",
)

_METRIC_CODE: dict[str, str] = {name: str(spec["standard_line_code"]) for name, spec in GENERIC_METRIC_RULES.items()}
_METRIC_STATEMENT: dict[str, StatementType] = {name: spec["statement_type"] for name, spec in GENERIC_METRIC_RULES.items()}

#: Additive English/IFRS-style label anchors, each evidenced from the retained target
#: corpus (see operations-review/retained-official-financial-pdf-extraction-scaleout-
#: v1-20260827/).  These never replace or reorder financial_statement_template_
#: recognizer.GENERIC_METRIC_RULES's own Vietnamese anchors -- they are a separate,
#: purely additive table consulted only by this module's own row matching, so the
#: exact-form AAA path (which never imports this module) is unaffected.
_ENGLISH_ANCHORS: dict[str, tuple[str, ...]] = {
    "revenue": ("net revenue", "revenue"),
    "net_income": ("net profit after tax", "profit after tax attributable to parent", "shareholders of the parent company", "net profit"),
    "operating_cash_flow": (
        "net cash flows from operating activities",
        "net cash generated from operating activities",
        "net cash flow from operating activities",
    ),
    "total_assets": ("total assets",),
    "shareholders_equity": ("total equity", "equity"),
    "cash_and_equivalents": ("cash and cash equivalents",),
}

_VN_TITLE_MARKERS = ("bang can doi", "bao cao ket qua", "bao cao luu chuyen", "bang can boi")
_CONSOLIDATED_LEAD_IN_STOPWORDS = {"the", "a", "an", "on", "in", "of", "comprise", "comprises", "and", "code"}


def _heading_marks_consolidated(page_text: str, statement_type: StatementType) -> bool:
    """Whether this page's OWN statement-title occurrence is explicitly consolidated.

    recognize_statement_type matches the first pattern that appears anywhere in
    STATEMENT_PATTERNS[type]["titles"] tuple order -- since the generic "balance
    sheet" is a literal substring of "consolidated balance sheet" and sits earlier in
    that tuple, its own title_match can never report the consolidated variant even
    when the page literally says "CONSOLIDATED BALANCE SHEET".  This finds the
    left-most occurrence of ANY known title for this statement type in the page (the
    same occurrence recognize_statement_type would have anchored on) and checks only
    a small window immediately around IT for an explicit consolidated/hop-nhat marker
    -- not the whole page (which would also catch an unrelated narrative mention of
    "the consolidated net profit" far away) and not a fixed top-of-page window (some
    filings place the real heading mid-page, sharing it with a highlights summary).
    """
    norm = _normalize_text(page_text)
    best_position = None
    best_title = ""
    for title in STATEMENT_PATTERNS[statement_type]["titles"]:
        position = norm.find(title)
        if position >= 0 and (best_position is None or position < best_position):
            best_position, best_title = position, title
    if best_position is None:
        return False
    window = norm[max(0, best_position - 60):best_position + len(best_title) + 20]
    marker_pos = window.find("consolidated")
    if marker_pos == -1:
        return "hop nhat" in window
    # A real heading opens directly with "CONSOLIDATED ..." (at most a company name or
    # page number precedes it).  An inline cross-reference inside notes prose --
    # "(Code 224 on Consolidated Balance sheet)", "...which comprise the consolidated
    # balance sheet..." -- always has a preposition/article immediately before it.
    lead_in_words = window[:marker_pos].split()
    return not lead_in_words or lead_in_words[-1] not in _CONSOLIDATED_LEAD_IN_STOPWORDS


def _is_front_matter_or_divider_page(page_text: str) -> bool:
    """A table-of-contents / section-divider / audit-opinion page never IS a primary
    statement table, even when it names one -- a TOC page can legitimately list
    "Consolidated balance sheet" as an entry (HPG23 p5), a section divider can list
    the same title as one of several sub-items (HPG23 p77 "PART VII / AUDITED
    FINANCIAL STATEMENTS / 1. / 2. / 3."), and an auditor's opinion narrates "...which
    comprise the consolidated balance sheet as at 31 December..." in prose (HPG23
    p81).  Recognized by the page's OWN heading region, not by statement-type content.
    """
    heading_lines = [line for line in page_text.splitlines() if line.strip()][:6]
    heading_norm = _normalize_text("\n".join(heading_lines))
    if any(marker in heading_norm for marker in ("notes to", "thuyet minh", "contents", "independent auditor", "auditor s report", "kiem toan doc lap")):
        return True
    bare_enumeration_lines = sum(1 for line in heading_lines if re.fullmatch(r"[0-9]{1,2}\.\s*", line.strip()))
    return bare_enumeration_lines >= 2


_DASH_TOKENS = {"-", "–", "—"}
# A rendering artifact seen in some of these PDFs' native text layers inserts a
# spurious space before a thousands-grouping comma (e.g. "37 ,165,930" for
# "37,165,930" -- confirmed on VNM).  The optional \s? absorbs that gap so the WHOLE
# fragmented span is captured as one token, rather than the plain, unspaced pattern
# only matching from the second comma-group onward and silently returning a truncated
# number (e.g. "165,930") as if it were the real value.  parse_accounting_integer
# still requires an exact, space-free match, so a token this regex captures WITH an
# embedded space correctly fails closed as UNPARSEABLE instead of being repaired.
_NUM_TOKEN_RE = re.compile(r"\(?[0-9]{1,3}(?:\s?[.,][0-9]{3})+\)?")
_CODE_LINE_RE = re.compile(r"^\(?[0-9]{1,3}\)?$")
_NOTE_TOKEN_RE = re.compile(r"^[0-9]{1,2}(?:\.[0-9]{1,2})?$")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _anchors_for(metric: str) -> tuple[str, ...]:
    base = tuple(GENERIC_METRIC_RULES[metric]["label_anchors"])
    extra = _ENGLISH_ANCHORS.get(metric, ())
    seen: list[str] = []
    for anchor in base + extra:
        if anchor not in seen:
            seen.append(anchor)
    return tuple(seen)


_ORDINAL_PREFIX_RE = re.compile(r"^(?:[ivxlcdm]{1,4}\.|[0-9]{1,2}\.|[a-z]\)|-)\s*")


def _anchor_matches(norm_line: str, anchor: str) -> bool:
    """A short/generic anchor (<=2 words) must lead the line; a specific one may match anywhere.

    Guards against a bare anchor like "equity" matching a narrower sub-line such as
    "equity attributable to equity holders" ahead of the true total-equity row.  A
    leading list marker ("1. ", "iii.", "a)") is stripped first so a genuinely
    leading anchor like "3.  Net revenue from goods sold ..." still qualifies.

    A single-word anchor additionally requires the very next word to be numeric (a
    value, code, or note reference), not another word -- "Equity 37,165,930" is the
    real total-equity row, but "Equity investments in other entities 26,121,..." is a
    same-anchor-prefixed but semantically different line (PAN's balance sheet has
    both).  A two-word anchor like "net revenue" is specific enough that its own
    legitimate explanatory continuation ("net revenue FROM goods sold ...") must
    still be accepted, so this stricter check is not applied there.
    """
    words = anchor.split()
    if len(words) == 1:
        unprefixed = _ORDINAL_PREFIX_RE.sub("", norm_line, count=1)
        if unprefixed == anchor:
            return True
        if not unprefixed.startswith(anchor + " "):
            return False
        remainder = unprefixed[len(anchor):].lstrip()
        return not remainder or not remainder[0].isalpha()
    if len(words) == 2:
        unprefixed = _ORDINAL_PREFIX_RE.sub("", norm_line, count=1)
        return unprefixed == anchor or unprefixed.startswith(anchor + " ")
    return anchor in norm_line


def _page_map(pages: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    return {int(page["page_number"]): str(page["page_text"]) for page in pages}


def recognize_layout_family(pages: Sequence[Mapping[str, Any]]) -> str:
    """Classify a document's structural layout family from real recognizer evidence.

    Families are derived from the retained target corpus, not invented ahead of
    evidence: NARRATIVE_ONLY_NO_EMBEDDED_STATEMENT (no page recognizes as any
    statement type -- e.g. an annual-report narrative volume whose statements are a
    separate document), NOTES_DOMINANT_WITH_FRONT_STATEMENT_PAGES (the document is
    mostly notes-to-financial-statements text, with at most a few front primary-
    statement pages), BILINGUAL_ENGLISH_TITLED_STATEMENT_TABLE (recognized pages carry
    English-language statement titles rather than Vietnamese form-code titles), or
    OTHER_STRUCTURED_CORPORATE for anything else recognized but not fitting either.
    """
    hits: list[tuple[int, str, str | None, bool]] = []
    notes_pages = 0
    for page in pages:
        text = str(page.get("page_text", ""))
        norm = _normalize_text(text)
        if "thuyet minh" in norm[:600] or "notes to the consolidated financial statements" in norm[:600] or "notes to financial statements" in norm[:600]:
            notes_pages += 1
        statement_type, title, form_code, is_continuation = recognize_statement_type(text)
        if statement_type is not None:
            hits.append((int(page["page_number"]), title, form_code, is_continuation))
    if not hits:
        return "NARRATIVE_ONLY_NO_EMBEDDED_STATEMENT"
    if notes_pages and notes_pages >= max(3, len(pages) * 0.4):
        return "NOTES_DOMINANT_WITH_FRONT_STATEMENT_PAGES"
    english_hits = sum(
        1 for _, title, form_code, _ in hits
        if title and title != "continuation_anchors_match" and not form_code and not any(marker in title for marker in _VN_TITLE_MARKERS)
    )
    if english_hits >= max(1, len(hits) // 2):
        return "BILINGUAL_ENGLISH_TITLED_STATEMENT_TABLE"
    return "OTHER_STRUCTURED_CORPORATE"


def _contiguous_blocks(page_numbers: Sequence[int]) -> list[list[int]]:
    blocks: list[list[int]] = []
    for page_no in sorted(page_numbers):
        if blocks and page_no == blocks[-1][-1] + 1:
            blocks[-1].append(page_no)
        else:
            blocks.append([page_no])
    return blocks


def select_consolidated_block(page_map: Mapping[int, str], statement_type: StatementType) -> tuple[list[int] | None, dict[str, Any]]:
    """Pick the one CONSOLIDATED block for a statement type, or block with an explicit reason.

    Never assumes consolidated scope from being the only block; never picks between
    multiple consolidated-marked blocks (e.g. a consolidated block plus a separate/
    parent-company block of the same statement type in the same filing).
    """
    recognized: dict[int, str] = {}
    for page_no in sorted(page_map):
        statement, title, _form_code, _is_continuation = recognize_statement_type(page_map[page_no])
        if statement == statement_type:
            recognized[page_no] = title
    if not recognized:
        return None, {"state": "STATEMENT_NOT_RECOGNIZED", "reason": f"NO_PAGE_RECOGNIZED_AS_{statement_type.value.upper()}"}
    blocks = _contiguous_blocks(list(recognized))
    consolidated_blocks = []
    for block in blocks:
        marked = False
        for page_no in block:
            if _is_front_matter_or_divider_page(page_map[page_no]):
                continue
            if _heading_marks_consolidated(page_map[page_no], statement_type):
                marked = True
                break
        if marked:
            consolidated_blocks.append(block)
    if len(consolidated_blocks) == 1:
        return consolidated_blocks[0], {"state": "SELECTED", "reason": "SINGLE_CONSOLIDATED_MARKED_BLOCK", "candidate_block_count": len(blocks)}
    if len(consolidated_blocks) > 1:
        # A table-of-contents entry, a narrative page discussing a policy, or a notes
        # paragraph can still carry an exact "consolidated <statement>" phrase near a
        # few incidental numbers without being genuine tabular evidence.  Require the
        # stronger, later-stage bar too: does this specific block ALSO independently
        # resolve real unit/currency AND period-column evidence (recognize_unit_and_
        # scale / recognize_period_column_layout, the same functions the real table
        # extraction itself depends on)?  A heading-only false positive reliably fails
        # this; only genuine statement tables carry both a unit declaration and an
        # unambiguous current/comparative column header.
        structurally_evidenced = [block for block in consolidated_blocks if _block_resolves_unit_and_period(page_map, block, statement_type)]
        if len(structurally_evidenced) == 1:
            return structurally_evidenced[0], {"state": "SELECTED", "reason": "SINGLE_BLOCK_WITH_UNIT_AND_PERIOD_EVIDENCE", "candidate_block_count": len(consolidated_blocks)}
        if not structurally_evidenced:
            return None, {"state": "STATEMENT_FAMILY_AMBIGUOUS", "reason": "MULTIPLE_CONSOLIDATED_MARKED_BLOCKS_NONE_WITH_UNIT_AND_PERIOD_EVIDENCE", "candidate_block_count": len(consolidated_blocks)}
        return None, {"state": "STATEMENT_FAMILY_AMBIGUOUS", "reason": "MULTIPLE_CONSOLIDATED_BLOCKS_WITH_UNIT_AND_PERIOD_EVIDENCE", "candidate_block_count": len(structurally_evidenced)}
    return None, {"state": "STATEMENT_SCOPE_UNPROVEN", "reason": "NO_EXPLICIT_CONSOLIDATED_MARKER_ON_ANY_BLOCK", "candidate_block_count": len(blocks)}


def _resolve_period_layout(page_text: str, statement_type: StatementType, target_period: str):
    """recognize_period_column_layout, tolerant of a bottom-of-page header row.

    recognize_period_column_layout only scans a page's first 30 lines for the
    current/comparative header.  That is correct for a row-major page (the header
    always leads the table), but the column-major layout family (see module
    docstring) draws the whole table as parallel label/code/value runs and only
    states "Code Note 2023 VND 2022 VND" as a short header AFTER all of them --
    genuinely past line 30 on a page with 90+ rows.  Retried against the page's own
    last 30 lines only when the normal top-of-page scan finds nothing; never invents
    an ordering the header text itself does not state.
    """
    try:
        return recognize_period_column_layout(page_text, statement_type, target_period)
    except ValueError:
        pass
    lines = page_text.splitlines()
    if len(lines) <= 30:
        return None
    try:
        return recognize_period_column_layout("\n".join(lines[-30:]), statement_type, target_period)
    except ValueError:
        return None


def _block_resolves_unit_and_period(page_map: Mapping[int, str], block: Sequence[int], statement_type: StatementType) -> bool:
    """Probe whether a candidate block independently carries real table evidence.

    Deliberately reuses the exact functions recognize_structural_statement_tables
    uses for the real table build, so this is never a looser or different bar than
    what final extraction itself requires.
    """
    unit = None
    for page_no in block:
        unit = recognize_unit_and_scale(page_map[page_no]) or _fallback_unit_and_scale(page_map[page_no])
        if unit is not None:
            break
    if unit is None:
        return False
    target_period = _infer_target_period({page_no: page_map[page_no] for page_no in block})
    if target_period is None:
        return False
    return any(_resolve_period_layout(page_map[page_no], statement_type, target_period) is not None for page_no in block)


def _infer_target_period(block_text_by_page: Mapping[int, str]) -> str | None:
    """Infer the filing's target fiscal year from the block's own header-region evidence.

    Deterministic and table-local: scans only the top of each page in the block for
    lines carrying an explicit period anchor (current/prior-year labels, "ended",
    "as at", a closing/opening-balance label, or a dd/mm/yyyy date) and collects the
    4-digit years on those lines.  Never guesses column order -- that remains
    recognize_period_column_layout's job once a target year is established.  Blocks
    (returns None) when zero or more than two distinct plausible years are found.
    """
    candidates: set[int] = set()
    for text in block_text_by_page.values():
        for line in text.splitlines()[:40]:
            norm = _normalize_text(line)
            if not any(anchor in norm for anchor in (
                "nam nay", "nam truoc", "cuoi nam", "dau nam", "current year", "prior year",
                "previous year", "ended", "as at", "closing balance", "opening balance", "31/12",
            )):
                continue
            for year in re.findall(r"20[0-3][0-9]", line):
                candidates.add(int(year))
    if not candidates or len(candidates) > 2:
        return None
    return str(max(candidates))


def _cell_state(token: str | None) -> dict[str, Any]:
    if token is None:
        return {"raw_text": "", "state": "BLANK", "parsed_value": None, "sign": None}
    token = token.strip()
    if token in _DASH_TOKENS:
        return {"raw_text": token, "state": "DASH", "parsed_value": None, "sign": None}
    if not token:
        return {"raw_text": "", "state": "BLANK", "parsed_value": None, "sign": None}
    try:
        value, sign = parse_accounting_integer(token)
    except ValueError:
        return {"raw_text": token, "state": "UNPARSEABLE", "parsed_value": None, "sign": None}
    return {"raw_text": token, "state": "NUMERIC", "parsed_value": value, "sign": sign}


def _extract_note_reference(line: str, label_end: int, value_start: int) -> str | None:
    between = line[label_end:value_start].strip()
    return between if between and _NOTE_TOKEN_RE.fullmatch(between) else None


def _dash_tokens_outside_parens(text: str) -> list[tuple[str, int, int]]:
    """Dash-shaped tokens that are not inside a (...) span.

    A genuine nil/not-applicable value cell is a standalone dash.  A formula
    annotation like "(10 = 01 - 02)" or "(30 = 20 + (21 - 22) + 24 - (25 + 26))" --
    common on the label-only run of a column-major layout (see module docstring) --
    also contains bare "-" characters as arithmetic minus signs; treating one of
    those as a nil cell would silently misreport a formula reference as this row's
    value.  Tracking paren depth is a cheap, reliable way to tell them apart: every
    observed formula annotation is itself fully parenthesized.
    """
    depth = 0
    result: list[tuple[str, int, int]] = []
    for match in re.finditer(r"[()]|(?<![\w.,])[-–—](?![\w.,\d])", text):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            result.append((token, match.start(), match.end()))
    return result


def _row_major_match(block_text_by_page: Mapping[int, str], metric: str) -> dict[str, Any] | None:
    """Row-major: a stitched line window carries the anchor label and >=1 value token."""
    code = _METRIC_CODE[metric]
    anchors = _anchors_for(metric)
    for page_no in sorted(block_text_by_page):
        lines = block_text_by_page[page_no].splitlines()
        for start in range(len(lines)):
            window = [line for line in lines[start:start + 3] if line.strip()]
            if not window:
                continue
            joined = " ".join(part.strip() for part in window)
            norm = _normalize_text(joined)
            matched_anchor = next((anchor for anchor in anchors if _anchor_matches(norm, anchor)), None)
            if matched_anchor is None:
                continue
            # The anchor must open this window, not merely appear somewhere inside it.
            # Without this, a window starting one (unrelated) line early -- e.g.
            # "Current assets 37 ,501,520 ..." immediately followed by "Cash and cash
            # equivalents  2,225,944 ..." -- also satisfies the anchor check once its
            # 3-line join happens to include the real label line, and the FIRST
            # numeric token found would then be the wrong, preceding row's value, not
            # this row's.  Requiring the anchor within the first ~15 characters keeps
            # the window anchored to its own label while still tolerating a short
            # numbered/lettered prefix ("1. Gross revenue ...").
            if norm.find(matched_anchor) > 15:
                continue
            tokens_with_pos = [(match.group(0), match.start(), match.end()) for match in _NUM_TOKEN_RE.finditer(joined)]
            dash_positions = _dash_tokens_outside_parens(joined)
            cells = sorted(tokens_with_pos + dash_positions, key=lambda item: item[1])
            if not cells:
                continue
            has_code = bool(code) and bool(re.search(rf"\b{re.escape(code)}\b", joined))
            note = _extract_note_reference(joined, 0, cells[0][1]) if len(joined[:cells[0][1]].split()) <= 6 else None
            return {
                "page": page_no, "line_text": joined, "matched_anchor": matched_anchor,
                "current_raw": cells[0][0], "comparative_raw": cells[1][0] if len(cells) > 1 else None,
                "has_code": has_code, "note_reference": note, "layout": "row_major",
            }
    return None


def _column_runs(lines: Sequence[str]) -> list[tuple[str, int, int, list[str]]]:
    """Maximal parallel runs of pure line-code lines and pure value lines, in order."""
    runs: list[tuple[str, int, int, list[str]]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if _CODE_LINE_RE.fullmatch(stripped):
            start = index
            items: list[str] = []
            while index < len(lines) and _CODE_LINE_RE.fullmatch(lines[index].strip()):
                items.append(lines[index].strip())
                index += 1
            if len(items) >= 5:
                runs.append(("code", start, index, items))
            continue
        if _NUM_TOKEN_RE.fullmatch(stripped) or stripped in _DASH_TOKENS:
            start = index
            items = []
            while index < len(lines) and (_NUM_TOKEN_RE.fullmatch(lines[index].strip()) or lines[index].strip() in _DASH_TOKENS):
                items.append(lines[index].strip())
                index += 1
            if len(items) >= 5:
                runs.append(("value", start, index, items))
            continue
        index += 1
    return runs


def _column_major_match(block_text_by_page: Mapping[int, str], metric: str) -> dict[str, Any] | None:
    """Column-major: the text layer draws all labels, then all codes, then value runs.

    Trusted only when the code-run and both following value-runs have IDENTICAL
    length (proving positional alignment), and only when an anchor for this metric is
    independently found in the label region preceding the code-run -- position alone
    is never sufficient proof of which row a code belongs to.
    """
    code = _METRIC_CODE.get(metric)
    if not code:
        return None
    anchors = _anchors_for(metric)
    for page_no in sorted(block_text_by_page):
        lines = block_text_by_page[page_no].splitlines()
        runs = _column_runs(lines)
        code_runs = [run for run in runs if run[0] == "code"]
        value_runs = [run for run in runs if run[0] == "value"]
        for run in code_runs:
            _, run_start, run_end, items = run
            if code not in items:
                continue
            position = items.index(code)
            # A value run's start index equals the code run's (exclusive) end index
            # when the two are contiguous -- the normal, expected case (no line sits
            # between the last code and the first value).  ">=" is required, not ">":
            # the latter off-by-one silently excluded every immediately-contiguous
            # value run and could only ever match when something else separated them.
            following = [value_run for value_run in value_runs if value_run[1] >= run_end]
            if len(following) < 2:
                continue
            current_run, comparative_run = following[0], following[1]
            if len(current_run[3]) != len(items) or len(comparative_run[3]) != len(items):
                continue
            label_region_lines = lines[:run_start]
            label_region_norm = _normalize_text("\n".join(label_region_lines))
            matched_anchor = next((anchor for anchor in anchors if anchor in label_region_norm), None)
            if matched_anchor is None:
                continue
            label_line = next((line for line in label_region_lines if matched_anchor in _normalize_text(line)), None)
            if label_line is None:
                continue
            return {
                "page": page_no, "line_text": label_line.strip(), "matched_anchor": matched_anchor,
                "current_raw": current_run[3][position], "comparative_raw": comparative_run[3][position],
                "has_code": True, "note_reference": None, "layout": "column_major",
            }
    return None


def _vertical_tolerance(tokens: Sequence[Mapping[str, Any]]) -> float:
    """Derive a bounded same-baseline tolerance from this page's own token geometry."""
    levels = sorted({float(token["top"]) for token in tokens})
    jitter = [b - a for a, b in zip(levels, levels[1:]) if 0 < b - a <= 4.0]
    if jitter:
        jitter.sort()
        median = jitter[len(jitter) // 2]
        return round(min(3.0, max(0.5, median * 3.0 + 0.25)), 4)
    sizes = sorted(max(0.1, float(token.get("font_size", 1.0))) for token in tokens)
    median_size = sizes[len(sizes) // 2] if sizes else 1.0
    return round(min(3.0, max(0.5, median_size * 0.75)), 4)


def reconstruct_physical_lines(tokens: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Rebuild physical lines from native token geometry, never stream ordering.

    The result preserves raw callback order and x-sorted geometric order.  The
    tolerance is per-page, deterministic, bounded, and included in the contract so
    a later parser revision cannot silently change row grouping.
    """
    usable = [dict(token) for token in tokens if str(token.get("text", "")).strip()]
    tolerance = _vertical_tolerance(usable)
    lines: list[dict[str, Any]] = []
    for token in sorted(usable, key=lambda row: (-float(row["top"]), int(row.get("raw_token_order", 0)))):
        line = next((item for item in lines if abs(float(item["baseline"]) - float(token["top"])) <= tolerance), None)
        if line is None:
            line = {"line_id": len(lines), "baseline": float(token["top"]), "raw_tokens": []}
            lines.append(line)
        line["raw_tokens"].append(token)
    for line in lines:
        geometric = sorted(line["raw_tokens"], key=lambda row: (float(row["x0"]), int(row.get("raw_token_order", 0))))
        line["tokens"] = geometric
        line["text"] = " ".join(str(token["text"]) for token in geometric)
        line["bbox"] = {
            "x0": min(float(token["x0"]) for token in geometric), "x1": max(float(token["x1"]) for token in geometric),
            "top": min(float(token["top"]) for token in geometric), "bottom": max(float(token["bottom"]) for token in geometric),
        }
    lines.sort(key=lambda row: -float(row["baseline"]))
    for index, line in enumerate(lines):
        line["line_id"] = index
    return {"recognizer_version": GEOMETRY_RECOGNIZER_VERSION, "vertical_tolerance": tolerance, "lines": lines}


def _x_clusters(tokens: Sequence[Mapping[str, Any]], gap: float = 35.0) -> list[list[Mapping[str, Any]]]:
    clusters: list[list[Mapping[str, Any]]] = []
    for token in sorted(tokens, key=lambda row: float(row["x0"])):
        if not clusters or float(token["x0"]) - float(clusters[-1][-1]["x0"]) > gap:
            clusters.append([token])
        else:
            clusters[-1].append(token)
    return clusters


def discover_column_bands(lines: Sequence[Mapping[str, Any]], target_period: str) -> dict[str, Any] | None:
    """Discover code/note/value x-bands with explicit two-period header evidence."""
    # Header labels can occupy two nearby physical baselines (year above VND).  This
    # is a semantic header group, not a relaxation of physical-line reconstruction:
    # each component line remains preserved and its total bounded vertical span is
    # recorded below.
    header = None
    for start in range(len(lines)):
        group = [lines[start]]
        for candidate in lines[start + 1:start + 3]:
            if abs(float(candidate["baseline"]) - float(group[0]["baseline"])) <= 8.0:
                group.append(candidate)
        text = " ".join(str(line["text"]) for line in group)
        if "code" in _normalize_text(text) and target_period in text and len(set(re.findall(r"20[0-3][0-9]", text))) >= 2:
            header = {"lines": group, "text": text}
            break
    if header is None:
        return None
    ordered_years = list(dict.fromkeys(re.findall(r"20[0-3][0-9]", str(header["text"]))))
    comparative = next((year for year in ordered_years if year != target_period), None)
    if comparative is None:
        return None
    all_tokens = [token for line in lines for token in line["tokens"]]
    amount_tokens = [token for token in all_tokens if "," in str(token["text"]) or str(token["text"]).strip() in _DASH_TOKENS]
    amount_clusters = [cluster for cluster in _x_clusters(amount_tokens) if len(cluster) >= 3]
    if len(amount_clusters) < 2:
        return None
    first_cluster, second_cluster = amount_clusters[-2:]
    if ordered_years[0] == target_period:
        current_cluster, comparative_cluster = first_cluster, second_cluster
    elif ordered_years[1] == target_period:
        comparative_cluster, current_cluster = first_cluster, second_cluster
    else:  # defensive: target period was required above, so do not infer a fallback.
        return None
    left_edge = min(float(token["x0"]) for token in current_cluster)
    short_numeric = [token for token in all_tokens if _CODE_LINE_RE.fullmatch(str(token["text"]).strip()) and float(token["x0"]) < left_edge]
    short_clusters = [cluster for cluster in _x_clusters(short_numeric, gap=20.0) if len(cluster) >= 3]
    if not short_clusters:
        return None
    code_cluster = short_clusters[-2] if len(short_clusters) >= 2 else short_clusters[-1]
    note_cluster = short_clusters[-1] if len(short_clusters) >= 2 else None
    def band(cluster: Sequence[Mapping[str, Any]]) -> dict[str, float]:
        return {"x0": round(min(float(token["x0"]) for token in cluster) - 2.0, 4), "x1": round(max(float(token["x0"]) for token in cluster) + 2.0, 4)}
    return {
        "recognizer_version": GEOMETRY_RECOGNIZER_VERSION,
        "header_evidence": {"line_ids": [line["line_id"] for line in header["lines"]], "text": header["text"],
                            "bbox": {"x0": min(line["bbox"]["x0"] for line in header["lines"]), "x1": max(line["bbox"]["x1"] for line in header["lines"]),
                                     "top": min(line["bbox"]["top"] for line in header["lines"]), "bottom": max(line["bbox"]["bottom"] for line in header["lines"])}},
        "current_period_label": target_period, "comparative_period_label": comparative,
        "bands": {"line_code": band(code_cluster), "note_reference": band(note_cluster) if note_cluster is not None else None, "current_period_value": band(current_cluster), "comparative_period_value": band(comparative_cluster)},
    }


def _in_band(token: Mapping[str, Any], band: Mapping[str, float] | None) -> bool:
    if band is None:
        return False
    return float(band["x0"]) <= float(token["x0"]) <= float(band["x1"])


def _geometry_column_major_match(page: Mapping[str, Any], metric: str, target_period: str) -> dict[str, Any] | None:
    tokens = page.get("positioned_tokens") or []
    if not tokens:
        return None
    reconstruction = reconstruct_physical_lines(tokens)
    lines = reconstruction["lines"]
    discovered = discover_column_bands(lines, target_period)
    if discovered is None:
        return None
    bands = discovered["bands"]
    if max(bands["current_period_value"]["x0"], bands["comparative_period_value"]["x0"]) <= min(bands["current_period_value"]["x1"], bands["comparative_period_value"]["x1"]):
        return None
    code = _METRIC_CODE.get(metric)
    if not code:
        return None
    # A wrapped label may precede its code/value line by one physical baseline.  The
    # permitted gap is derived from this page's closest distinct baselines, not text
    # similarity or a fixed line count.
    baselines = [float(line["baseline"]) for line in lines]
    steps = [abs(a - b) for a, b in zip(baselines, baselines[1:]) if abs(a - b) >= 6.0]
    continuation_gap = min(steps) * 1.5 if steps else 0.0
    anchors = _anchors_for(metric)
    for index, line in enumerate(lines):
        code_tokens = [token for token in line["tokens"] if _in_band(token, bands["line_code"])]
        if not any(str(token["text"]).strip() == code for token in code_tokens):
            continue
        fragments = [token for token in line["tokens"] if float(token["x0"]) < bands["line_code"]["x0"]]
        if index and continuation_gap:
            prior = lines[index - 1]
            prior_fragments = [token for token in prior["tokens"] if float(token["x0"]) < bands["line_code"]["x0"]]
            prior_has_code_or_value = any(
                _in_band(token, bands["line_code"]) or _in_band(token, bands["current_period_value"]) or _in_band(token, bands["comparative_period_value"])
                for token in prior["tokens"]
            )
            if prior_fragments and not prior_has_code_or_value and abs(float(prior["baseline"]) - float(line["baseline"])) <= continuation_gap:
                fragments = prior_fragments + fragments
        raw_fragments = [str(token["text"]) for token in fragments]
        reconstructed_label = " ".join(raw_fragments)
        norm_label = _normalize_text(reconstructed_label)
        anchor = next((item for item in anchors if _anchor_matches(norm_label, item)), None)
        if anchor is None:
            continue
        current = [token for token in line["tokens"] if _in_band(token, bands["current_period_value"])]
        comparative = [token for token in line["tokens"] if _in_band(token, bands["comparative_period_value"])]
        if any(token in comparative for token in current):
            return None
        if len(current) != 1 or len(comparative) != 1:
            return None
        note = next((str(token["text"]).strip() for token in line["tokens"] if _in_band(token, bands["note_reference"]) and _NOTE_TOKEN_RE.fullmatch(str(token["text"]).strip())), None)
        citation_label = next((fragment for fragment in raw_fragments if anchor in _normalize_text(fragment)), max(raw_fragments, key=len, default=""))
        if not citation_label:
            return None
        return {
            "page": int(page["page_number"]), "line_text": citation_label, "matched_anchor": anchor,
            "current_raw": str(current[0]["text"]), "comparative_raw": str(comparative[0]["text"]),
            "has_code": True, "note_reference": note, "layout": "column_major_geometry",
            "row_object": {"document_sha": page.get("document_sha256"), "page": int(page["page_number"]), "table_id": None,
                "statement_family": None, "row_bbox": line["bbox"], "raw_label_fragments": raw_fragments,
                "reconstructed_label": reconstructed_label, "line_code": code, "note_reference": note,
                "current_period_label": discovered["current_period_label"], "current_raw_value": str(current[0]["text"]),
                "current_value_bbox": {k: current[0][k] for k in ("x0", "x1", "top", "bottom")},
                "comparative_period_label": discovered["comparative_period_label"], "comparative_raw_value": str(comparative[0]["text"]),
                "comparative_value_bbox": {k: comparative[0][k] for k in ("x0", "x1", "top", "bottom")},
                "recognizer_version": GEOMETRY_RECOGNIZER_VERSION, "physical_line_reconstruction": {"vertical_tolerance": reconstruction["vertical_tolerance"], "line_id": line["line_id"]},
                "column_bands": discovered},
        }
    return None


def match_metric_row(block_text_by_page: Mapping[int, str], metric: str, *, positioned_pages: Mapping[int, Mapping[str, Any]] | None = None, target_period: str | None = None) -> dict[str, Any] | None:
    """Dispatch: row-major evidence first, column-major positional reconstruction second."""
    if positioned_pages is not None and target_period is not None:
        for page_no in sorted(positioned_pages):
            match = _geometry_column_major_match(positioned_pages[page_no], metric, target_period)
            if match is not None:
                return match
    return _row_major_match(block_text_by_page, metric) or _column_major_match(block_text_by_page, metric)


_BARE_CURRENCY_LINE_RE = re.compile(r"^(VND|USD)[\s,]*(million|billion|thousand|tri[eệ]u|t[yỷ]|ngh[iì]n)?$", re.IGNORECASE)
_SCALE_WORDS = {"million": 1_000_000, "billion": 1_000_000_000, "thousand": 1_000,
                "trieu": 1_000_000, "ty": 1_000_000_000, "nghin": 1_000}


def _fallback_unit_and_scale(page_text: str) -> RecognizedUnitScale | None:
    """A bare "VND million" / "VND" header-column label, with no "Unit:"/"Đơn vị" word.

    Evidenced from VNM/HPG: these column headers repeat the currency+scale as its own
    standalone line ("31/12/2024 / VND million / 31/12/2023 / VND million") instead of
    a declarative unit line, which the reused recognize_unit_and_scale (requiring the
    literal word unit/đơn vị) never matches.  Tried only when that function finds
    nothing on the table's own pages.
    """
    for line in page_text.splitlines():
        match = _BARE_CURRENCY_LINE_RE.fullmatch(line.strip())
        if not match:
            continue
        scale_key = _normalize_text(match.group(2) or "")
        scale = _SCALE_WORDS.get(scale_key, 1)
        currency = match.group(1).upper()
        return RecognizedUnitScale(currency=currency, unit_scale=scale, unit_label=line.strip(), evidence_text=line.strip())
    return None


def recognize_structural_statement_tables(pages: Sequence[Mapping[str, Any]]) -> tuple[dict[StatementType, dict[str, Any]], list[dict[str, Any]]]:
    """Phase 3/4/5/6: recognize one consolidated table per statement type, or block it.

    Returns (tables_by_type, blocked) where each table dict carries page range,
    statement family, unit/currency evidence, and period-column evidence -- all
    table-local, never borrowed from an unrelated page.
    """
    page_map = _page_map(pages)
    tables: dict[StatementType, dict[str, Any]] = {}
    blocked: list[dict[str, Any]] = []
    for statement_type in StatementType:
        block, selection = select_consolidated_block(page_map, statement_type)
        if block is None:
            blocked.append({"statement_family": statement_type.value, **selection})
            continue
        block_text = {page_no: page_map[page_no] for page_no in block}
        unit = None
        for page_no in block:
            unit = recognize_unit_and_scale(page_map[page_no]) or _fallback_unit_and_scale(page_map[page_no])
            if unit is not None:
                break
        if unit is None:
            blocked.append({"statement_family": statement_type.value, "state": "UNIT_OR_CURRENCY_MISSING_ON_TABLE",
                             "reason": "NO_UNIT_SCALE_EVIDENCE_ON_SELECTED_BLOCK_PAGES", "pages": block})
            continue
        target_period = _infer_target_period(block_text)
        if target_period is None:
            blocked.append({"statement_family": statement_type.value, "state": "PERIOD_YEAR_UNPROVEN",
                             "reason": "ZERO_OR_AMBIGUOUS_YEAR_EVIDENCE_ON_SELECTED_BLOCK_PAGES", "pages": block})
            continue
        period_layout = None
        for page_no in block:
            period_layout = _resolve_period_layout(page_map[page_no], statement_type, target_period)
            if period_layout is not None:
                break
        if period_layout is None:
            blocked.append({"statement_family": statement_type.value, "state": "PERIOD_COLUMN_AMBIGUOUS",
                             "reason": "PERIOD_COLUMN_NOT_RESOLVED_ON_TOP_OR_BOTTOM_OF_ANY_BLOCK_PAGE", "pages": block})
            continue
        heading_line = next((line.strip() for line in page_map[block[0]].splitlines() if line.strip()), "")
        tables[statement_type] = {
            "recognizer_identity": VERSION, "document_identity": None, "page_range": [block[0], block[-1]],
            "pages": block, "statement_family": statement_type.value, "table_heading": heading_line,
            "current_period_column": period_layout.current_period_label,
            "comparative_period_column": period_layout.comparative_period_label,
            "period_header_evidence": period_layout.header_evidence, "target_period": target_period,
            "unit_currency": unit.currency, "unit_scale": unit.unit_scale, "unit_label": unit.unit_label,
            "unit_evidence_text": unit.evidence_text, "continuation_pages": block[1:],
            "statement_scope": "consolidated",
        }
    return tables, blocked


#: Broadened, evidenced English/bilingual self-identification patterns.  Each was
#: found verbatim in the retained target corpus (VNM: "Stock ticker on HOSE: VNM";
#: HPG: "Stock sticker: HPG" / "Stock sticker symbol: HPG" -- the source document's
#: own spelling, not a typo introduced here; PAN: "Securities Symbol PAN", "under the
#: ticker PAN", "stock symbol PAN since").  A caller-supplied ticker is never accepted
#: as proof by itself -- the retained PDF must still state it, exactly like the
#: existing Vietnamese-only document_metadata() invariant this module does not modify.
_TICKER_SELF_STATEMENT_RE = re.compile(
    r"stock\s+ticker\s+on\s+hose:?\s*\n?\s*([A-Z]{3,5})"
    r"|stock\s+sticker(?:\s+symbol)?:?\s*\n?\s*([A-Z]{3,5})"
    r"|securities\s+symbol\s+([A-Z]{3,5})"
    r"|under\s+the\s+ticker\s+([A-Z]{3,5})"
    r"|stock\s+symbol\s+([A-Z]{3,5})\s+since",
    re.IGNORECASE,
)
_AUDIT_ANCHORS = (
    "bao cao kiem toan doc lap", "independent auditor", "report of independent auditor",
    "auditors report", "based on our audit", "opinion on the consolidated financial statements",
)


def structural_document_identity_claims(pages: Sequence[Mapping[str, Any]], ticker: str) -> dict[str, Any]:
    """Bilingual issuer/ticker self-statement and audit-opinion-presence claims.

    Deliberately separate from official_financial_pdf_page_evidence.document_metadata,
    which stays untouched: this is additive evidence used only by the structural
    fallback path, never a relaxation of the existing Vietnamese-only function's own
    AAA-tested behaviour.
    """
    ticker = str(ticker).upper()
    ticker_matched = False
    ticker_evidence = None
    audited = False
    audit_evidence = None
    for page in pages:
        text = str(page.get("page_text", ""))
        if not ticker_matched:
            for match in _TICKER_SELF_STATEMENT_RE.finditer(text):
                found = next(group for group in match.groups() if group)
                if found.upper() == ticker:
                    ticker_matched = True
                    ticker_evidence = {"page": int(page["page_number"]), "text": match.group(0)}
                    break
        if not audited:
            norm = _normalize_text(text)
            anchor = next((a for a in _AUDIT_ANCHORS if a in norm), None)
            if anchor:
                audited = True
                audit_evidence = {"page": int(page["page_number"]), "matched_anchor": anchor}
        if ticker_matched and audited:
            break
    return {
        "ticker_self_stated": ticker_matched, "ticker_evidence": ticker_evidence,
        "audit_or_review_status": "audited" if audited else None, "audit_evidence": audit_evidence,
    }


def _row_source_span(page_text: str, raw_value: str, label: str) -> dict[str, Any]:
    position = page_text.find(raw_value)
    if position < 0:
        return {"start": None, "end": None, "text": label, "coordinate_status": "UNAVAILABLE_FOR_DERIVED_OR_WRAPPED_ROW"}
    start = page_text.rfind("\n", 0, position) + 1
    end = page_text.find("\n", position)
    if end < 0:
        end = len(page_text)
    return {"start": start, "end": end, "text": page_text[start:end], "coordinate_status": "NATIVE_TEXT_LINE"}


def build_structural_candidates(*, document: Mapping[str, Any], pages: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Phase 7-9: recognize tables, parse rows, map canonical identity, build citation-proof candidates.

    Returns (candidates, blocked) in the SAME candidate shape official_financial_pdf_
    page_evidence.extract_candidates already produces, so build_artifact's existing
    panel-fact construction and P3-F13 ingress consume either source unmodified.
    """
    page_map = _page_map(pages)
    layout_family = recognize_layout_family(pages)
    tables, blocked = recognize_structural_statement_tables(pages)
    if not tables:
        return [], blocked or [{"state": "STRUCTURE_INSUFFICIENT", "reason": "NO_STATEMENT_TABLE_RECOGNIZED", "layout_family": layout_family}]

    document_id = document.get("document_id")
    document_sha256 = document["sha256"]
    ticker = str(document["ticker"]).upper()
    official_url = document.get("official_url")
    identity_claims = structural_document_identity_claims(pages, ticker)
    if not identity_claims["ticker_self_stated"]:
        blocked.append({"state": "OFFICIAL_FACT_CANDIDATE_BLOCKED", "reason": "TICKER_SELF_STATEMENT_UNPROVEN", "layout_family": layout_family})
    if identity_claims["audit_or_review_status"] is None:
        blocked.append({"state": "OFFICIAL_FACT_CANDIDATE_BLOCKED", "reason": "AUDIT_OR_REVIEW_STATUS_UNPROVEN", "layout_family": layout_family})
    document_qualified = identity_claims["ticker_self_stated"] and identity_claims["audit_or_review_status"] is not None

    candidates: list[dict[str, Any]] = []
    for metric in CORPORATE_METRICS:
        statement_type = _METRIC_STATEMENT[metric]
        table = tables.get(statement_type)
        if table is None:
            continue
        block_text = {page_no: page_map[page_no] for page_no in table["pages"]}
        positioned_pages = {int(page["page_number"]): page for page in pages if int(page["page_number"]) in table["pages"]}
        match = match_metric_row(block_text, metric, positioned_pages=positioned_pages, target_period=table["target_period"])
        if match is None:
            blocked.append({"statement_family": statement_type.value, "canonical_metric": metric,
                             "state": "STRUCTURE_INSUFFICIENT", "reason": "ROW_NOT_STRUCTURALLY_MATCHED", "pages": table["pages"]})
            continue
        current = _cell_state(match["current_raw"])
        comparative = _cell_state(match.get("comparative_raw"))
        if current["state"] != "NUMERIC":
            blocked.append({"statement_family": statement_type.value, "canonical_metric": metric,
                             "state": "STRUCTURE_INSUFFICIENT", "reason": f"CURRENT_PERIOD_CELL_{current['state']}",
                             "pages": table["pages"], "raw_text": current["raw_text"]})
            continue
        source_page_no = match["page"]
        source_page_text = page_map[source_page_no]
        try:
            extraction = verified_extraction(
                {"document_sha256": document_sha256, "pages": [{"page": source_page_no, "status": "text_available",
                                                                 "text": source_page_text, "document_id": document_id,
                                                                 "document_sha256": document_sha256,
                                                                 "materialization_id": f"structural:{document_sha256}:{source_page_no}",
                                                                 "text_sha256": hashlib.sha256(source_page_text.encode("utf-8")).hexdigest(),
                                                                 "extraction_engine": EXTRACTION_METHOD}]},
                page=source_page_no, raw_label=match["line_text"], raw_value=current["raw_text"],
                unit=table["unit_label"], statement=statement_type.value, visual_source_page_verified=True,
            )
        except ValueError as error:
            blocked.append({"statement_family": statement_type.value, "canonical_metric": metric,
                             "state": "STRUCTURE_INSUFFICIENT", "reason": str(error), "pages": table["pages"]})
            continue
        table_id = _hash({"document": document_sha256, "statement_family": statement_type.value,
                           "pages": table["pages"], "recognizer": VERSION})
        if match.get("row_object") is not None:
            match["row_object"]["table_id"] = table_id
            match["row_object"]["statement_family"] = statement_type.value
            match["row_object"]["unit_currency_lineage"] = {
                "currency": table["unit_currency"], "unit_scale": table["unit_scale"], "unit_evidence_text": table["unit_evidence_text"],
            }
        # verified_extraction's own "normalized_value" is only the parsed displayed
        # integer (e.g. 2,225,944 as printed) -- it does not know the table's unit
        # scale.  The actual base-currency value requires multiplying by unit_scale,
        # exactly like official_financial_pdf_page_evidence's own candidate builder
        # (normalized = value * fact.unit_scale) -- skipping this silently understated
        # every value on a non-1 scale table (confirmed via Phase 13 reconciliation:
        # VNM's "VND million" table produced a value 1,000,000x too small).
        normalized_value = extraction["normalized_value"] * table["unit_scale"]
        candidates.append({
            "ticker": ticker, "canonical_metric": metric, "canonical_mapping_state": "CANONICAL_IDENTITY_EXACT",
            "raw_row_label": match["line_text"], "raw_numeric_text": current["raw_text"],
            "parsed_numeric_value": current["parsed_value"], "normalized_value": normalized_value,
            "currency": table["unit_currency"], "unit_scale": table["unit_scale"], "fiscal_period": table["target_period"],
            "statement_scope": table["statement_scope"], "audit_or_review_status": identity_claims["audit_or_review_status"],
            "document_sha256": document_sha256, "official_url": official_url, "page_number": source_page_no,
            "statement_family": statement_type.value, "table_id": table_id, "table_heading": table["table_heading"],
            "period_column_label": table["current_period_column"], "source_span": _row_source_span(source_page_text, current["raw_text"], match["line_text"]),
            "extraction_method": EXTRACTION_METHOD,
            "qualification_status": "OFFICIAL_FACT_QUALIFIED" if document_qualified else "OFFICIAL_FACT_CANDIDATE_BLOCKED",
            "structural_evidence": {
                "recognizer_identity": VERSION, "layout_family": layout_family, "row_layout": match["layout"],
                "matched_anchor": match["matched_anchor"], "note_reference": match.get("note_reference"),
                "comparative_raw_text": comparative["raw_text"], "comparative_state": comparative["state"],
                "comparative_parsed_value": comparative["parsed_value"],
                "period_header_evidence": table["period_header_evidence"],
                "comparative_period_column": table["comparative_period_column"],
                "unit_evidence_text": table["unit_evidence_text"], "continuation_pages": table["continuation_pages"],
                "row_object": match.get("row_object"),
            },
        })
    return candidates, blocked


def reconcile_against_existing_panel(candidates: Sequence[Mapping[str, Any]], existing_panel: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Phase 13: compare newly qualified structural candidates against the existing
    P3-F13 panel by (ticker, canonical_metric, reporting_period, statement_scope).

    Several of this milestone's target tickers (VNM, HPG, PAN, QNS, GAS) already
    carry OFFICIAL_QUALIFIED P3-F13 facts for these exact identities and periods,
    sourced through an earlier, differently-evidenced route -- not the page/table-
    cited extraction this module performs.  A colliding key is classified
    (EXACT_MATCH / VALUE_CONFLICT / NOT_COMPARABLE) and marked ineligible for
    ingress; it is never merged over the existing fact.  Only a genuinely new key
    (no existing entry at all) is marked eligible -- callers must still route it
    through the existing p3f13_official_financial_evidence_scaleout.
    merge_document_qualified_facts_into_panel ingress themselves; this function only
    classifies, it never mutates a panel.
    """
    existing_by_key: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    for issuer in existing_panel.get("issuers", []):
        ticker = str(issuer.get("issuer_identity", {}).get("ticker", "")).upper()
        for fact in issuer.get("facts", []):
            if fact.get("qualification_state") != "QUALIFIED":
                continue
            key = (ticker, str(fact.get("canonical_metric")), str(fact.get("reporting_period")), fact.get("statement_scope"))
            existing_by_key[key] = fact
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("qualification_status") != "OFFICIAL_FACT_QUALIFIED":
            continue
        key = (str(candidate["ticker"]).upper(), str(candidate["canonical_metric"]), str(candidate["fiscal_period"]), candidate["statement_scope"])
        existing = existing_by_key.get(key)
        new_value = candidate["normalized_value"]
        if existing is None:
            records.append({
                "ticker": key[0], "canonical_metric": key[1], "reporting_period": key[2], "statement_scope": key[3],
                "classification": "NOT_COMPARABLE_NEW_KEY", "existing_value": None, "new_value": new_value,
                "new_document_sha256": candidate["document_sha256"], "eligible_for_ingress": True,
            })
            continue
        existing_value = existing.get("value")
        classification = "EXACT_MATCH" if existing_value == new_value else "VALUE_CONFLICT"
        records.append({
            "ticker": key[0], "canonical_metric": key[1], "reporting_period": key[2], "statement_scope": key[3],
            "classification": classification, "existing_value": existing_value, "new_value": new_value,
            "existing_source_lineage": existing.get("source_lineage"), "new_document_sha256": candidate["document_sha256"],
            "eligible_for_ingress": False,
        })
    return records
