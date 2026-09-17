"""Private, local-only portfolio workbook contracts.

This module is intentionally outside the Daily, Dashboard, and AI-handoff paths.
It turns an owner-maintained workbook into deterministic private artifacts below
``%USERPROFILE%/.stocklookup/portfolio``.  No workbook data is written to the
repository, and the existing explicit-portfolio risk envelope remains the only
consumer that may later evaluate supplied exposures.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping


EVENT_LEDGER_CONTRACT = "portfolio_event_ledger/v1"
SNAPSHOT_CONTRACT = "portfolio_snapshot/v1"
POLICY_CONTRACT = "portfolio_policy/v1"
# PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: additive, local-only per-account and
# aggregate contracts layered alongside the existing single ``account_snapshot/v1`` (which is
# never removed or reinterpreted -- see ``_account_snapshot_contract``). A workbook with no
# recognizable multi-account structure produces zero ``investment_account_context/v1`` records
# and a ``NOT_PROVIDED`` aggregate; every existing single-account consumer is unaffected.
INVESTMENT_ACCOUNT_CONTEXT_CONTRACT = "investment_account_context/v1"
INVESTMENT_ACCOUNTS_PORTFOLIO_CONTEXT_CONTRACT = "investment_accounts_portfolio_context/v1"
# The one stable identity a single, alias-less AccountSnapshot row (every pre-existing real or
# fixture workbook) resolves to -- never invented per-row when more than one row lacks an alias,
# which instead becomes ACCOUNT_ALIAS_MISSING_FOR_MULTI_ACCOUNT_ROW (see
# ``_investment_account_contexts``).
LEGACY_UNSPECIFIED_ACCOUNT_ID = "LEGACY_UNSPECIFIED_ACCOUNT"
# A ledger event or position-level account-attribution row whose source workbook row carries no
# recognizable per-row account column value. Never retrospectively guessed or backfilled.
ACCOUNT_ATTRIBUTION_UNRESOLVED = "ACCOUNT_ATTRIBUTION_UNRESOLVED"
# PERSONAL_DECISION_INPUT_TRUTH_V1: the required distinction between HISTORICAL_EVENT_LEDGER_STATE
# (the raw, always-preserved event trail -- see build_event_ledger) and CURRENT_POSITION_TRUTH (what
# a position row below is allowed to assert about presence *today*). CURRENT_CONFIRMED is the only
# status a consumer may treat as an actual current holding; CURRENT_POSITION_UNRESOLVED means the
# reconstructed quantity is not trustworthy (e.g. a SELL exceeded the derived running holding) and
# must never be read as a phantom holding, positive or otherwise. CLOSED means reconciliation is
# clean and the position is genuinely flat.
CURRENT_POSITION_STATUS_CONFIRMED = "CURRENT_CONFIRMED"
CURRENT_POSITION_STATUS_CLOSED = "CLOSED"
CURRENT_POSITION_STATUS_UNRESOLVED = "CURRENT_POSITION_UNRESOLVED"
SYSTEM_DEFAULT_POLICY_CONTRACT = "system_default_policy/v1"
IMPORT_MANIFEST_CONTRACT = "portfolio_import_manifest/v1"
# V2 -> V3: real-workbook schema adaptation (new header aliases, the
# headerless legacy margin fallback, and the zero-events fail-closed check).
# V3 -> V4: dividend row-level refinement discovered from the real V3 import's
# own residual warnings (record/ex-rights date fallback when the execution
# date is blank; prefer the consistently-populated net-of-tax cash amount
# column over the frequently-blank nominal one). Each revision's own prior
# attempt -- including a failed one -- must never be silently overwritten; a
# new layout version creates its own immutable revision alongside it instead.
# V4 -> V5 (PERSONAL_DECISION_INPUT_TRUTH_V1): CURRENT_POSITION_TRUTH schema change -- every
# position row now carries `current_position_status` and `current_quantity` is withheld (None)
# whenever that status is CURRENT_POSITION_UNRESOLVED, instead of the prior version's stale
# positive quantity. A V4-layout snapshot predates this contract and must never be silently
# reinterpreted in place; re-running import_workbook against an unchanged real workbook lands in
# a new V5 layout directory instead of conflicting with the frozen V4 one.
# V5 -> V6 (PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1): every ledger event now carries a
# `source_account_id` field, every position now carries an additive `account_attribution` list,
# and two new artifacts (``investment_account_context/v1`` per account, plus the
# ``investment_accounts_portfolio_context/v1`` aggregate) are materialized alongside the unchanged
# single-account ``account_snapshot/v1``. A V5-layout snapshot predates this schema and must never
# be silently reinterpreted in place; a fresh import against an unchanged real workbook lands in a
# new V6 layout directory instead of conflicting with the frozen V5 one.
IMPORT_LAYOUT_VERSION = "PORTFOLIO_CONTEXT_IMPORT_LAYOUT_V6"
CURRENT_COST_BASIS_METHOD = "WEIGHTED_AVERAGE_CARRYING_COST"
LIFETIME_BREAKEVEN_METHOD = "LIFETIME_NET_CASH_OUTFLOW_PER_CURRENT_SHARE"
REPOSITORY_ROOT = Path(__file__).resolve().parent


class PortfolioImportError(ValueError):
    """A private workbook cannot be interpreted without an explicit disposition."""


def default_portfolio_root() -> Path:
    """The sole default local storage root; it is deliberately outside Git."""
    user_profile = os.environ.get("USERPROFILE")
    return Path(user_profile) / ".stocklookup" / "portfolio" if user_profile else Path.home() / ".stocklookup" / "portfolio"


def default_workbook_path() -> Path:
    return default_portfolio_root() / "portfolio_input.xlsx"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(kind: str, value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _normal(value: Any) -> str:
    # Vietnamese d/D (U+0111/U+0110) has no NFKD compatibility decomposition to
    # plain d/D -- unlike every other Vietnamese diacritic, it would otherwise
    # be silently dropped entirely by the combining-mark strip below rather
    # than folded, corrupting real header labels (e.g. "Hanh dong" would lose
    # its d and could collide with an unrelated label).
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    text = re.sub(r"[^0-9,\.\-()]", "", text)
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if not text:
        return None
    if "," in text and "." in text:
        # The rightmost separator is the decimal mark; the other is grouping.
        last_comma, last_dot = text.rfind(","), text.rfind(".")
        if last_comma > last_dot:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        tail = text.rsplit(",", 1)[1]
        text = text.replace(",", "") if len(tail) == 3 else text.replace(",", ".")
    elif "." in text:
        tail = text.rsplit(".", 1)[1]
        text = text.replace(".", "") if len(tail) == 3 else text
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return -result if negative and result > 0 else result


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rendered = format(value.normalize(), "f")
    return "0" if rendered in {"-0", ""} else rendered


def _date(value: Any) -> str | None:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def _truthy_cells(row: Iterable[Any]) -> bool:
    return any(value not in (None, "") for value in row)


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "tradedate", "transactiondate", "ngay", "ngaygd", "ngaygiaodich", "ngaythuchien"),
    # A corporate-action row's defining date is only reliably filled in on
    # "Ngay DKCC" (record date) or "Ngay GDKHQ" (ex-rights date) until the
    # action actually settles, at which point "Ngay thuc hien" (the primary
    # "date" alias above) is filled in too -- confirmed empirically against
    # the real workbook's own column-presence pattern (record/ex-rights dates
    # populated on rows where the execution date column is still blank).
    # _dividend_events() falls back through these only when "date" is absent;
    # they are never a second, competing definition of the same field.
    "date_record": ("ngaydkcc",),
    "date_exrights": ("ngaygdkhq",),
    "ticker": ("ticker", "symbol", "stockcode", "securitycode", "mack", "machungkhoan", "ma", "cophieu"),
    # "hanh dong" (Action) and "loai su kien" (Event Type) are the same generic
    # side/category slot as "action"/"type" above, just in the owner's own
    # language; "loai su kien" additionally drives the stock-vs-cash dividend
    # token match in _dividend_events (e.g. a value containing "co phieu").
    "side": ("side", "action", "type", "tradetype", "buysell", "muaban", "giaodich", "hanhdong", "loaisukien"),
    # "KL khop" (matched/filled quantity) and "Gia khop" (matched/filled price)
    # are the owner's actually-executed trade columns; the sibling "KL dat"/
    # "Gia dat" (order-placed, not necessarily filled as requested) are
    # deliberately not aliased here so the parser never prefers a requested
    # order over what was actually executed.
    "quantity": ("quantity", "qty", "volume", "shares", "sharequantity", "sl", "soluong", "klkhop"),
    "price": ("price", "tradeprice", "unitprice", "gia", "giagiao dich", "giagiaodich", "giakhop"),
    # "Gia tri khop" (matched trade value, pre-fee/tax) is the gross analogue of
    # "amount"; it is listed before "Thanh tien" is even needed because a
    # column that already carries the label the code's own netamount-recovery
    # branch expects (see amount_header handling in _trade_events) is safer
    # than back-computing gross from a net-settled figure. "So tien" is Money's
    # own generic cash-movement amount label.
    "amount": ("amount", "value", "totalamount", "cashamount", "netamount", "thanhtien", "giatri", "total", "giatrikhop", "sotien"),
    "fee": ("fee", "fees", "commission", "brokerage", "phi", "phigiaodich", "phigd"),
    "tax": ("tax", "taxes", "withholdingtax", "thue", "thuetncn"),
    # "So tien thuc nhan tru thue" (amount actually received, net of tax) is
    # listed first because it is the real workbook's consistently-populated
    # final cash figure for a dividend row; "Tien co tuc" (a nominal/declared
    # amount label) is frequently left blank on real rows where the net
    # figure is filled in instead, confirmed by the real workbook's own
    # column-presence pattern.  Column order (not alias order) decides which
    # wins when a row happens to populate both.
    "cash_amount": ("cashdividend", "dividendamount", "cashamount", "amount", "thanhtien", "giatri", "tiencotuc", "sotienthucnhantruthue"),
    "cash_per_share": ("cashpershare", "dividendpershare", "cophieutienmatmoicophieu"),
    # "So CK duoc nhan/duoc mua" is the owner's already-settled received/bought
    # share count for a corporate-action row (the figure actually added to the
    # position); the sibling "So CK huong quyen" (theoretical rights
    # entitlement) is deliberately not aliased here -- it stays an informational,
    # non-authoritative annotation, never a reconciliation input, per the
    # approved fractional-entitlement-is-not-a-mismatch semantics.
    "stock_quantity": ("stockquantity", "bonusshares", "stockdividendshares", "sharedividend", "cophieunhan", "soluongcophieu", "sockduocnhanduocmua"),
    "key": ("key", "field", "metric", "name", "parameter", "chi tieu", "chitieu"),
    "value": ("value", "amount", "number", "gia tri", "giatri"),
    # A per-row brokerage account identifier already present on some real Trade/Dividend/Money
    # rows (e.g. "So tai khoan" / "Tai khoan"). This is an independent identifier namespace from
    # AccountSnapshot's own `account_alias` (see ACCOUNT_IDENTITY_FIELDS below) -- the two are
    # never cross-referenced or assumed equal, only ever compared by exact string match.
    "source_account": ("account", "accountid", "accountnumber", "taikhoan", "sotaikhoan"),
}
FIELD_ALIAS_NORMALS = {field: {_normal(alias) for alias in aliases} for field, aliases in FIELD_ALIASES.items()}

ACCOUNT_FIELDS = {
    "as_of_date": ("asofdate", "asof", "snapshotdate", "ngaychot", "ngay"),
    "currency": ("currency", "basecurrency", "tiente", "donvitien"),
    "cash_available": ("cashavailable", "cashbalance", "cash", "tienmat", "tiensan sang", "cashinvestable"),
    "cash_reserved": ("cashreserved", "reservedcash", "tienphongtoa", "tiencho"),
    # Cash and securities receivables are immediately-usable-cash's own
    # distinct, non-overlapping concept: a workbook that separately reports
    # them must never have their value folded into cash_available.
    "receivable_cash": ("receivablecash",),
    "receivable_dividends": ("receivabledividends",),
    "margin_debt": ("margindebt", "currentmargindebt", "marginloan", "currentmarginloan", "marginbalance", "nodu", "nodmargin"),
    "margin_available_minimum": ("marginavailableminimum", "minmarginavailable", "minimumavailablemargin", "marginavailabilitymin", "marginavailablemin", "hanmucmarginconlaitoithieu", "sucmuatoithieu"),
    "margin_available_maximum": ("marginavailablemaximum", "maxmarginavailable", "maximumavailablemargin", "marginavailabilitymax", "marginavailablemax", "hanmucmarginconlaitoida", "sucmuatoida"),
    "annual_margin_rate_percent": ("annualmarginratepercent", "annualmarginrate", "marginratepercent", "margininterestrate", "laisuatmargin", "laivaymarginphantram", "marginratepapct"),
    "accrued_margin_interest": ("accruedmargininterest", "margininterest", "laivaymargin", "laitrich"),
    # "broker_nav" is the broker-reported NAV; a separately, deterministically
    # computed NAV (if one is ever added) is a distinct successor field, per
    # the approved "broker and computed NAV may coexist" semantics -- this
    # field is never treated as anything other than the broker's own figure.
    "net_asset_value": ("netassetvalue", "nav", "taisanrong", "brokernav"),
    "gross_market_value": ("grossmarketvalue", "marketvalue", "giatrithitruong"),
}
# PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: identity-only fields that make a single
# AccountSnapshot row one candidate brokerage account rather than the sole implicit account.
# Deliberately excludes a bare "account"/"tai khoan" alias -- that generic token is reserved for
# FIELD_ALIASES["source_account"]'s own, independent per-row event identifier namespace.
ACCOUNT_IDENTITY_FIELDS = {
    "account_alias": ("accountalias", "accountid", "accountname", "tentaikhoan"),
    "broker": ("broker", "brokername", "congtyck", "ctck", "securitiescompany"),
    "account_type": ("accounttype", "loaitaikhoan", "accountkind"),
}
# The new per-account contract's own monetary/date field name -> the pre-existing ACCOUNT_FIELDS
# key it reuses (same header aliases, same semantics). ``broker_reported_nav`` and
# ``broker_reported_securities_market_value`` are the milestone's own spec names for what
# ACCOUNT_FIELDS already calls ``net_asset_value``/``gross_market_value``.
INVESTMENT_ACCOUNT_FIELD_SOURCE = {
    "cash_available": "cash_available",
    "cash_reserved": "cash_reserved",
    "receivable_cash": "receivable_cash",
    "receivable_dividends": "receivable_dividends",
    "margin_debt": "margin_debt",
    "margin_available_minimum": "margin_available_minimum",
    "margin_available_maximum": "margin_available_maximum",
    "annual_margin_rate_percent": "annual_margin_rate_percent",
    "accrued_margin_interest": "accrued_margin_interest",
    "broker_reported_nav": "net_asset_value",
    "broker_reported_securities_market_value": "gross_market_value",
}
INVESTMENT_ACCOUNT_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    **ACCOUNT_IDENTITY_FIELDS,
    "as_of_date": ACCOUNT_FIELDS["as_of_date"],
    "currency": ACCOUNT_FIELDS["currency"],
    **{new: ACCOUNT_FIELDS[old] for new, old in INVESTMENT_ACCOUNT_FIELD_SOURCE.items()},
}
POLICY_FIELDS = {
    "as_of_date": ACCOUNT_FIELDS["as_of_date"],
    "currency": ACCOUNT_FIELDS["currency"],
    "risk_budget_per_investment_decision_to_nav": ("riskbudgetperinvestmentdecisiontonav", "riskbudgetperdecision", "riskbudgettonav", "ngansachruimoiquyetdinh", "riskbudgetperdealpctnav"),
    "max_single_position_weight": ("maxsinglepositionweight", "maxsinglenameweight", "tytrongtoidamotma", "maxsinglenamepctnav"),
    "max_gross_exposure_to_nav": ("maxgrossexposuretonav", "maxgrossleverage", "tongphoinhiemtoida"),
    "max_margin_debt_to_nav": ("maxmargindebttonav", "maxmarginratio", "marginno toida", "marginnotoida", "maxmargindebtpctnav"),
    "max_sector_weight": ("maxsectorweight", "tytrongnganhtoida", "maxsectorpctnav"),
    "minimum_cash_reserve_to_nav": ("minimumcashreservetonav", "mincashreservetonav", "minimumcashreserve", "tienmatdutoithieutonnav", "mincashreservepctnav"),
    "max_margin_rate_percent_for_new_leveraged_exposure": ("maxmarginratepercentfornewleveragedexposure", "maxmarginratefornewleverage", "maxnewleveragemarginrate", "laisuatmarginmaxchodonbaymoi"),
    "max_ticker_financing_cost": ("maxtickerfinancingcost", "maxstockfinancingcost", "laivaymatotoida"),
    "max_account_margin_cost": ("maxaccountmargincost", "maxmargininterest", "laivaytaikhoantoida"),
    # PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1 additions (2026-09-09): probe/tactical-margin
    # policy defaults, owner-overridable through this same workbook sheet like every other
    # field above. Additive only -- no existing field's recognition or default changes.
    "probe_risk_budget_multiplier": ("proberiskbudgetmultiplier", "probesizemultiplier", "hesotigioihanrurochothudo"),
    "tactical_margin_holding_days": ("tacticalmarginholdingdays", "marginholdingdays", "songgiuvitheky"),
    "min_net_reward_risk_for_margin": ("minnetrewardriskformargin", "minrewardriskratiomargin", "tylethuongruitoithieuchomargin"),
    "strong_net_reward_risk_for_max_margin": ("strongnetrewardriskformaxmargin", "strongrewardriskratiomargin", "tylethuongruimanhchomargintoida"),
    "max_financing_cost_fraction_of_gross_upside": ("maxfinancingcostfractionofgrossupside", "maxfinancingcostfractionupside", "tylechiphilaivaytoidatrenloinhuan"),
}

# Monetary fields are VND because the workbook field contract says so.  The
# importer deliberately never inspects Excel number formatting or magnitude to
# guess a currency or rescale a numeric cell.
ACCOUNT_FIELD_SEMANTICS = {
    "as_of_date": "ISO_DATE",
    "currency": "ISO_CURRENCY_CODE",
    "cash_available": "VND",
    "cash_reserved": "VND",
    "receivable_cash": "VND",
    "receivable_dividends": "VND",
    "margin_debt": "VND",
    "margin_available_minimum": "VND",
    "margin_available_maximum": "VND",
    "annual_margin_rate_percent": "PERCENT_PER_ANNUM_NUMBER",
    "accrued_margin_interest": "VND",
    "net_asset_value": "VND",
    "gross_market_value": "VND",
}
INVESTMENT_ACCOUNT_FIELD_SEMANTICS: dict[str, str] = {
    "account_alias": "TEXT_IDENTITY",
    "broker": "TEXT_IDENTITY",
    "account_type": "TEXT_IDENTITY",
    "as_of_date": "ISO_DATE",
    "currency": "ISO_CURRENCY_CODE",
    **{new: ACCOUNT_FIELD_SEMANTICS[old] for new, old in INVESTMENT_ACCOUNT_FIELD_SOURCE.items()},
}
POLICY_FIELD_SEMANTICS = {
    "as_of_date": "ISO_DATE",
    "currency": "ISO_CURRENCY_CODE",
    "risk_budget_per_investment_decision_to_nav": "NAV_FRACTION",
    "max_single_position_weight": "NAV_FRACTION",
    "max_gross_exposure_to_nav": "NAV_FRACTION",
    "max_margin_debt_to_nav": "NAV_FRACTION",
    "max_sector_weight": "NAV_FRACTION",
    "minimum_cash_reserve_to_nav": "NAV_FRACTION",
    "max_margin_rate_percent_for_new_leveraged_exposure": "PERCENT_PER_ANNUM_NUMBER",
    "max_ticker_financing_cost": "VND",
    "max_account_margin_cost": "VND",
    "probe_risk_budget_multiplier": "UNIT_FRACTION_OF_NORMAL_RISK_BUDGET",
    "tactical_margin_holding_days": "CALENDAR_DAYS_INTEGER",
    "min_net_reward_risk_for_margin": "RATIO",
    "strong_net_reward_risk_for_max_margin": "RATIO",
    "max_financing_cost_fraction_of_gross_upside": "UNIT_FRACTION",
}
# V1 -> V2 (PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1, 2026-09-09): five new probe/tactical-
# margin defaults added below. The version string itself must change, not just the dict content
# -- ``_import_layout()`` folds ``SYSTEM_DEFAULT_POLICY_VERSION`` into its own identity, and an
# already-materialized immutable ``portfolio_snapshot_v1.json`` at a V1 layout directory must
# never silently gain five new effective-policy fields under an unchanged version string. A
# fresh ``import_workbook()`` re-run against the same, unchanged real workbook now lands in a new
# V2 layout directory instead of conflicting with the frozen V1 one.
SYSTEM_DEFAULT_POLICY_VERSION = "SYSTEM_DEFAULT_POLICY_V2"
SYSTEM_DEFAULT_POLICY_FIELDS = {
    "risk_budget_per_investment_decision_to_nav": "0.01",
    "max_single_position_weight": "0.30",
    "max_sector_weight": "0.45",
    "max_gross_exposure_to_nav": "1.15",
    "max_margin_debt_to_nav": "0.15",
    "minimum_cash_reserve_to_nav": "0.05",
    "max_margin_rate_percent_for_new_leveraged_exposure": "15.0",
    # PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1 additions (2026-09-09). Additive only: every
    # field above is untouched, so a caller that only ever read the pre-existing seven fields
    # sees no behavior change.
    "probe_risk_budget_multiplier": "0.50",
    "tactical_margin_holding_days": "30",
    "min_net_reward_risk_for_margin": "2.0",
    "strong_net_reward_risk_for_max_margin": "3.0",
    "max_financing_cost_fraction_of_gross_upside": "0.20",
}


def _field_for_header(value: Any, aliases: Mapping[str, Iterable[str]]) -> str | None:
    normalized = _normal(value)
    for field, candidates in aliases.items():
        if normalized in {_normal(candidate) for candidate in candidates}:
            return field
    return None


def _header_map(sheet: Any, *, candidates: Mapping[str, Iterable[str]], required: set[str], limit: int = 30) -> tuple[int, dict[str, int]] | None:
    for row_index, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, limit), values_only=True), start=1):
        mapping: dict[str, int] = {}
        for column_index, value in enumerate(row, start=1):
            field = _field_for_header(value, candidates)
            if field and field not in mapping:
                mapping[field] = column_index
        if required.issubset(mapping):
            return row_index, mapping
    return None


def _cell(row: tuple[Any, ...], mapping: Mapping[str, int], field: str) -> Any:
    index = mapping.get(field)
    return None if index is None or index > len(row) else row[index - 1]


def _ticker(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"[A-Z0-9.\-]{1,16}", text) else None


def _event_identity(event: Mapping[str, Any]) -> str:
    return "portfolio_event:" + _identity("portfolio_event", event)["artifact_sha256"]


def _event(*, event_type: str, effective_date: str, source_sheet: str, source_row: int, ticker: str | None = None, quantity: Decimal | None = None, gross_amount: Decimal | None = None, fee: Decimal | None = None, tax: Decimal | None = None, note: str | None = None, monetary_currency: str | None = None, monetary_unit_basis: str | None = None, source_account_id: str | None = None) -> dict[str, Any]:
    body = {
        "event_type": event_type,
        "effective_date": effective_date,
        "ticker": ticker,
        "quantity": _number(quantity),
        "gross_amount": _number(gross_amount),
        "fee": _number(fee),
        "tax": _number(tax),
        "source": {"sheet": source_sheet, "row": source_row},
        "note_class": note,
        "monetary_currency": monetary_currency,
        "monetary_unit_basis": monetary_unit_basis,
        # PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: the row's own account column value
        # (FIELD_ALIASES["source_account"]), never retrospectively assigned when the row carries
        # none -- see ACCOUNT_ATTRIBUTION_UNRESOLVED.
        "source_account_id": source_account_id,
    }
    body["event_identity"] = _event_identity(body)
    return body


def _account_id(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _side(value: Any) -> str | None:
    text = _normal(value)
    if text in {"buy", "b", "mua", "mua vao", "muavao"} or "buy" in text or "mua" in text:
        return "BUY"
    if text in {"sell", "s", "ban", "banra"} or "sell" in text or "ban" in text:
        return "SELL"
    return None


def _trade_events(sheet: Any, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    header = _header_map(sheet, candidates=FIELD_ALIASES, required={"date", "ticker", "side", "quantity"})
    if header is None:
        warnings.append({"code": "TRADE_HEADER_UNRECOGNIZED", "sheet": sheet.title})
        return []
    header_row, mapping = header
    events = []
    for source_row, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        if not _truthy_cells(row):
            continue
        effective_date, ticker, event_type = _date(_cell(row, mapping, "date")), _ticker(_cell(row, mapping, "ticker")), _side(_cell(row, mapping, "side"))
        quantity, price, amount = _decimal(_cell(row, mapping, "quantity")), _decimal(_cell(row, mapping, "price")), _decimal(_cell(row, mapping, "amount"))
        fee, tax = _decimal(_cell(row, mapping, "fee")) or Decimal(0), _decimal(_cell(row, mapping, "tax")) or Decimal(0)
        if not effective_date or not ticker or not event_type or quantity is None or quantity <= 0:
            warnings.append({"code": "TRADE_ROW_INVALID", "sheet": sheet.title, "row": source_row})
            continue
        amount_header = _normal(sheet.cell(header_row, mapping["amount"]).value) if "amount" in mapping else ""
        if amount is None:
            gross = quantity * price if price is not None else None
        elif amount_header == "netamount":
            # A labelled net amount already includes transaction costs.  Recover
            # the gross trade value before recording fees/tax separately so that
            # neither a buy nor a sell double-counts them.
            gross = amount - fee - tax if event_type == "BUY" else amount + fee + tax
        else:
            gross = amount
        if gross is None or gross < 0 or fee < 0 or tax < 0:
            warnings.append({"code": "TRADE_CASHFLOW_UNRESOLVED", "sheet": sheet.title, "row": source_row})
            continue
        source_account_id = _account_id(_cell(row, mapping, "source_account"))
        events.append(_event(event_type=event_type, effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, quantity=quantity, gross_amount=gross, fee=fee, tax=tax, source_account_id=source_account_id))
    return events


def _dividend_events(sheet: Any, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    header = _header_map(sheet, candidates=FIELD_ALIASES, required={"date", "ticker"})
    if header is None:
        warnings.append({"code": "DIVIDEND_HEADER_UNRECOGNIZED", "sheet": sheet.title})
        return []
    header_row, mapping = header
    events = []
    for source_row, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        if not _truthy_cells(row):
            continue
        # A corporate-action row may only carry its record/ex-rights date
        # until settlement fills in the execution date; never fabricate one
        # date from another, only fall back to an earlier, already-real
        # lifecycle date when the primary one is genuinely absent.
        effective_date = (
            _date(_cell(row, mapping, "date"))
            or _date(_cell(row, mapping, "date_record"))
            or _date(_cell(row, mapping, "date_exrights"))
        )
        ticker = _ticker(_cell(row, mapping, "ticker"))
        event_hint = _normal(_cell(row, mapping, "side"))
        stock_quantity = _decimal(_cell(row, mapping, "stock_quantity"))
        # ``Cash Amount`` is also a generic ``amount`` alias.  Prefer the
        # dividend-specific header when present, then use the generic amount
        # field rather than treating a valid received dividend as absent.
        cash_amount = _decimal(_cell(row, mapping, "cash_amount"))
        if cash_amount is None:
            cash_amount = _decimal(_cell(row, mapping, "amount"))
        if cash_amount is None:
            per_share, quantity = _decimal(_cell(row, mapping, "cash_per_share")), _decimal(_cell(row, mapping, "quantity"))
            cash_amount = per_share * quantity if per_share is not None and quantity is not None else None
        if not effective_date or not ticker:
            warnings.append({"code": "DIVIDEND_ROW_INVALID", "sheet": sheet.title, "row": source_row})
            continue
        source_account_id = _account_id(_cell(row, mapping, "source_account"))
        stock_like = stock_quantity is not None or any(token in event_hint for token in ("stock", "bonus", "share", "co phieu", "cophieu"))
        if stock_like:
            if stock_quantity is None or stock_quantity <= 0:
                warnings.append({"code": "STOCK_DISTRIBUTION_QUANTITY_UNRESOLVED", "sheet": sheet.title, "row": source_row})
                continue
            events.append(_event(event_type="STOCK_DISTRIBUTION", effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, quantity=stock_quantity, gross_amount=Decimal(0), source_account_id=source_account_id))
        elif cash_amount is not None and cash_amount >= 0:
            events.append(_event(event_type="CASH_DIVIDEND", effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, gross_amount=cash_amount, source_account_id=source_account_id))
        else:
            warnings.append({"code": "CASH_DIVIDEND_AMOUNT_UNRESOLVED", "sheet": sheet.title, "row": source_row})
    return events


def _money_events(sheet: Any, warnings: list[dict[str, Any]], *, margin: bool = False) -> list[dict[str, Any]]:
    header = _header_map(sheet, candidates=FIELD_ALIASES, required={"date", "amount"})
    if header is None:
        warnings.append({"code": "MARGIN_HEADER_UNRECOGNIZED" if margin else "MONEY_HEADER_UNRECOGNIZED", "sheet": sheet.title})
        return []
    header_row, mapping = header
    events = []
    for source_row, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        if not _truthy_cells(row):
            continue
        effective_date, amount = _date(_cell(row, mapping, "date")), _decimal(_cell(row, mapping, "amount"))
        ticker, hint = _ticker(_cell(row, mapping, "ticker")), _normal(_cell(row, mapping, "side"))
        if not effective_date or amount is None:
            warnings.append({"code": "MARGIN_ROW_INVALID" if margin else "MONEY_ROW_INVALID", "sheet": sheet.title, "row": source_row})
            continue
        if margin:
            event_type = "TICKER_FINANCING_COST" if ticker else "ACCOUNT_MARGIN_COST"
        elif ticker and any(token in hint for token in ("fee", "tax", "commission", "phi", "thue")):
            event_type = "TICKER_FEE_OR_TAX_CASHFLOW"
        else:
            event_type = "MONEY_MOVEMENT"
        retained_amount = amount if event_type == "MONEY_MOVEMENT" else abs(amount)
        events.append(_event(
            event_type=event_type,
            effective_date=effective_date,
            source_sheet=sheet.title,
            source_row=source_row,
            ticker=ticker,
            gross_amount=retained_amount,
            note="OWNER_REPORTED_CASHFLOW",
            monetary_currency="VND",
            monetary_unit_basis="WORKBOOK_FIELD_IDENTITY_VND_NO_FORMAT_OR_MAGNITUDE_INFERENCE",
            source_account_id=_account_id(_cell(row, mapping, "source_account")),
        ))
    return events


def _legacy_positional_margin_events(sheet: Any, *, date_column: int = 2, amount_column: int = 3, note_column: int = 4) -> list[dict[str, Any]]:
    """A headerless legacy margin ledger: fixed date/amount/note columns with
    no labelled header row at all.

    Used only as a fallback in ``build_event_ledger`` when the ``margin``
    sheet has no recognizable label header and no account-snapshot-style
    key/value fields -- every other sheet, and this one when it does carry a
    header, is always matched by label, never by bare column position.  A
    row is treated as a real cash-movement record only when its date column
    parses as a date AND its amount column parses as a number; this
    correctly skips a trailing summary/total row (whose date-column cell is
    a text label instead) without needing to recognize that text.  A
    non-empty free-text remark is retained as the event's ``note_class`` only
    for the reconciliation trail; the movement itself is intentionally
    always classified as ``MONEY_MOVEMENT`` and never a financing-cost or
    account-margin-cost event, because deposits, loan draws, and debt
    repayments described in the owner's own notes are real cash movements,
    not interest expense, and forcing them into a cost category from a free
    text hint would misrepresent the ledger rather than merely leave it
    unclassified.
    """
    events = []
    for source_row, row in enumerate(sheet.iter_rows(min_row=1, values_only=True), start=1):
        if not _truthy_cells(row):
            continue
        date_value = row[date_column - 1] if date_column <= len(row) else None
        amount_value = row[amount_column - 1] if amount_column <= len(row) else None
        effective_date, amount = _date(date_value), _decimal(amount_value)
        if not effective_date or amount is None:
            continue
        events.append(_event(
            event_type="MONEY_MOVEMENT",
            effective_date=effective_date,
            source_sheet=sheet.title,
            source_row=source_row,
            gross_amount=amount,
            note="OWNER_REPORTED_CASHFLOW",
            monetary_currency="VND",
            monetary_unit_basis="WORKBOOK_FIELD_IDENTITY_VND_NO_FORMAT_OR_MAGNITUDE_INFERENCE",
        ))
    return events


def _optional_contract(sheet: Any | None, *, contract_version: str, fields: Mapping[str, Iterable[str]], field_semantics: Mapping[str, str], label: str, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {field: None for field in fields}
    semantics = {
        field: {
            "unit_or_format": field_semantics.get(field, "UNSPECIFIED"),
            "value_interpretation": "WORKBOOK_FIELD_IDENTITY_NO_CELL_FORMAT_OR_MAGNITUDE_INFERENCE",
        }
        for field in fields
    }
    if sheet is None:
        body = {"schema_version": contract_version.replace("/", "_"), "contract_version": contract_version, "status": "NOT_PROVIDED", "fields": values, "field_semantics": semantics, "source": None}
        return {**body, **_identity(label, body)}
    header = _header_map(sheet, candidates=fields, required=set(), limit=10)
    if header is not None and header[1]:
        header_row, mapping = header
        row = next((candidate for candidate in sheet.iter_rows(min_row=header_row + 1, values_only=True) if _truthy_cells(candidate)), None)
        if row is not None:
            for field, index in mapping.items():
                values[field] = _cell(row, mapping, field)
    if not any(value is not None for value in values.values()):
        # A two-column ``field/value`` form is equally supported for human workbooks.
        key_value_header = _header_map(sheet, candidates={"key": FIELD_ALIASES["key"], "value": FIELD_ALIASES["value"]}, required={"key", "value"}, limit=20)
        if key_value_header is not None:
            header_row, mapping = key_value_header
            for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
                if not _truthy_cells(row):
                    continue
                normalized_key = _normal(_cell(row, mapping, "key"))
                for field, aliases in fields.items():
                    if normalized_key in {_normal(alias) for alias in aliases}:
                        values[field] = _cell(row, mapping, "value")
    normalized: dict[str, Any] = {}
    for field, value in values.items():
        if field == "as_of_date":
            normalized[field] = _date(value)
        elif field == "currency":
            normalized[field] = str(value).strip().upper() if value not in (None, "") else None
        else:
            normalized[field] = _number(_decimal(value))
    provided = any(value is not None for value in normalized.values())
    if not provided:
        warnings.append({"code": f"{label.upper()}_FIELDS_ABSENT", "sheet": sheet.title})
    body = {"schema_version": contract_version.replace("/", "_"), "contract_version": contract_version, "status": "PROVIDED" if provided else "NOT_PROVIDED", "fields": normalized, "field_semantics": semantics, "source": {"sheet": sheet.title} if provided else None}
    return {**body, **_identity(label, body)}


def _system_default_policy() -> dict[str, Any]:
    """Materialize the versioned system defaults without inventing owner input."""
    body = {
        "schema_version": "system_default_policy_v1",
        "contract_version": SYSTEM_DEFAULT_POLICY_CONTRACT,
        "policy_version": SYSTEM_DEFAULT_POLICY_VERSION,
        "status": "ACTIVE_SYSTEM_DEFAULTS",
        "default_fields": SYSTEM_DEFAULT_POLICY_FIELDS,
        "field_semantics": {field: POLICY_FIELD_SEMANTICS[field] for field in SYSTEM_DEFAULT_POLICY_FIELDS},
        "authority_boundary": {
            "applies_only_when_owner_field_absent": True,
            "owner_value_overrides_default_per_field": True,
            "not_an_automatic_sell_or_trade_instruction": True,
        },
    }
    return {**body, **_identity("system_default_policy", body)}


def _import_layout() -> dict[str, Any]:
    """Version the private artifact layout so a corrective never overwrites prior immutable output."""
    body = {
        "layout_version": IMPORT_LAYOUT_VERSION,
        "artifact_contracts": [
            EVENT_LEDGER_CONTRACT,
            SNAPSHOT_CONTRACT,
            POLICY_CONTRACT,
            SYSTEM_DEFAULT_POLICY_CONTRACT,
            "account_snapshot/v1",
            INVESTMENT_ACCOUNT_CONTEXT_CONTRACT,
            INVESTMENT_ACCOUNTS_PORTFOLIO_CONTEXT_CONTRACT,
            IMPORT_MANIFEST_CONTRACT,
        ],
        "system_default_policy_version": SYSTEM_DEFAULT_POLICY_VERSION,
    }
    return {**body, **_identity("portfolio_import_layout", body)}


def _effective_policy(owner_policy: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep raw owner values and individually resolve only documented defaults."""
    system_default_policy = _system_default_policy()
    owner_fields = dict(owner_policy.get("fields") or {})
    defaults = system_default_policy["default_fields"]
    effective_fields: dict[str, Any] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for field in POLICY_FIELDS:
        owner_value = owner_fields.get(field)
        system_value = defaults.get(field)
        if owner_value is not None:
            effective_value, source = owner_value, "OWNER_WORKBOOK"
        elif system_value is not None:
            effective_value, source = system_value, SYSTEM_DEFAULT_POLICY_VERSION
        else:
            effective_value, source = None, "UNAVAILABLE_NO_OWNER_OR_SYSTEM_DEFAULT"
        effective_fields[field] = effective_value
        provenance[field] = {
            "owner_supplied_value": owner_value,
            "system_default_value": system_value,
            "effective_value": effective_value,
            "effective_source": source,
            "unit_or_format": POLICY_FIELD_SEMANTICS[field],
        }
    owner_defaultable_count = sum(owner_fields.get(field) is not None for field in defaults)
    if owner_defaultable_count == 0:
        status = "SYSTEM_DEFAULTS_APPLIED"
    elif owner_defaultable_count == len(defaults):
        status = "OWNER_SUPPLIED_DEFAULTABLE_LIMITS"
    else:
        status = "MIXED_OWNER_AND_SYSTEM_DEFAULTS"
    body = {
        "schema_version": "portfolio_policy_v1",
        "contract_version": POLICY_CONTRACT,
        "status": status,
        "owner_policy_status": owner_policy.get("status"),
        "owner_policy_identity": owner_policy.get("artifact_identity"),
        "owner_policy_source": owner_policy.get("source"),
        "owner_supplied_fields": owner_fields,
        "effective_fields": effective_fields,
        # ``fields`` remains the policy that a future consumer must use; the
        # unmodified owner values and their provenance are retained above.
        "fields": effective_fields,
        "field_provenance": provenance,
        "system_default_policy_identity": system_default_policy["artifact_identity"],
        "system_default_policy_version": SYSTEM_DEFAULT_POLICY_VERSION,
        "authority_boundary": {
            "owner_values_override_system_defaults_per_field": True,
            "existing_positions_above_policy_caps_are_not_automatic_sell_instructions": True,
            "decision_and_risk_sizing_are_successor_scope": "PORTFOLIO_AWARE_DECISION_AND_RISK_SIZING_V1",
        },
    }
    return {**body, **_identity("portfolio_policy", body)}, system_default_policy


def _has_account_snapshot_fields(sheet: Any | None) -> bool:
    """Recognize account-labelled fields without mistaking a margin ledger date for a snapshot."""
    if sheet is None:
        return False
    header = _header_map(sheet, candidates=ACCOUNT_FIELDS, required=set(), limit=10)
    if header is not None and any(field not in {"as_of_date", "currency"} for field in header[1]):
        return True
    key_value_header = _header_map(sheet, candidates={"key": FIELD_ALIASES["key"], "value": FIELD_ALIASES["value"]}, required={"key", "value"}, limit=20)
    if key_value_header is None:
        return False
    header_row, mapping = key_value_header
    for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        field = _field_for_header(_cell(row, mapping, "key"), ACCOUNT_FIELDS)
        if field not in {None, "as_of_date", "currency"}:
            return True
    return False


def _account_snapshot_contract(account_sheet: Any | None, margin_sheet: Any | None, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer the dedicated sheet but reuse distinctly labelled legacy margin fields."""
    dedicated = _optional_contract(
        account_sheet,
        contract_version="account_snapshot/v1",
        fields=ACCOUNT_FIELDS,
        field_semantics=ACCOUNT_FIELD_SEMANTICS,
        label="dedicated_account_snapshot",
        warnings=warnings,
    )
    legacy_margin = None
    if margin_sheet is not None and _has_account_snapshot_fields(margin_sheet):
        legacy_margin = _optional_contract(
            margin_sheet,
            contract_version="account_snapshot/v1",
            fields=ACCOUNT_FIELDS,
            field_semantics=ACCOUNT_FIELD_SEMANTICS,
            label="legacy_margin_account_snapshot",
            warnings=warnings,
        )
    candidates = [candidate for candidate in (dedicated, legacy_margin) if candidate and candidate.get("status") == "PROVIDED"]
    fields: dict[str, Any] = {field: None for field in ACCOUNT_FIELDS}
    field_provenance: dict[str, dict[str, Any]] = {
        field: {"selected_source": None, "value_origin": "UNAVAILABLE"}
        for field in ACCOUNT_FIELDS
    }
    sources: list[str] = []
    for candidate in candidates:
        sheet_name = ((candidate.get("source") or {}).get("sheet"))
        if sheet_name:
            sources.append(sheet_name)
        for field, value in (candidate.get("fields") or {}).items():
            if value is None:
                continue
            if fields[field] is None:
                fields[field] = value
                field_provenance[field] = {"selected_source": sheet_name, "value_origin": "OWNER_WORKBOOK_FIELD"}
            elif fields[field] != value:
                warnings.append({"code": "ACCOUNT_SNAPSHOT_FIELD_CONFLICT", "field": field, "preferred_source": sources[0] if sources else "ACCOUNT_SNAPSHOT"})
    provided = any(value is not None for value in fields.values())
    body = {
        "schema_version": "account_snapshot_v1",
        "contract_version": "account_snapshot/v1",
        "status": "PROVIDED" if provided else "NOT_PROVIDED",
        "fields": fields,
        "field_provenance": field_provenance,
        "field_semantics": {
            field: {
                "unit_or_format": ACCOUNT_FIELD_SEMANTICS[field],
                "value_interpretation": "WORKBOOK_FIELD_IDENTITY_NO_CELL_FORMAT_OR_MAGNITUDE_INFERENCE",
            }
            for field in ACCOUNT_FIELDS
        },
        "source": {"sheets": sources} if sources else None,
        "authority_boundary": {
            "margin_availability_is_not_margin_debt": True,
            "dedicated_account_snapshot_precedes_legacy_margin_fields_on_conflict": True,
            "cash_available_excludes_receivable_cash_and_receivable_dividends": True,
        },
    }
    return {**body, **_identity("account_snapshot", body)}


# ── PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: per-account and aggregate contracts ──────
# Additive alongside `_account_snapshot_contract` above (never replaces it): every existing
# single-account consumer keeps reading `account_snapshot/v1` unchanged.

_INVESTMENT_ACCOUNT_FIELD_INTERPRETATION = "WORKBOOK_FIELD_IDENTITY_NO_CELL_FORMAT_OR_MAGNITUDE_INFERENCE"


def _investment_account_field_rows(sheet: Any | None) -> list[dict[str, Any]]:
    """Every truthy AccountSnapshot data row, unlike `_optional_contract`'s single-row read
    (`next(... for row in ... if truthy)`), which would silently drop every row after the first."""
    if sheet is None:
        return []
    header = _header_map(sheet, candidates=INVESTMENT_ACCOUNT_FIELD_CANDIDATES, required=set(), limit=10)
    if header is None:
        return []
    header_row, mapping = header
    if not any(field not in {"as_of_date", "currency"} for field in mapping):
        # Mirrors `_has_account_snapshot_fields`'s guard: matching only as_of/currency is not a
        # recognizable account-fields header at all (e.g. an unrelated date/currency column).
        return []
    rows: list[dict[str, Any]] = []
    for source_row, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        if not _truthy_cells(row):
            continue
        raw = {field: _cell(row, mapping, field) for field in INVESTMENT_ACCOUNT_FIELD_CANDIDATES}
        if not any(value not in (None, "") for value in raw.values()):
            continue
        rows.append({"source_row": source_row, "raw": raw})
    return rows


def _investment_account_contexts(sheet: Any | None, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One ``investment_account_context/v1`` record per real AccountSnapshot row.

    A single alias-less row (every pre-existing real or fixture workbook) resolves to the one
    stable ``LEGACY_UNSPECIFIED_ACCOUNT_ID`` -- Section 6's required legacy-import compatibility.
    More than one alias-less row is genuinely ambiguous (which is "the" legacy account?) and is
    never guessed: each gets its own row-qualified identity plus a reconciliation warning.
    """
    rows = _investment_account_field_rows(sheet)
    if not rows:
        return []
    unaliased_rows = [row for row in rows if not _account_id(row["raw"].get("account_alias"))]
    accounts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        raw, source_row = row["raw"], row["source_row"]
        alias = _account_id(raw.get("account_alias"))
        if alias:
            account_id, account_id_basis = alias, "OWNER_SUPPLIED_ACCOUNT_ALIAS"
        elif len(unaliased_rows) == 1:
            account_id, account_id_basis = LEGACY_UNSPECIFIED_ACCOUNT_ID, "LEGACY_UNSPECIFIED_SINGLE_ACCOUNT"
        else:
            account_id, account_id_basis = f"UNSPECIFIED_ACCOUNT_ROW_{source_row}", "ACCOUNT_ALIAS_MISSING_AMBIGUOUS_MULTI_ROW"
            warnings.append({"code": "ACCOUNT_ALIAS_MISSING_FOR_MULTI_ACCOUNT_ROW", "sheet": sheet.title, "row": source_row})
        if account_id in seen_ids:
            warnings.append({"code": "DUPLICATE_ACCOUNT_ALIAS", "sheet": sheet.title, "row": source_row})
            continue
        seen_ids.add(account_id)
        fields: dict[str, Any] = {}
        for field in INVESTMENT_ACCOUNT_FIELD_CANDIDATES:
            if field == "account_alias":
                continue
            value = raw.get(field)
            if field == "as_of_date":
                fields[field] = _date(value)
            elif field in ("broker", "account_type"):
                fields[field] = str(value).strip() if value not in (None, "") else None
            elif field == "currency":
                fields[field] = str(value).strip().upper() if value not in (None, "") else None
            else:
                fields[field] = _number(_decimal(value))
        body = {
            "schema_version": "investment_account_context_v1",
            "contract_version": INVESTMENT_ACCOUNT_CONTEXT_CONTRACT,
            "account_id": account_id,
            "account_id_basis": account_id_basis,
            "status": "PROVIDED",
            "fields": fields,
            "field_semantics": {
                field: {"unit_or_format": INVESTMENT_ACCOUNT_FIELD_SEMANTICS[field], "value_interpretation": _INVESTMENT_ACCOUNT_FIELD_INTERPRETATION}
                for field in fields
            },
            "source": {"sheet": sheet.title, "row": source_row},
            "authority_boundary": {
                "margin_availability_is_not_margin_debt": True,
                "broker_reported_nav_is_not_independently_computed": True,
                "not_a_position_sizing_or_investment_recommendation": True,
            },
        }
        accounts.append({**body, **_identity("investment_account_context", body)})
    return accounts


_AGGREGATE_TOTAL_FROM_FIELD = {
    "cash_available": "total_broker_cash",
    "cash_reserved": "total_reserved_cash",
    "margin_debt": "total_margin_debt",
    "broker_reported_nav": "total_broker_reported_nav",
    "broker_reported_securities_market_value": "total_broker_reported_securities_market_value",
}
_INVESTMENT_ACCOUNTS_AGGREGATE_AUTHORITY_BOUNDARY = {
    "sums_only_same_as_of_date_and_currency_qualified_accounts": True,
    "total_is_unavailable_not_zero_when_any_qualified_account_omits_the_field": True,
    "broker_reported_nav_is_never_independently_recomputed_here": True,
    "not_a_position_sizing_or_investment_recommendation": True,
    "local_private_only_never_producer_dashboard_or_public_ai_handoff": True,
}


def _accounts_aggregate(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic ``investment_accounts_portfolio_context/v1``.

    Never sums across accounts with inconsistent as-of dates or currencies (fails the whole
    aggregate closed with ``MULTI_ACCOUNT_AS_OF_MISMATCH``/``MULTI_ACCOUNT_CURRENCY_MISMATCH``
    rather than silently mixing a stale and a current snapshot), and never sums a field for which
    any as-of-qualified account is missing a value (a total is ``None`` -- UNKNOWN -- not a
    manufactured partial figure).
    """
    if not accounts:
        body = {
            "schema_version": "investment_accounts_portfolio_context_v1",
            "contract_version": INVESTMENT_ACCOUNTS_PORTFOLIO_CONTEXT_CONTRACT,
            "status": "NOT_PROVIDED",
            "reason_codes": ["NO_INVESTMENT_ACCOUNT_CONTEXT_AVAILABLE"],
            "account_count": 0,
            "account_ids": [],
            "as_of_dates": {},
            "as_of_consistency": "NOT_APPLICABLE_NO_ACCOUNTS",
            "currency_consistency": "NOT_APPLICABLE_NO_ACCOUNTS",
            "totals": {},
            "total_field_basis": {},
            "account_identities": [],
            "authority_boundary": _INVESTMENT_ACCOUNTS_AGGREGATE_AUTHORITY_BOUNDARY,
        }
        return {**body, **_identity("investment_accounts_portfolio_context", body)}

    as_of_by_account = {account["account_id"]: account["fields"].get("as_of_date") for account in accounts}
    currency_by_account = {account["account_id"]: account["fields"].get("currency") for account in accounts}
    distinct_as_of = {value for value in as_of_by_account.values() if value is not None}
    distinct_currency = {value for value in currency_by_account.values() if value is not None}
    as_of_consistent = len(distinct_as_of) <= 1
    currency_consistent = len(distinct_currency) <= 1
    consistent = as_of_consistent and currency_consistent
    reason_codes: list[str] = []
    if not as_of_consistent:
        reason_codes.append("MULTI_ACCOUNT_AS_OF_MISMATCH")
    if not currency_consistent:
        reason_codes.append("MULTI_ACCOUNT_CURRENCY_MISMATCH")

    def _sum_field(field: str) -> tuple[str | None, dict[str, Any]]:
        if not consistent:
            return None, {"status": "UNAVAILABLE", "reason": reason_codes[0]}
        values = {account["account_id"]: account["fields"].get(field) for account in accounts}
        missing = sorted(account_id for account_id, value in values.items() if value is None)
        if missing:
            return None, {"status": "UNAVAILABLE", "reason": "INCOMPLETE_ACCOUNT_COVERAGE_FOR_FIELD", "accounts_missing_field": missing}
        total = sum((Decimal(value) for value in values.values()), Decimal(0))
        return _number(total), {"status": "AVAILABLE", "contributing_accounts": sorted(values)}

    totals: dict[str, str | None] = {}
    total_field_basis: dict[str, dict[str, Any]] = {}
    for field, total_name in _AGGREGATE_TOTAL_FROM_FIELD.items():
        totals[total_name], total_field_basis[total_name] = _sum_field(field)

    # `total_receivables` is the milestone's single aggregate figure for the two distinct
    # per-account receivable fields; it is available only when both constituent totals are.
    cash_receivable_total, cash_receivable_basis = _sum_field("receivable_cash")
    dividend_receivable_total, dividend_receivable_basis = _sum_field("receivable_dividends")
    if cash_receivable_total is not None and dividend_receivable_total is not None:
        totals["total_receivables"] = _number(Decimal(cash_receivable_total) + Decimal(dividend_receivable_total))
        total_field_basis["total_receivables"] = {
            "status": "AVAILABLE",
            "constituents": {"receivable_cash": cash_receivable_basis, "receivable_dividends": dividend_receivable_basis},
        }
    else:
        totals["total_receivables"] = None
        total_field_basis["total_receivables"] = {
            "status": "UNAVAILABLE",
            "reason": reason_codes[0] if reason_codes else "INCOMPLETE_RECEIVABLE_CONSTITUENT_COVERAGE",
            "constituents": {"receivable_cash": cash_receivable_basis, "receivable_dividends": dividend_receivable_basis},
        }

    body = {
        "schema_version": "investment_accounts_portfolio_context_v1",
        "contract_version": INVESTMENT_ACCOUNTS_PORTFOLIO_CONTEXT_CONTRACT,
        "status": "AGGREGATED" if consistent else "PARTIAL_MULTI_ACCOUNT_MISMATCH",
        "reason_codes": reason_codes,
        "account_count": len(accounts),
        "account_ids": sorted(as_of_by_account),
        "as_of_dates": as_of_by_account,
        "as_of_consistency": "CONSISTENT" if as_of_consistent else "MULTI_ACCOUNT_AS_OF_MISMATCH",
        "currency_consistency": "CONSISTENT" if currency_consistent else "MULTI_ACCOUNT_CURRENCY_MISMATCH",
        "totals": totals,
        "total_field_basis": total_field_basis,
        "account_identities": [
            {
                "account_id": account["account_id"],
                "broker": account["fields"].get("broker"),
                "account_type": account["fields"].get("account_type"),
                "as_of_date": account["fields"].get("as_of_date"),
                "artifact_identity": account["artifact_identity"],
            }
            for account in accounts
        ],
        "authority_boundary": _INVESTMENT_ACCOUNTS_AGGREGATE_AUTHORITY_BOUNDARY,
    }
    return {**body, **_identity("investment_accounts_portfolio_context", body)}


_ACCOUNT_ATTRIBUTION_EVENT_TYPES = frozenset({"BUY", "SELL", "STOCK_DISTRIBUTION"})


def _position_account_attribution(events: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Ticker -> per-account current-quantity lineage, additive to (never a replacement for) the
    existing global per-ticker CURRENT_POSITION_TRUTH in `_snapshot_from_ledger`.

    Only ``source_account_id``-bearing BUY/SELL/STOCK_DISTRIBUTION events ever populate a named
    account bucket; every other event falls into ``ACCOUNT_ATTRIBUTION_UNRESOLVED``. A ticker held
    in two accounts keeps two separate rows -- never collapsed into one -- and a ledger with no
    account identity anywhere is never retroactively assigned one.
    """
    per_ticker: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for event in events:
        event_type, ticker = event.get("event_type"), event.get("ticker")
        if not ticker or event_type not in _ACCOUNT_ATTRIBUTION_EVENT_TYPES:
            continue
        account_id = event.get("source_account_id") or ACCOUNT_ATTRIBUTION_UNRESOLVED
        bucket = per_ticker[ticker].setdefault(account_id, {
            "quantity": Decimal(0), "purchase_count": 0, "sale_count": 0, "accounting_blocked": False,
        })
        quantity = _decimal(event.get("quantity")) or Decimal(0)
        if event_type == "BUY":
            bucket["quantity"] += quantity
            bucket["purchase_count"] += 1
        elif event_type == "STOCK_DISTRIBUTION":
            bucket["quantity"] += quantity
        elif event_type == "SELL":
            bucket["sale_count"] += 1
            if quantity > bucket["quantity"]:
                # Mirrors the global reconciliation rule: once an account-level SELL exceeds its
                # own derived running holding, that account's quantity is never trustworthy again.
                bucket["accounting_blocked"] = True
                continue
            bucket["quantity"] -= quantity
    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, accounts in per_ticker.items():
        rows = []
        for account_id, state in sorted(accounts.items()):
            if account_id == ACCOUNT_ATTRIBUTION_UNRESOLVED:
                status = "ACCOUNT_ATTRIBUTION_UNRESOLVED"
            elif state["accounting_blocked"]:
                status = "ACCOUNT_LEVEL_RECONCILIATION_BLOCKED"
            else:
                status = "ATTRIBUTED"
            rows.append({
                "account_id": account_id,
                "attribution_status": status,
                "current_quantity": None if status != "ATTRIBUTED" else _number(state["quantity"]),
                "purchase_count": state["purchase_count"],
                "sale_count": state["sale_count"],
            })
        result[ticker] = rows
    return result


def _total_quantity_hint(sheet: Any | None, warnings: list[dict[str, Any]]) -> dict[str, Decimal]:
    if sheet is None:
        return {}
    header = _header_map(sheet, candidates=FIELD_ALIASES, required={"ticker", "quantity"})
    if header is None:
        warnings.append({"code": "TOTAL_VIEW_HINT_UNUSABLE", "sheet": sheet.title})
        return {}
    header_row, mapping = header
    result: dict[str, Decimal] = {}
    for source_row, row in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        ticker, quantity = _ticker(_cell(row, mapping, "ticker")), _decimal(_cell(row, mapping, "quantity"))
        if ticker is None or quantity is None:
            continue
        if ticker in result:
            warnings.append({"code": "TOTAL_VIEW_HINT_DUPLICATE_TICKER", "sheet": sheet.title, "row": source_row})
            continue
        result[ticker] = quantity
    return result


def _sheet_by_normalized_name(workbook: Any, name: str) -> Any | None:
    expected = _normal(name)
    return next((sheet for sheet in workbook.worksheets if _normal(sheet.title) == expected), None)


def build_event_ledger(*, workbook_path: Path, workbook_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read only the workbook and return ledger plus private optional contracts."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency availability is environmental
        raise PortfolioImportError("OPENPYXL_REQUIRED_FOR_PORTFOLIO_WORKBOOK") from exc
    workbook = load_workbook(workbook_path, read_only=True, data_only=False)
    warnings: list[dict[str, Any]] = []
    sheets = { _normal(sheet.title): sheet for sheet in workbook.worksheets }
    trade = _sheet_by_normalized_name(workbook, "Trade")
    dividend = _sheet_by_normalized_name(workbook, "Dividend")
    money = _sheet_by_normalized_name(workbook, "Money")
    margin = _sheet_by_normalized_name(workbook, "margin")
    if trade is None:
        warnings.append({"code": "TRADE_SHEET_MISSING"})
    events = []
    if trade is not None:
        events.extend(_trade_events(trade, warnings))
    if dividend is not None:
        events.extend(_dividend_events(dividend, warnings))
    if money is not None:
        events.extend(_money_events(money, warnings))
    margin_has_account_fields = _has_account_snapshot_fields(margin)
    if margin is not None:
        margin_event_header = _header_map(margin, candidates=FIELD_ALIASES, required={"date", "amount"})
        if margin_event_header is not None:
            events.extend(_money_events(margin, warnings, margin=True))
        elif not margin_has_account_fields:
            # No recognizable label header and no account-snapshot-style
            # key/value fields either: try the known headerless legacy
            # ledger shape (fixed date/amount/note columns) before giving up.
            legacy_events = _legacy_positional_margin_events(margin)
            if legacy_events:
                events.extend(legacy_events)
                warnings.append({"code": "MARGIN_LEGACY_POSITIONAL_LAYOUT_USED", "sheet": margin.title})
            else:
                warnings.append({"code": "MARGIN_HEADER_UNRECOGNIZED", "sheet": margin.title})
    events.sort(key=lambda item: (item["effective_date"], item["source"]["sheet"], item["source"]["row"], item["event_identity"]))
    account = _account_snapshot_contract(_sheet_by_normalized_name(workbook, "AccountSnapshot"), margin, warnings)
    investment_accounts = _investment_account_contexts(_sheet_by_normalized_name(workbook, "AccountSnapshot"), warnings)
    investment_accounts_portfolio_context = _accounts_aggregate(investment_accounts)
    owner_policy = _optional_contract(
        _sheet_by_normalized_name(workbook, "PortfolioPolicy"),
        contract_version=POLICY_CONTRACT,
        fields=POLICY_FIELDS,
        field_semantics=POLICY_FIELD_SEMANTICS,
        label="owner_portfolio_policy",
        warnings=warnings,
    )
    policy, system_default_policy = _effective_policy(owner_policy)
    total_hint = _total_quantity_hint(_sheet_by_normalized_name(workbook, "Total"), warnings)
    # A syntactically successful import that recognized every present source
    # sheet's header yet produced zero events is suspicious, not clean: it is
    # exactly the failure mode a schema-adaptation regression would produce
    # (every required column found, but some row-level rule silently rejects
    # every row). Surface it explicitly rather than letting it read the same
    # as a workbook that genuinely records no activity.
    present_source_sheets = [sheet for sheet in (trade, dividend, money, margin) if sheet is not None]
    header_unrecognized_codes = {"TRADE_HEADER_UNRECOGNIZED", "DIVIDEND_HEADER_UNRECOGNIZED", "MONEY_HEADER_UNRECOGNIZED", "MARGIN_HEADER_UNRECOGNIZED"}
    any_header_unrecognized = any(warning.get("code") in header_unrecognized_codes for warning in warnings)
    if present_source_sheets and not any_header_unrecognized and not events:
        warnings.append({"code": "ZERO_EVENTS_DESPITE_RECOGNIZED_SOURCES"})
    body = {
        "schema_version": "portfolio_event_ledger_v1",
        "contract_version": EVENT_LEDGER_CONTRACT,
        "workbook_sha256": workbook_sha256,
        "workbook_filename": workbook_path.name,
        "sheet_inventory": [{"sheet": sheet.title, "max_row": sheet.max_row, "max_column": sheet.max_column} for sheet in workbook.worksheets],
        "events": events,
        "event_counts": dict(sorted(Counter(event["event_type"] for event in events).items())),
        "reconciliation_warnings": warnings,
        "authority_boundary": {
            "private_local_only": True,
            "total_sheet_is_view_hint_only": True,
            "money_and_margin_monetary_fields_currency": "VND",
            "money_and_margin_currency_inference_from_cell_format_or_magnitude": "PROHIBITED",
            "no_market_context_or_timing_classification": True,
            "no_daily_dashboard_or_ai_handoff_integration": True,
        },
    }
    ledger = {**body, **_identity("portfolio_event_ledger", body)}
    # The Total data is intentionally held only in-process, never retained as authority.
    workbook.close()
    return ledger, account, {
        "policy": policy,
        "system_default_policy": system_default_policy,
        "total_quantity_hint": total_hint,
        "investment_accounts": investment_accounts,
        "investment_accounts_portfolio_context": investment_accounts_portfolio_context,
    }


def _amount_from_event(event: Mapping[str, Any], field: str = "gross_amount") -> Decimal:
    return _decimal(event.get(field)) or Decimal(0)


def _snapshot_from_ledger(*, ledger: Mapping[str, Any], account_snapshot: Mapping[str, Any], policy: Mapping[str, Any], total_quantity_hint: Mapping[str, Decimal], investment_accounts: list[dict[str, Any]] | None = None, investment_accounts_portfolio_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    states: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "quantity": Decimal(0), "carrying_cost": Decimal(0), "current_episode_start_date": None,
        "first_acquisition_date": None, "last_acquisition_date": None, "purchase_count": 0, "sale_count": 0,
        "purchase_cashflow": Decimal(0), "sale_proceeds": Decimal(0), "cash_dividends": Decimal(0),
        "stock_distribution_quantity": Decimal(0), "ticker_financing_cost": Decimal(0),
        "ticker_fee_or_tax_cashflow": Decimal(0), "realized_pnl": Decimal(0), "accounting_blocked": False,
    })
    unallocated_margin_cost = Decimal(0)
    warnings = list(ledger.get("reconciliation_warnings") or [])
    for event in ledger.get("events") or []:
        event_type, ticker = event.get("event_type"), event.get("ticker")
        amount, quantity = _amount_from_event(event), _decimal(event.get("quantity")) or Decimal(0)
        if event_type == "ACCOUNT_MARGIN_COST":
            unallocated_margin_cost += amount
            continue
        if not ticker or ticker not in states and event_type == "MONEY_MOVEMENT":
            continue
        state = states[ticker]
        date = event["effective_date"]
        if event_type == "BUY":
            if state["quantity"] == 0:
                state["current_episode_start_date"] = date
            outflow = amount + _amount_from_event(event, "fee") + _amount_from_event(event, "tax")
            state["quantity"] += quantity
            state["carrying_cost"] += outflow
            state["purchase_cashflow"] += outflow
            state["purchase_count"] += 1
            state["first_acquisition_date"] = state["first_acquisition_date"] or date
            state["last_acquisition_date"] = date
        elif event_type == "SELL":
            proceeds = amount - _amount_from_event(event, "fee") - _amount_from_event(event, "tax")
            state["sale_proceeds"] += proceeds
            state["sale_count"] += 1
            if quantity > state["quantity"]:
                # The running derived quantity cannot absorb this SELL -- the reconstruction
                # itself is broken from this point forward, not just this one row. `quantity`
                # is deliberately left untouched (never coerced to 0 or to this SELL's size):
                # once broken, no further arithmetic on it is trustworthy either. The position
                # row below turns this into CURRENT_POSITION_UNRESOLVED and withholds
                # `current_quantity` entirely -- this flag must never let a stale positive
                # quantity read as a confirmed current holding downstream.
                state["accounting_blocked"] = True
                warnings.append({"code": "SELL_QUANTITY_EXCEEDS_DERIVED_HOLDING", "sheet": event["source"]["sheet"], "row": event["source"]["row"]})
                continue
            allocated_cost = state["carrying_cost"] * quantity / state["quantity"] if state["quantity"] else Decimal(0)
            state["quantity"] -= quantity
            state["carrying_cost"] -= allocated_cost
            state["realized_pnl"] += proceeds - allocated_cost
            if state["quantity"] == 0:
                state["current_episode_start_date"] = None
        elif event_type == "CASH_DIVIDEND":
            state["cash_dividends"] += amount
        elif event_type == "STOCK_DISTRIBUTION":
            if state["quantity"] == 0:
                state["current_episode_start_date"] = date
            state["quantity"] += quantity
            state["stock_distribution_quantity"] += quantity
            state["first_acquisition_date"] = state["first_acquisition_date"] or date
            state["last_acquisition_date"] = date
        elif event_type == "TICKER_FINANCING_COST":
            state["ticker_financing_cost"] += amount
        elif event_type == "TICKER_FEE_OR_TAX_CASHFLOW":
            state["ticker_fee_or_tax_cashflow"] += amount
    event_dates = [event.get("effective_date") for event in ledger.get("events") or [] if isinstance(event.get("effective_date"), str)]
    account_as_of = ((account_snapshot.get("fields") or {}).get("as_of_date"))
    snapshot_as_of_date = account_as_of or max(event_dates, default=None)
    snapshot_as_of_basis = "ACCOUNT_SNAPSHOT_AS_OF_DATE" if account_as_of else "LATEST_LEDGER_EVENT_DATE" if snapshot_as_of_date else "UNAVAILABLE"
    account_attribution_by_ticker = _position_account_attribution(ledger.get("events") or [])
    positions = []
    for ticker, state in sorted(states.items()):
        # A ticker whose only activity is a SELL that exceeded its (zero) opening holding --
        # e.g. a missing historical opening position -- must still surface as
        # CURRENT_POSITION_UNRESOLVED, never be silently dropped as if it never existed.
        if state["quantity"] <= 0 and state["purchase_count"] == 0 and state["stock_distribution_quantity"] == 0 and not state["accounting_blocked"]:
            continue
        total_hint = total_quantity_hint.get(ticker)
        if total_hint is not None and total_hint != state["quantity"]:
            warnings.append({"code": "TOTAL_VIEW_HINT_QUANTITY_MISMATCH", "ticker": ticker})
        lifetime_outflow = state["purchase_cashflow"] + state["ticker_financing_cost"] + state["ticker_fee_or_tax_cashflow"] - state["sale_proceeds"] - state["cash_dividends"]
        current_cost_per_share = state["carrying_cost"] / state["quantity"] if state["quantity"] > 0 else None
        lifetime_breakeven = lifetime_outflow / state["quantity"] if state["quantity"] > 0 else None
        episode_holding_days = None
        if state["current_episode_start_date"] and snapshot_as_of_date:
            episode_start = dt.date.fromisoformat(state["current_episode_start_date"])
            as_of = dt.date.fromisoformat(snapshot_as_of_date)
            if as_of >= episode_start:
                episode_holding_days = (as_of - episode_start).days
            else:
                warnings.append({"code": "ACCOUNT_SNAPSHOT_BEFORE_POSITION_EPISODE", "ticker": ticker})
        if state["accounting_blocked"]:
            current_position_status = CURRENT_POSITION_STATUS_UNRESOLVED
        elif state["quantity"] > 0:
            current_position_status = CURRENT_POSITION_STATUS_CONFIRMED
        else:
            current_position_status = CURRENT_POSITION_STATUS_CLOSED
        positions.append({
            "ticker": ticker,
            # CURRENT_POSITION_TRUTH: `current_quantity` is withheld (None), never a stale
            # reconstructed number, whenever `current_position_status` is not CURRENT_CONFIRMED.
            # A caller must read `current_position_status` before treating a ticker as held --
            # this mirrors the existing `realized_pnl`/`realized_pnl_status` pairing below.
            "current_quantity": _number(state["quantity"]) if current_position_status != CURRENT_POSITION_STATUS_UNRESOLVED else None,
            "current_position_status": current_position_status,
            "position_episode_start_date": state["current_episode_start_date"],
            "position_episode_holding_days": episode_holding_days,
            "first_acquisition_date": state["first_acquisition_date"],
            "last_acquisition_date": state["last_acquisition_date"],
            "purchase_count": state["purchase_count"], "sale_count": state["sale_count"],
            "purchase_cashflow": _number(state["purchase_cashflow"]), "sale_proceeds": _number(state["sale_proceeds"]),
            "cash_dividends": _number(state["cash_dividends"]), "stock_distribution_quantity": _number(state["stock_distribution_quantity"]),
            "ticker_financing_cost": _number(state["ticker_financing_cost"]), "ticker_fee_or_tax_cashflow": _number(state["ticker_fee_or_tax_cashflow"]),
            "current_position_carrying_cost": _number(state["carrying_cost"]),
            "current_position_cost_basis_per_share": _number(current_cost_per_share),
            "current_position_cost_basis_method": CURRENT_COST_BASIS_METHOD,
            "lifetime_net_cash_outflow": _number(lifetime_outflow),
            "lifetime_cash_recovery_breakeven": _number(lifetime_breakeven),
            "lifetime_cash_recovery_breakeven_method": LIFETIME_BREAKEVEN_METHOD,
            "realized_pnl": None if state["accounting_blocked"] else _number(state["realized_pnl"]),
            "realized_pnl_status": "UNRESOLVED_RECONCILIATION_WARNING" if state["accounting_blocked"] else "AVAILABLE",
            "unrealized_pnl": None,
            "unrealized_pnl_status": "UNAVAILABLE_NO_OWNER_MARK_PRICE",
            # PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: additive per-account lineage.
            # Never consulted by `current_position_status`/`current_quantity` above -- those
            # remain the sole current-holding authority, unchanged by this milestone.
            "account_attribution": account_attribution_by_ticker.get(ticker, []),
        })
    warning_codes = sorted(Counter(warning["code"] for warning in warnings).items())
    current_position_status_counts = dict(sorted(Counter(position["current_position_status"] for position in positions).items()))
    tickers_with_attributed_account = sum(
        1 for rows in account_attribution_by_ticker.values() if any(row["attribution_status"] == "ATTRIBUTED" for row in rows)
    )
    tickers_unresolved_attribution_only = sum(
        1 for rows in account_attribution_by_ticker.values()
        if rows and all(row["attribution_status"] != "ATTRIBUTED" for row in rows)
    )
    position_account_attribution_summary = {
        "total_tickers_with_any_activity": len(account_attribution_by_ticker),
        "tickers_with_attributed_account": tickers_with_attributed_account,
        "tickers_unresolved_attribution_only": tickers_unresolved_attribution_only,
    }
    investment_accounts_list = list(investment_accounts or [])
    investment_accounts_context = investment_accounts_portfolio_context if investment_accounts_portfolio_context is not None else _accounts_aggregate([])
    body = {
        "schema_version": "portfolio_snapshot_v1",
        "contract_version": SNAPSHOT_CONTRACT,
        "ledger_identity": ledger.get("artifact_identity"),
        "account_snapshot_identity": account_snapshot.get("artifact_identity"),
        "portfolio_policy_identity": policy.get("artifact_identity"),
        "snapshot_as_of_date": snapshot_as_of_date,
        "snapshot_as_of_basis": snapshot_as_of_basis,
        "positions": positions,
        # `current_position_count` (public summaries below) counts only CURRENT_CONFIRMED --
        # this breakdown is what makes that count auditable without re-scanning `positions`.
        "current_position_status_counts": current_position_status_counts,
        "account_snapshot": account_snapshot,
        "portfolio_policy": policy,
        "account_level_unallocated_margin_cost": _number(unallocated_margin_cost),
        # PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1: additive, alongside the unchanged
        # single-account `account_snapshot` above.
        "investment_accounts": investment_accounts_list,
        "investment_accounts_portfolio_context": investment_accounts_context,
        "position_account_attribution_summary": position_account_attribution_summary,
        "reconciliation": {"status": "WARNING" if warnings else "RECONCILED", "warning_counts": dict(warning_codes), "warning_count": len(warnings)},
        "authority_boundary": {
            "cash_dividends_and_sale_proceeds_do_not_change_current_position_carrying_cost": True,
            "ticker_financing_separate_from_account_margin_cost": True,
            "total_sheet_never_used_as_factual_authority": True,
            "market_timing_top_bottom_classification": "NOT_IMPLEMENTED_RETAIN_EVENTS_FOR_LATER_CONTEXT",
            "unrealized_pnl_requires_owner_supplied_mark_price": True,
            "no_position_sizing_or_investment_recommendation": True,
            "policy_cap_excess_is_not_an_automatic_sell_instruction": True,
            "current_position_status_is_the_sole_current_holding_authority": True,
            "reconciliation_blocked_quantity_is_never_reported_as_a_current_holding": True,
            "account_attribution_is_additive_lineage_never_a_current_holding_authority": True,
            "cash_availability_is_capital_context_not_a_buy_signal": True,
        },
    }
    return {**body, **_identity("portfolio_snapshot", body)}


def _write_immutable_json(path: Path, value: Mapping[str, Any]) -> bool:
    """Return True only when a new private artifact was written."""
    payload = _canonical(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise PortfolioImportError("PRIVATE_PORTFOLIO_CONTENT_ADDRESS_CONFLICT")
        return False
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)
    return True


def _write_pointer(path: Path, value: Mapping[str, Any]) -> bool:
    payload = _canonical(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)
    return True


def import_workbook(*, workbook_path: Path | None = None, portfolio_root: Path | None = None) -> dict[str, Any]:
    """Materialize one content-addressed, private import without any provider call."""
    workbook_path = (workbook_path or default_workbook_path()).expanduser().resolve()
    portfolio_root = (portfolio_root or default_portfolio_root()).expanduser().resolve()
    if not workbook_path.is_file():
        raise PortfolioImportError("PORTFOLIO_WORKBOOK_NOT_FOUND")
    if _within(workbook_path, REPOSITORY_ROOT):
        raise PortfolioImportError("PORTFOLIO_WORKBOOK_MUST_LIVE_OUTSIDE_REPOSITORY")
    workbook_sha256 = _sha256_file(workbook_path)
    ledger, account_snapshot, extras = build_event_ledger(workbook_path=workbook_path, workbook_sha256=workbook_sha256)
    policy = extras["policy"]
    system_default_policy = extras["system_default_policy"]
    investment_accounts = extras["investment_accounts"]
    investment_accounts_portfolio_context = extras["investment_accounts_portfolio_context"]
    snapshot = _snapshot_from_ledger(
        ledger=ledger, account_snapshot=account_snapshot, policy=policy, total_quantity_hint=extras["total_quantity_hint"],
        investment_accounts=investment_accounts, investment_accounts_portfolio_context=investment_accounts_portfolio_context,
    )
    investment_accounts_document_body = {
        "schema_version": "investment_accounts_v1",
        "contract_version": INVESTMENT_ACCOUNT_CONTEXT_CONTRACT,
        "accounts": investment_accounts,
        "account_count": len(investment_accounts),
    }
    investment_accounts_document = {**investment_accounts_document_body, **_identity("investment_accounts_document", investment_accounts_document_body)}
    import_layout = _import_layout()
    relative_directory = Path("imports") / workbook_sha256 / import_layout["artifact_sha256"]
    manifest_body = {
        "schema_version": "portfolio_import_manifest_v1",
        "contract_version": IMPORT_MANIFEST_CONTRACT,
        "workbook_sha256": workbook_sha256,
        "workbook_filename": workbook_path.name,
        "import_layout_version": IMPORT_LAYOUT_VERSION,
        "import_layout_identity": import_layout["artifact_identity"],
        "artifact_identities": {
            "portfolio_event_ledger_v1": ledger["artifact_identity"],
            "portfolio_snapshot_v1": snapshot["artifact_identity"],
            "portfolio_policy_v1": policy["artifact_identity"],
            "system_default_policy_v1": system_default_policy["artifact_identity"],
            "account_snapshot_v1": account_snapshot["artifact_identity"],
            "investment_accounts_v1": investment_accounts_document["artifact_identity"],
            "investment_accounts_portfolio_context_v1": investment_accounts_portfolio_context["artifact_identity"],
        },
        "relative_directory": relative_directory.as_posix(),
        "authority_boundary": {"local_only": True, "workbook_values_not_written_to_repository": True, "provider_calls": "NOT_USED", "daily_run": "NOT_USED"},
    }
    manifest = {**manifest_body, **_identity("portfolio_import_manifest", manifest_body)}
    destination = portfolio_root / relative_directory
    wrote = [
        _write_immutable_json(destination / "portfolio_event_ledger_v1.json", ledger),
        _write_immutable_json(destination / "portfolio_snapshot_v1.json", snapshot),
        _write_immutable_json(destination / "portfolio_policy_v1.json", policy),
        _write_immutable_json(destination / "system_default_policy_v1.json", system_default_policy),
        _write_immutable_json(destination / "account_snapshot_v1.json", account_snapshot),
        _write_immutable_json(destination / "investment_accounts_v1.json", investment_accounts_document),
        _write_immutable_json(destination / "investment_accounts_portfolio_context_v1.json", investment_accounts_portfolio_context),
        _write_immutable_json(destination / "portfolio_import_manifest_v1.json", manifest),
    ]
    pointer = {"schema_version": "portfolio_latest_import_pointer/v1", "workbook_sha256": workbook_sha256, "import_manifest_identity": manifest["artifact_identity"], "relative_directory": relative_directory.as_posix()}
    _write_pointer(portfolio_root / "latest_import.json", pointer)
    return {
        "status": "IMPORTED" if any(wrote) else "REUSED_IDENTICAL",
        "manifest": manifest,
        "ledger": ledger,
        "snapshot": snapshot,
        "policy": policy,
        "system_default_policy": system_default_policy,
        "account_snapshot": account_snapshot,
        "investment_accounts": investment_accounts_document,
        "investment_accounts_portfolio_context": investment_accounts_portfolio_context,
        "storage_root": portfolio_root,
        "private_artifact_directory": destination,
    }


def portfolio_status(*, portfolio_root: Path | None = None) -> dict[str, Any]:
    """Read the private latest pointer without opening the source workbook."""
    root = (portfolio_root or default_portfolio_root()).expanduser().resolve()
    pointer_path = root / "latest_import.json"
    if not pointer_path.is_file():
        return {"status": "NOT_IMPORTED", "portfolio_root": root}
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        directory = root / str(pointer["relative_directory"])
        manifest = json.loads((directory / "portfolio_import_manifest_v1.json").read_text(encoding="utf-8"))
        snapshot = json.loads((directory / "portfolio_snapshot_v1.json").read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise PortfolioImportError("PRIVATE_PORTFOLIO_LATEST_POINTER_INVALID") from exc
    warning_counts = snapshot["reconciliation"]["warning_counts"]
    if "ZERO_EVENTS_DESPITE_RECOGNIZED_SOURCES" in warning_counts:
        # A syntactically successful import whose recognized source sheets
        # produced no events at all must never read the same as a genuinely
        # activity-free workbook -- fail closed instead of claiming READY.
        return {
            "status": "RECONCILIATION_INCOMPLETE",
            "reason_codes": ["ZERO_EVENTS_DESPITE_RECOGNIZED_SOURCES"],
            "pointer": pointer, "manifest": manifest, "snapshot": snapshot, "portfolio_root": root,
        }
    return {"status": "READY", "pointer": pointer, "manifest": manifest, "snapshot": snapshot, "portfolio_root": root}


def _current_position_count(snapshot: Mapping[str, Any]) -> int:
    """Actual CONFIRMED current positions only -- never a count of every ticker with any
    historical portfolio activity (CLOSED and CURRENT_POSITION_UNRESOLVED are excluded)."""
    return sum(
        1 for position in snapshot.get("positions") or []
        if position.get("current_position_status") == CURRENT_POSITION_STATUS_CONFIRMED
    )


def _investment_accounts_public_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Safe CLI surface for the multi-account context: counts/status only, never a real account
    alias, broker name, or monetary value."""
    aggregate = snapshot.get("investment_accounts_portfolio_context") or {}
    return {
        "investment_account_count": len(snapshot.get("investment_accounts") or []),
        "investment_accounts_aggregate_status": aggregate.get("status"),
        "investment_accounts_as_of_consistency": aggregate.get("as_of_consistency"),
        "position_account_attribution_summary": snapshot.get("position_account_attribution_summary"),
    }


def public_import_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Safe CLI surface: identities/counts/codes only, never private values or tickers."""
    snapshot = result["snapshot"]
    return {
        "status": result["status"],
        "import_manifest_identity": result["manifest"]["artifact_identity"],
        "workbook_sha256": result["manifest"]["workbook_sha256"],
        "event_count": len(result["ledger"]["events"]),
        "current_position_count": _current_position_count(snapshot),
        "current_position_status_counts": snapshot.get("current_position_status_counts"),
        "reconciliation_warning_counts": snapshot["reconciliation"]["warning_counts"],
        **_investment_accounts_public_summary(snapshot),
        "provider_calls": "NOT_USED",
        "daily_run": "NOT_USED",
    }


def public_status_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    if result["status"] == "NOT_IMPORTED":
        return {"status": "NOT_IMPORTED"}
    snapshot = result["snapshot"]
    summary = {
        "status": result["status"],
        "import_manifest_identity": result["manifest"]["artifact_identity"],
        "workbook_sha256": result["manifest"]["workbook_sha256"],
        "current_position_count": _current_position_count(snapshot),
        "current_position_status_counts": snapshot.get("current_position_status_counts"),
        "reconciliation_warning_counts": snapshot["reconciliation"]["warning_counts"],
        **_investment_accounts_public_summary(snapshot),
        "provider_calls": "NOT_USED",
        "daily_run": "NOT_USED",
    }
    if "reason_codes" in result:
        summary["reason_codes"] = result["reason_codes"]
    return summary
