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
SYSTEM_DEFAULT_POLICY_CONTRACT = "system_default_policy/v1"
IMPORT_MANIFEST_CONTRACT = "portfolio_import_manifest/v1"
IMPORT_LAYOUT_VERSION = "PORTFOLIO_CONTEXT_IMPORT_LAYOUT_V2"
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
    text = unicodedata.normalize("NFKD", str(value or ""))
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
    "ticker": ("ticker", "symbol", "stockcode", "securitycode", "mack", "machungkhoan", "ma"),
    "side": ("side", "action", "type", "tradetype", "buysell", "muaban", "giaodich"),
    "quantity": ("quantity", "qty", "volume", "shares", "sharequantity", "sl", "soluong"),
    "price": ("price", "tradeprice", "unitprice", "gia", "giagiao dich", "giagiaodich"),
    "amount": ("amount", "value", "totalamount", "cashamount", "netamount", "thanhtien", "giatri", "total"),
    "fee": ("fee", "fees", "commission", "brokerage", "phi", "phigiaodich"),
    "tax": ("tax", "taxes", "withholdingtax", "thue"),
    "cash_amount": ("cashdividend", "dividendamount", "cashamount", "amount", "thanhtien", "giatri"),
    "cash_per_share": ("cashpershare", "dividendpershare", "cophieutienmatmoicophieu"),
    "stock_quantity": ("stockquantity", "bonusshares", "stockdividendshares", "sharedividend", "cophieunhan", "soluongcophieu"),
    "key": ("key", "field", "metric", "name", "parameter", "chi tieu", "chitieu"),
    "value": ("value", "amount", "number", "gia tri", "giatri"),
}
FIELD_ALIAS_NORMALS = {field: {_normal(alias) for alias in aliases} for field, aliases in FIELD_ALIASES.items()}

ACCOUNT_FIELDS = {
    "as_of_date": ("asofdate", "asof", "snapshotdate", "ngaychot", "ngay"),
    "currency": ("currency", "basecurrency", "tiente", "donvitien"),
    "cash_available": ("cashavailable", "cashbalance", "cash", "tienmat", "tiensan sang"),
    "cash_reserved": ("cashreserved", "reservedcash", "tienphongtoa", "tiencho"),
    "margin_debt": ("margindebt", "currentmargindebt", "marginloan", "currentmarginloan", "marginbalance", "nodu", "nodmargin"),
    "margin_available_minimum": ("marginavailableminimum", "minmarginavailable", "minimumavailablemargin", "marginavailabilitymin", "marginavailablemin", "hanmucmarginconlaitoithieu", "sucmuatoithieu"),
    "margin_available_maximum": ("marginavailablemaximum", "maxmarginavailable", "maximumavailablemargin", "marginavailabilitymax", "marginavailablemax", "hanmucmarginconlaitoida", "sucmuatoida"),
    "annual_margin_rate_percent": ("annualmarginratepercent", "annualmarginrate", "marginratepercent", "margininterestrate", "laisuatmargin", "laivaymarginphantram"),
    "accrued_margin_interest": ("accruedmargininterest", "margininterest", "laivaymargin", "laitrich"),
    "net_asset_value": ("netassetvalue", "nav", "taisanrong"),
    "gross_market_value": ("grossmarketvalue", "marketvalue", "giatrithitruong"),
}
POLICY_FIELDS = {
    "as_of_date": ACCOUNT_FIELDS["as_of_date"],
    "currency": ACCOUNT_FIELDS["currency"],
    "risk_budget_per_investment_decision_to_nav": ("riskbudgetperinvestmentdecisiontonav", "riskbudgetperdecision", "riskbudgettonav", "ngansachruimoiquyetdinh"),
    "max_single_position_weight": ("maxsinglepositionweight", "maxsinglenameweight", "tytrongtoidamotma"),
    "max_gross_exposure_to_nav": ("maxgrossexposuretonav", "maxgrossleverage", "tongphoinhiemtoida"),
    "max_margin_debt_to_nav": ("maxmargindebttonav", "maxmarginratio", "marginno toida", "marginnotoida"),
    "max_sector_weight": ("maxsectorweight", "tytrongnganhtoida"),
    "minimum_cash_reserve_to_nav": ("minimumcashreservetonav", "mincashreservetonav", "minimumcashreserve", "tienmatdutoithieutonnav"),
    "max_margin_rate_percent_for_new_leveraged_exposure": ("maxmarginratepercentfornewleveragedexposure", "maxmarginratefornewleverage", "maxnewleveragemarginrate", "laisuatmarginmaxchodonbaymoi"),
    "max_ticker_financing_cost": ("maxtickerfinancingcost", "maxstockfinancingcost", "laivaymatotoida"),
    "max_account_margin_cost": ("maxaccountmargincost", "maxmargininterest", "laivaytaikhoantoida"),
}

# Monetary fields are VND because the workbook field contract says so.  The
# importer deliberately never inspects Excel number formatting or magnitude to
# guess a currency or rescale a numeric cell.
ACCOUNT_FIELD_SEMANTICS = {
    "as_of_date": "ISO_DATE",
    "currency": "ISO_CURRENCY_CODE",
    "cash_available": "VND",
    "cash_reserved": "VND",
    "margin_debt": "VND",
    "margin_available_minimum": "VND",
    "margin_available_maximum": "VND",
    "annual_margin_rate_percent": "PERCENT_PER_ANNUM_NUMBER",
    "accrued_margin_interest": "VND",
    "net_asset_value": "VND",
    "gross_market_value": "VND",
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
}
SYSTEM_DEFAULT_POLICY_VERSION = "SYSTEM_DEFAULT_POLICY_V1"
SYSTEM_DEFAULT_POLICY_V1 = {
    "risk_budget_per_investment_decision_to_nav": "0.01",
    "max_single_position_weight": "0.30",
    "max_sector_weight": "0.45",
    "max_gross_exposure_to_nav": "1.15",
    "max_margin_debt_to_nav": "0.15",
    "minimum_cash_reserve_to_nav": "0.05",
    "max_margin_rate_percent_for_new_leveraged_exposure": "15.0",
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


def _event(*, event_type: str, effective_date: str, source_sheet: str, source_row: int, ticker: str | None = None, quantity: Decimal | None = None, gross_amount: Decimal | None = None, fee: Decimal | None = None, tax: Decimal | None = None, note: str | None = None, monetary_currency: str | None = None, monetary_unit_basis: str | None = None) -> dict[str, Any]:
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
    }
    body["event_identity"] = _event_identity(body)
    return body


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
        events.append(_event(event_type=event_type, effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, quantity=quantity, gross_amount=gross, fee=fee, tax=tax))
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
        effective_date, ticker = _date(_cell(row, mapping, "date")), _ticker(_cell(row, mapping, "ticker"))
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
        stock_like = stock_quantity is not None or any(token in event_hint for token in ("stock", "bonus", "share", "co phieu", "cophieu"))
        if stock_like:
            if stock_quantity is None or stock_quantity <= 0:
                warnings.append({"code": "STOCK_DISTRIBUTION_QUANTITY_UNRESOLVED", "sheet": sheet.title, "row": source_row})
                continue
            events.append(_event(event_type="STOCK_DISTRIBUTION", effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, quantity=stock_quantity, gross_amount=Decimal(0)))
        elif cash_amount is not None and cash_amount >= 0:
            events.append(_event(event_type="CASH_DIVIDEND", effective_date=effective_date, source_sheet=sheet.title, source_row=source_row, ticker=ticker, gross_amount=cash_amount))
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
        "default_fields": SYSTEM_DEFAULT_POLICY_V1,
        "field_semantics": {field: POLICY_FIELD_SEMANTICS[field] for field in SYSTEM_DEFAULT_POLICY_V1},
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
        },
    }
    return {**body, **_identity("account_snapshot", body)}


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
        if margin_event_header is not None or not margin_has_account_fields:
            events.extend(_money_events(margin, warnings, margin=True))
    events.sort(key=lambda item: (item["effective_date"], item["source"]["sheet"], item["source"]["row"], item["event_identity"]))
    account = _account_snapshot_contract(_sheet_by_normalized_name(workbook, "AccountSnapshot"), margin, warnings)
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
    return ledger, account, {"policy": policy, "system_default_policy": system_default_policy, "total_quantity_hint": total_hint}


def _amount_from_event(event: Mapping[str, Any], field: str = "gross_amount") -> Decimal:
    return _decimal(event.get(field)) or Decimal(0)


def _snapshot_from_ledger(*, ledger: Mapping[str, Any], account_snapshot: Mapping[str, Any], policy: Mapping[str, Any], total_quantity_hint: Mapping[str, Decimal]) -> dict[str, Any]:
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
    positions = []
    for ticker, state in sorted(states.items()):
        if state["quantity"] <= 0 and state["purchase_count"] == 0 and state["stock_distribution_quantity"] == 0:
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
        positions.append({
            "ticker": ticker,
            "current_quantity": _number(state["quantity"]),
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
        })
    warning_codes = sorted(Counter(warning["code"] for warning in warnings).items())
    body = {
        "schema_version": "portfolio_snapshot_v1",
        "contract_version": SNAPSHOT_CONTRACT,
        "ledger_identity": ledger.get("artifact_identity"),
        "account_snapshot_identity": account_snapshot.get("artifact_identity"),
        "portfolio_policy_identity": policy.get("artifact_identity"),
        "snapshot_as_of_date": snapshot_as_of_date,
        "snapshot_as_of_basis": snapshot_as_of_basis,
        "positions": positions,
        "account_snapshot": account_snapshot,
        "portfolio_policy": policy,
        "account_level_unallocated_margin_cost": _number(unallocated_margin_cost),
        "reconciliation": {"status": "WARNING" if warnings else "RECONCILED", "warning_counts": dict(warning_codes), "warning_count": len(warnings)},
        "authority_boundary": {
            "cash_dividends_and_sale_proceeds_do_not_change_current_position_carrying_cost": True,
            "ticker_financing_separate_from_account_margin_cost": True,
            "total_sheet_never_used_as_factual_authority": True,
            "market_timing_top_bottom_classification": "NOT_IMPLEMENTED_RETAIN_EVENTS_FOR_LATER_CONTEXT",
            "unrealized_pnl_requires_owner_supplied_mark_price": True,
            "no_position_sizing_or_investment_recommendation": True,
            "policy_cap_excess_is_not_an_automatic_sell_instruction": True,
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
    snapshot = _snapshot_from_ledger(ledger=ledger, account_snapshot=account_snapshot, policy=policy, total_quantity_hint=extras["total_quantity_hint"])
    import_layout = _import_layout()
    relative_directory = Path("imports") / workbook_sha256 / import_layout["artifact_sha256"]
    manifest_body = {
        "schema_version": "portfolio_import_manifest_v1",
        "contract_version": IMPORT_MANIFEST_CONTRACT,
        "workbook_sha256": workbook_sha256,
        "workbook_filename": workbook_path.name,
        "import_layout_version": IMPORT_LAYOUT_VERSION,
        "import_layout_identity": import_layout["artifact_identity"],
        "artifact_identities": {"portfolio_event_ledger_v1": ledger["artifact_identity"], "portfolio_snapshot_v1": snapshot["artifact_identity"], "portfolio_policy_v1": policy["artifact_identity"], "system_default_policy_v1": system_default_policy["artifact_identity"], "account_snapshot_v1": account_snapshot["artifact_identity"]},
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
    return {"status": "READY", "pointer": pointer, "manifest": manifest, "snapshot": snapshot, "portfolio_root": root}


def public_import_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Safe CLI surface: identities/counts/codes only, never private values or tickers."""
    snapshot = result["snapshot"]
    return {
        "status": result["status"],
        "import_manifest_identity": result["manifest"]["artifact_identity"],
        "workbook_sha256": result["manifest"]["workbook_sha256"],
        "event_count": len(result["ledger"]["events"]),
        "current_position_count": len(snapshot["positions"]),
        "reconciliation_warning_counts": snapshot["reconciliation"]["warning_counts"],
        "provider_calls": "NOT_USED",
        "daily_run": "NOT_USED",
    }


def public_status_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    if result["status"] == "NOT_IMPORTED":
        return {"status": "NOT_IMPORTED"}
    snapshot = result["snapshot"]
    return {
        "status": "READY",
        "import_manifest_identity": result["manifest"]["artifact_identity"],
        "workbook_sha256": result["manifest"]["workbook_sha256"],
        "current_position_count": len(snapshot["positions"]),
        "reconciliation_warning_counts": snapshot["reconciliation"]["warning_counts"],
        "provider_calls": "NOT_USED",
        "daily_run": "NOT_USED",
    }
