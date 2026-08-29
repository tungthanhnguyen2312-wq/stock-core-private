"""Fail-closed, scoped currency and scale evidence for financial statements.

The resolver deliberately accepts only an explicit unit declaration.  It does
not infer a reporting currency from an issuer, numerical magnitude, or a bare
currency token elsewhere in a document.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "financial_statement_scoped_unit_resolution/v1"
_SCALE = (("billion", 1_000_000_000, "billion"), ("ty", 1_000_000_000, "tỷ"),
          ("million", 1_000_000, "million"), ("trieu", 1_000_000, "triệu"),
          ("thousand", 1_000, "thousand"), ("nghin", 1_000, "nghìn"))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _norm(value: str) -> str:
    normalized = "".join(ch for ch in unicodedata.normalize("NFKD", str(value).lower())
                         if not unicodedata.combining(ch))
    return " ".join(normalized.replace("đ", "d").split())


def parse_explicit_unit_declaration(text: str) -> dict[str, Any] | None:
    """Parse one labelled declaration, preserving currency and scale separately."""
    normalized = _norm(text)
    if not re.search(r"\b(don\s*vi(?:\s*tinh)?|unit|currency)\b", normalized):
        return None
    currencies = set(re.findall(r"\b(?:vnd|usd)\b", normalized))
    if "dong" in normalized or "đong" in normalized:
        currencies.add("vnd")
    if len(currencies) != 1:
        return None
    currency = next(iter(currencies)).upper()
    scales = [(multiplier, label) for word, multiplier, label in _SCALE if re.search(rf"\b{word}\b", normalized)]
    if len(scales) > 1:
        return None
    multiplier, scale_label = scales[0] if scales else (1, "base")
    return {"currency": currency, "unit_scale": multiplier,
            "unit_label": currency if multiplier == 1 else f"{scale_label} {currency}",
            "evidence_text": str(text).strip()}


def declaration_from_tokens(*, tokens: Iterable[Mapping[str, Any]], document_sha256: str,
                            page_number: int, statement_family: str, table_id: str | None = None) -> list[dict[str, Any]]:
    """Return explicit OCR line declarations with their exact token/source span."""
    groups: dict[tuple[int, int, int], list[Mapping[str, Any]]] = {}
    for token in tokens:
        hierarchy = token.get("tsv_hierarchy") or {}
        key = (int(hierarchy.get("block_num", 0)), int(hierarchy.get("par_num", 0)), int(hierarchy.get("line_num", 0)))
        groups.setdefault(key, []).append(token)
    declarations = []
    for _, line in sorted(groups.items()):
        line = sorted(line, key=lambda item: int(item.get("raw_token_order", 0)))
        text = " ".join(str(item.get("text", "")) for item in line)
        parsed = parse_explicit_unit_declaration(text)
        if not parsed:
            continue
        token_ids = [str(item.get("token_id", "")) for item in line]
        declaration = {**parsed, "scope_level": "table" if table_id else "statement_page",
                       "document_sha256": document_sha256, "page_number": int(page_number),
                       "statement_family": statement_family, "table_id": table_id,
                       "source_span": {"token_ids": token_ids,
                                       "raw_token_order": [int(item.get("raw_token_order", 0)) for item in line]},
                       "evidence_id": _hash({"document_sha256": document_sha256, "page_number": page_number,
                                              "statement_family": statement_family, "table_id": table_id,
                                              "text": parsed["evidence_text"], "token_ids": token_ids})}
        declarations.append(declaration)
    return declarations


def resolve_unit_for_scope(declarations: Iterable[Mapping[str, Any]], *, document_sha256: str,
                           page_number: int | None, statement_family: str | None,
                           table_id: str | None = None) -> dict[str, Any]:
    """Resolve table > statement/page > document evidence without weakening conflicts."""
    candidates = [dict(item) for item in declarations if item.get("document_sha256") == document_sha256]
    levels = []
    if table_id:
        levels.append(("table", lambda item: item.get("table_id") == table_id))
    if page_number is not None and statement_family:
        levels.append(("statement_page", lambda item: item.get("scope_level") in {"statement_page", "page"}
                      and item.get("page_number") == page_number and item.get("statement_family") == statement_family))
    levels.append(("document", lambda item: item.get("scope_level") == "document"))
    for level, predicate in levels:
        selected = [item for item in candidates if predicate(item)]
        if not selected:
            continue
        semantics = {(item.get("currency"), item.get("unit_scale")) for item in selected}
        if len(semantics) != 1 or any(currency is None or scale is None for currency, scale in semantics):
            return {"state": "UNIT_SCALE_BLOCKED", "reason": "SCOPED_UNIT_DECLARATION_CONFLICT",
                    "scope_level": level, "evidence": sorted(selected, key=lambda item: str(item.get("evidence_id", "")))}
        evidence = sorted(selected, key=lambda item: str(item.get("evidence_id", "")))[0]
        return {"state": "QUALIFIED", "scope_level": level, "currency": evidence["currency"],
                "unit_scale": evidence["unit_scale"], "unit_label": evidence["unit_label"],
                "evidence": evidence}
    return {"state": "UNIT_SCALE_BLOCKED", "reason": "SCOPED_UNIT_DECLARATION_MISSING"}
