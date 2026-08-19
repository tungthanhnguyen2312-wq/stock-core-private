#!/usr/bin/env python3
"""Deterministic financial item mapping registry.

Matching order is fixed: item_id, source_field, normalized label, regex.  A
derived rule is returned only when the caller explicitly requests a canonical
metric.  Fuzzy matching is intentionally unsupported.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MAPPING_PATH = ROOT_DIR / "config" / "financial_item_map.csv"
DEFAULT_PROFILES_PATH = ROOT_DIR / "config" / "ticker_entity_profiles.csv"
DEFAULT_METADATA_PATH = ROOT_DIR / "config" / "financial_item_map.meta.json"

REQUIRED_COLUMNS = {
    "rule_id", "canonical_metric", "entity_type", "report_type", "source",
    "item_id", "source_field", "normalized_label", "label_regex", "priority",
    "sign_multiplier", "unit_multiplier", "derivation_rule", "valid_from", "valid_to",
}
ENTITY_TYPES = {"*", "unknown", "corporate", "bank", "securities", "insurance", "finance_company"}
REPORT_TYPES = {"*", "derived", "balance_sheet", "income_statement", "cash_flow"}
KNOWN_CANONICAL_METRICS = {
    "amortization", "depreciation", "depreciation_and_amortization", "ebit",
    "ebitda", "general_admin_expense", "interest_expense", "operating_cash_flow",
    "profit_before_tax", "retained_earnings", "retained_earnings_current_year",
    "retained_earnings_prior_year", "selling_expense", "sga",
}


def normalize_label(value: str | None, strip_accents: bool = False) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = re.sub(r"\s+", " ", text)
    if strip_accents:
        text = "".join(
            char for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        ).replace("đ", "d")
    return text


@dataclass(frozen=True)
class MappingRule:
    rule_id: str
    canonical_metric: str
    entity_type: str
    report_type: str
    source: str
    item_id: str
    source_field: str
    normalized_label: str
    label_regex: str
    priority: int
    sign_multiplier: float
    unit_multiplier: float
    derivation_rule: str
    valid_from: str
    valid_to: str

    @property
    def specificity(self) -> int:
        return int(self.entity_type != "*") + int(self.report_type != "*") + int(self.source != "*")


class FinancialMappingRegistry:
    def __init__(
        self,
        mapping_path: Path,
        profiles_path: Path | None = None,
        metadata_path: Path | None = None,
        *,
        require_metadata: bool = False,
        enforce_known_metrics: bool = False,
    ):
        self.mapping_path = Path(mapping_path)
        self.profiles_path = Path(profiles_path) if profiles_path else None
        self.metadata_path = Path(metadata_path) if metadata_path else None
        self.metadata = self._load_metadata(require_metadata)
        self.enforce_known_metrics = enforce_known_metrics
        self.rules = self._load_rules()
        self.entity_profiles = self._load_profiles()

    def _load_metadata(self, required: bool) -> dict[str, Any]:
        if self.metadata_path is None or not self.metadata_path.exists():
            if required:
                raise ValueError("Mapping registry metadata with provenance/version is required")
            return {}
        payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not str(payload.get("registry_version") or "").strip():
            raise ValueError("Mapping registry metadata requires registry_version")
        provenance = payload.get("provenance")
        required_provenance = {"source_basis", "owner", "updated_at"}
        if not isinstance(provenance, dict) or required_provenance - set(provenance):
            raise ValueError("Mapping registry metadata requires provenance source_basis/owner/updated_at")
        return payload

    def _load_rules(self) -> list[MappingRule]:
        with self.mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(f"Mapping registry missing columns: {sorted(missing)}")
            raw_rows = list(reader)
        seen: set[str] = set()
        rules: list[MappingRule] = []
        for row_number, row in enumerate(raw_rows, start=2):
            cleaned = {key: (value or "").strip() for key, value in row.items()}
            rule_id = cleaned["rule_id"]
            if not rule_id or rule_id in seen:
                raise ValueError(f"Invalid or duplicate rule_id at row {row_number}: {rule_id!r}")
            seen.add(rule_id)
            entity_type = cleaned["entity_type"].lower()
            report_type = cleaned["report_type"].lower()
            if entity_type not in ENTITY_TYPES:
                raise ValueError(f"Unsupported entity_type in {rule_id}: {entity_type}")
            if report_type not in REPORT_TYPES:
                raise ValueError(f"Unsupported report_type in {rule_id}: {report_type}")
            if self.enforce_known_metrics and cleaned["canonical_metric"] not in KNOWN_CANONICAL_METRICS:
                raise ValueError(f"Unknown canonical_metric in {rule_id}: {cleaned['canonical_metric']!r}")
            has_matcher = any(cleaned[key] for key in ("item_id", "source_field", "normalized_label", "label_regex"))
            if not has_matcher and not cleaned["derivation_rule"]:
                raise ValueError(f"Rule {rule_id} has neither matcher nor derivation")
            if cleaned["label_regex"]:
                try:
                    re.compile(cleaned["label_regex"])
                except re.error as exc:
                    raise ValueError(f"Invalid label_regex in {rule_id}: {exc}") from exc
            try:
                priority = int(cleaned["priority"] or 0)
                sign_multiplier = float(cleaned["sign_multiplier"] or 1)
                unit_multiplier = float(cleaned["unit_multiplier"] or 1)
            except ValueError as exc:
                raise ValueError(f"Invalid numeric mapping metadata in {rule_id}") from exc
            if not math.isfinite(sign_multiplier) or sign_multiplier not in {-1.0, 1.0}:
                raise ValueError(f"Invalid sign_multiplier in {rule_id}: {sign_multiplier}")
            if not math.isfinite(unit_multiplier) or unit_multiplier <= 0:
                raise ValueError(f"Invalid unit_multiplier in {rule_id}: {unit_multiplier}")
            rule = MappingRule(
                rule_id=rule_id,
                canonical_metric=cleaned["canonical_metric"],
                entity_type=entity_type,
                report_type=report_type,
                source=(cleaned["source"] or "*").upper(),
                item_id=cleaned["item_id"].lower(),
                source_field=cleaned["source_field"].lower(),
                normalized_label=normalize_label(cleaned["normalized_label"]),
                label_regex=cleaned["label_regex"],
                priority=priority,
                sign_multiplier=sign_multiplier,
                unit_multiplier=unit_multiplier,
                derivation_rule=cleaned["derivation_rule"],
                valid_from=cleaned["valid_from"],
                valid_to=cleaned["valid_to"],
            )
            rules.append(rule)
        exact_seen: dict[tuple[str, ...], str] = {}
        for rule in rules:
            for matcher, value in (
                ("item_id", rule.item_id),
                ("source_field", rule.source_field),
                ("normalized_label", rule.normalized_label),
            ):
                if not value:
                    continue
                key = (
                    matcher, value, rule.entity_type, rule.report_type, rule.source,
                    str(rule.priority), rule.valid_from, rule.valid_to,
                )
                previous = exact_seen.get(key)
                if previous:
                    raise ValueError(
                        f"Ambiguous exact mapping at equal priority: {previous} and {rule.rule_id}"
                    )
                exact_seen[key] = rule.rule_id
        return sorted(rules, key=lambda rule: (rule.priority, rule.specificity, rule.rule_id), reverse=True)

    def _load_profiles(self) -> dict[str, str]:
        if not self.profiles_path or not self.profiles_path.exists():
            return {}
        from entity_classification_contract import load_layered_entity_profiles
        profiles = load_layered_entity_profiles(seed_path=self.profiles_path)
        for ticker, entity_type in profiles.items():
            if not ticker or entity_type not in ENTITY_TYPES - {"*", "unknown"}:
                raise ValueError(f"Invalid entity profile: {ticker!r} -> {entity_type!r}")
        return profiles

    def entity_type_for(self, ticker: str) -> str:
        return self.entity_profiles.get(str(ticker).strip().upper(), "unknown")

    @staticmethod
    def _compatible(
        rule: MappingRule,
        source: str,
        entity_type: str,
        report_type: str,
        as_of: str | None = None,
    ) -> bool:
        return (
            rule.report_type != "derived"
            and rule.entity_type in {"*", entity_type}
            and rule.report_type in {"*", report_type}
            and rule.source in {"*", source}
            and (not as_of or not rule.valid_from or as_of >= rule.valid_from)
            and (not as_of or not rule.valid_to or as_of <= rule.valid_to)
        )

    @staticmethod
    def _result(rule: MappingRule, method: str, confidence: float) -> dict[str, Any]:
        return {
            "canonical_metric": rule.canonical_metric,
            "match_method": method,
            "mapping_rule_id": rule.rule_id,
            "confidence": confidence,
            "priority": rule.priority,
            "sign_multiplier": rule.sign_multiplier,
            "unit_multiplier": rule.unit_multiplier,
            "derivation_rule": rule.derivation_rule or None,
        }

    def map_financial_item(
        self,
        source: str,
        entity_type: str,
        report_type: str,
        item_id: str | None,
        raw_label: str | None,
        source_field: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        source_key = str(source or "*").strip().upper()
        entity_key = str(entity_type or "unknown").strip().lower()
        report_key = str(report_type or "*").strip().lower()
        item_key = str(item_id or "").strip().lower()
        field_key = str(source_field or "").strip().lower()
        label = normalize_label(raw_label)
        label_ascii = normalize_label(raw_label, strip_accents=True)
        rules = [
            rule for rule in self.rules
            if self._compatible(rule, source_key, entity_key, report_key, as_of)
        ]

        for rule in rules:
            if rule.item_id and item_key == rule.item_id:
                return self._result(rule, "item_id", 1.0)
        for rule in rules:
            if rule.source_field and field_key == rule.source_field:
                return self._result(rule, "source_field", 1.0)
        for rule in rules:
            if not rule.normalized_label:
                continue
            if label == rule.normalized_label:
                return self._result(rule, "exact_label", 1.0)
            if label_ascii == normalize_label(rule.normalized_label, strip_accents=True):
                return self._result(rule, "exact_label", 0.98)
        for rule in rules:
            if rule.label_regex and (
                re.search(rule.label_regex, label) or re.search(rule.label_regex, label_ascii)
            ):
                return self._result(rule, "regex", 0.9)
        return None

    def derivation_for(self, canonical_metric: str, entity_type: str) -> dict[str, Any] | None:
        candidates = [
            rule for rule in self.rules
            if rule.canonical_metric == canonical_metric
            and rule.report_type == "derived"
            and rule.entity_type in {"*", entity_type}
            and rule.derivation_rule
        ]
        return self._result(candidates[0], "derived", 1.0) if candidates else None

    def reported_metrics(self) -> set[str]:
        return {rule.canonical_metric for rule in self.rules if rule.report_type != "derived"}

    def diagnose_ticker(self, root: Path, ticker: str) -> dict[str, Any]:
        ticker = ticker.strip().upper()
        entity_type = self.entity_type_for(ticker)
        matches = []
        for path in sorted((Path(root) / "data_bctc").glob(f"{ticker}_*.csv")):
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    result = self.map_financial_item(
                        row.get("source", ""), entity_type, row.get("report_type", ""),
                        row.get("item_id"), row.get("item"), row.get("source_field"),
                    )
                    if result:
                        matches.append({
                            "source_file": path.relative_to(root).as_posix(),
                            "source": row.get("source"),
                            "report_type": row.get("report_type"),
                            "raw_item_id": row.get("item_id"),
                            "raw_label": row.get("item"),
                            **result,
                        })
        derivations = {
            metric: self.derivation_for(metric, entity_type)
            for metric in ("ebit", "ebitda", "sga")
        }
        return {
            "schema_version": "1.0.0",
            "ticker": ticker,
            "entity_type": entity_type,
            "registry": self.mapping_path.relative_to(root).as_posix(),
            "registry_version": self.metadata.get("registry_version"),
            "registry_provenance": self.metadata.get("provenance"),
            "matches": matches,
            "derivations_declared_not_executed": derivations,
        }


@lru_cache(maxsize=1)
def get_default_registry() -> FinancialMappingRegistry:
    return FinancialMappingRegistry(
        DEFAULT_MAPPING_PATH, DEFAULT_PROFILES_PATH, DEFAULT_METADATA_PATH,
        require_metadata=True, enforce_known_metrics=True,
    )


def map_financial_item(
    source: str,
    entity_type: str,
    report_type: str,
    item_id: str | None,
    raw_label: str | None,
    source_field: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any] | None:
    return get_default_registry().map_financial_item(
        source, entity_type, report_type, item_id, raw_label, source_field, as_of
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect deterministic financial registry mappings")
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = get_default_registry().diagnose_ticker(ROOT_DIR, args.ticker)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
