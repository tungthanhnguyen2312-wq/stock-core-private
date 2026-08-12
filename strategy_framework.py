"""Deterministic, feature-level strategy framework.

This module is deliberately a framework rather than a signal implementation.  A strategy is
eligible only when its own declared dependencies are usable; no instrument receives a global
qualification status and no ineligible result is assigned a synthetic score.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping


FRAMEWORK_VERSION = "1.0.0"
REGISTRY_PATH = Path(__file__).with_name("config") / "strategy_registry.json"


class RegistryState(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    IMPLEMENTATION_READY_FRAMEWORK = "IMPLEMENTATION_READY_FRAMEWORK"
    DECLARED_NON_EXECUTABLE = "DECLARED_NON_EXECUTABLE"


class SuspectInputPolicy(StrEnum):
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    REJECT = "REJECT"


ScoreHook = Callable[[Mapping[str, Any]], float]


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class StrategyPlugin:
    """The complete declaration a deterministic strategy evaluator can consume."""

    strategy_id: str
    strategy_version: str
    registry_state: RegistryState
    execution_enabled: bool
    execution_blocker: str | None
    required_features: tuple[str, ...]
    optional_features: tuple[str, ...]
    accepted_feature_statuses: tuple[str, ...]
    accepted_pit_statuses: tuple[str, ...]
    accepted_price_bases: tuple[str, ...]
    accepted_volume_bases: tuple[str, ...]
    applicable_instrument_classes: tuple[str, ...]
    applicable_sectors: tuple[str, ...]
    eligibility_rules: tuple[str, ...]
    scoring_handler: str | None
    scoring_contract: Mapping[str, Any]
    suspect_input_policy: SuspectInputPolicy
    lineage_version: str
    scoring_hook: ScoreHook | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_version or not self.lineage_version:
            raise ValueError("strategy identity and lineage versions are required")
        if not self.required_features:
            raise ValueError(f"{self.strategy_id}: required_features must be explicit")
        if set(self.required_features) & set(self.optional_features):
            raise ValueError(f"{self.strategy_id}: a feature cannot be both required and optional")
        if not self.accepted_feature_statuses or not self.accepted_pit_statuses:
            raise ValueError(f"{self.strategy_id}: feature and PIT status contracts are required")
        if not self.applicable_instrument_classes or not self.applicable_sectors or not self.eligibility_rules:
            raise ValueError(f"{self.strategy_id}: applicability must be explicit")
        if self.execution_enabled and self.scoring_hook is None and not self.scoring_handler:
            raise ValueError(f"{self.strategy_id}: executable strategies require a scoring hook or handler")
        if self.execution_enabled and not self.scoring_contract:
            raise ValueError(f"{self.strategy_id}: executable strategies require a scoring contract")
        if not self.execution_enabled and not self.execution_blocker:
            raise ValueError(f"{self.strategy_id}: non-executable strategies require an explicit blocker")

    @property
    def contract_lineage_id(self) -> str:
        contract = {
            "framework_version": FRAMEWORK_VERSION,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "lineage_version": self.lineage_version,
            "required_features": self.required_features,
            "optional_features": self.optional_features,
            "accepted_feature_statuses": self.accepted_feature_statuses,
            "accepted_pit_statuses": self.accepted_pit_statuses,
            "accepted_price_bases": self.accepted_price_bases,
            "accepted_volume_bases": self.accepted_volume_bases,
            "instrument_classes": self.applicable_instrument_classes,
            "sectors": self.applicable_sectors,
            "eligibility_rules": self.eligibility_rules,
            "scoring_handler": self.scoring_handler,
            "scoring_contract": self.scoring_contract,
            "suspect_input_policy": self.suspect_input_policy.value,
        }
        return sha256(_stable_json(contract).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StrategyResult:
    """A deterministic result, with score and rank absent for every ineligible result."""

    strategy_id: str
    strategy_version: str
    instrument_id: str
    as_of: str
    eligible: bool
    status: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]
    score: float | None
    rank: int | None
    component_values: Mapping[str, Any]
    component_statuses: Mapping[str, str]
    quality_metadata: Mapping[str, Any]
    pit_metadata: Mapping[str, Any]
    basis_metadata: Mapping[str, Any]
    feature_lineage: Mapping[str, Any]
    strategy_lineage: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.eligible and (self.score is not None or self.rank is not None):
            raise ValueError("ineligible strategy results must not contain score or rank")
        if self.eligible and self.blockers:
            raise ValueError("eligible strategy results cannot contain blockers")


def _feature_value(row: Mapping[str, Any], feature: str) -> Any:
    values = row.get("feature_values")
    return values.get(feature) if isinstance(values, Mapping) else row.get(feature)


def _feature_status(row: Mapping[str, Any], feature: str) -> str:
    statuses = row.get("feature_statuses")
    if isinstance(statuses, Mapping) and feature in statuses:
        return str(statuses[feature])
    return str(row.get(f"{feature}__status", "UNKNOWN"))


def _feature_reason(row: Mapping[str, Any], feature: str) -> str | None:
    reasons = row.get("feature_reasons")
    if isinstance(reasons, Mapping) and feature in reasons:
        return str(reasons[feature])
    value = row.get(f"{feature}__reason")
    return None if _missing(value) else str(value)


def evaluate_eligibility(plugin: StrategyPlugin, row: Mapping[str, Any]) -> StrategyResult:
    """Apply one plugin's dependency contract to one Phase 3 feature row.

    Phase 3 status columns use ``<feature_id>__status`` and ``<feature_id>__reason``.  The
    mapping forms are supported as an equivalent test/integration representation.
    """
    blockers: list[str] = []
    reasons: list[str] = []
    components: dict[str, Any] = {}
    statuses: dict[str, str] = {}
    quality_warnings: list[str] = []
    instrument_class = str(row.get("instrument_class", "UNKNOWN"))
    sector = str(row.get("sector", "UNKNOWN"))
    price_basis = str(row.get("price_basis_status", row.get("price_basis", "UNKNOWN")))
    volume_basis = str(row.get("volume_basis_status", "UNKNOWN"))
    pit_status = str(row.get("pit_status", "UNKNOWN"))

    if instrument_class not in plugin.applicable_instrument_classes:
        blockers.append("INSTRUMENT_CLASS_NOT_APPLICABLE")
        reasons.append(f"instrument_class:{instrument_class}")
    if "ALL" not in plugin.applicable_sectors and sector not in plugin.applicable_sectors:
        blockers.append("SECTOR_NOT_APPLICABLE")
        reasons.append(f"sector:{sector}")
    if price_basis not in plugin.accepted_price_bases:
        blockers.append("PRICE_BASIS_NOT_ACCEPTED")
        reasons.append(f"price_basis:{price_basis}")
    if plugin.accepted_volume_bases and volume_basis not in plugin.accepted_volume_bases:
        blockers.append("VOLUME_BASIS_NOT_ACCEPTED")
        reasons.append(f"volume_basis:{volume_basis}")
    if pit_status not in plugin.accepted_pit_statuses:
        blockers.append("PIT_STATUS_NOT_ACCEPTED")
        reasons.append(f"pit_status:{pit_status}")

    for feature in plugin.required_features + plugin.optional_features:
        value = _feature_value(row, feature)
        status = _feature_status(row, feature)
        reason = _feature_reason(row, feature)
        components[feature] = value
        statuses[feature] = status
        is_required = feature in plugin.required_features
        if status == "SUSPECT":
            quality_warnings.append(f"suspect_feature:{feature}")
            if plugin.suspect_input_policy == SuspectInputPolicy.REJECT and is_required:
                blockers.append("SUSPECT_INPUT_REJECTED")
                reasons.append(f"feature:{feature}")
        if not is_required:
            continue
        if status == "BLOCKED":
            blockers.append("FEATURE_BLOCKED")
            reasons.append(f"feature:{feature}:{reason or 'unspecified'}")
            continue
        if _missing(value):
            blockers.append("MISSING_REQUIRED_FEATURE")
            reasons.append(f"feature:{feature}")
            continue
        if status not in plugin.accepted_feature_statuses:
            blockers.append("FEATURE_STATUS_NOT_ACCEPTED")
            reasons.append(f"feature:{feature}:status:{status}")

    blockers = list(dict.fromkeys(blockers))
    reasons = list(dict.fromkeys(reasons))
    eligible = not blockers
    strategy_lineage = {
        "framework_version": FRAMEWORK_VERSION,
        "strategy_id": plugin.strategy_id,
        "strategy_version": plugin.strategy_version,
        "lineage_version": plugin.lineage_version,
        "contract_lineage_id": plugin.contract_lineage_id,
        "registry_state": plugin.registry_state.value,
    }
    return StrategyResult(
        strategy_id=plugin.strategy_id, strategy_version=plugin.strategy_version,
        instrument_id=str(row.get("canonical_instrument_id", row.get("instrument_id", "UNKNOWN"))),
        as_of=str(row.get("as_of", row.get("session", "UNKNOWN"))), eligible=eligible,
        status="ELIGIBLE" if eligible else "INELIGIBLE", blockers=tuple(blockers), reasons=tuple(reasons),
        score=None, rank=None, component_values=components, component_statuses=statuses,
        quality_metadata={"quality_status": row.get("quality_status", "UNKNOWN"),
                          "warnings": tuple(quality_warnings)},
        pit_metadata={"pit_status": pit_status, "pit_reason": row.get("pit_reason")},
        basis_metadata={"price_basis_status": price_basis, "volume_basis_status": volume_basis},
        feature_lineage={"feature_version": row.get("feature_version"),
                         "raw_observation_id": row.get("raw_observation_id")},
        strategy_lineage=strategy_lineage,
    )


def evaluate_strategy(plugin: StrategyPlugin, row: Mapping[str, Any]) -> StrategyResult:
    """Evaluate dependencies then invoke a bound scalar hook where one is declared."""
    base = evaluate_eligibility(plugin, row)
    blockers = list(base.blockers)
    reasons = list(base.reasons)
    if not plugin.execution_enabled:
        blockers.append("STRATEGY_NOT_EXECUTABLE")
        reasons.append(plugin.execution_blocker or "strategy_execution_disabled")
    elif plugin.scoring_hook is None:
        blockers.append("SCORING_HOOK_NOT_BOUND")
        reasons.append(plugin.scoring_handler or "scoring_handler_not_bound")
    blockers = list(dict.fromkeys(blockers))
    reasons = list(dict.fromkeys(reasons))
    eligible = not blockers
    score = float(plugin.scoring_hook(row)) if eligible and plugin.scoring_hook is not None else None
    return replace(base, eligible=eligible, status="ELIGIBLE" if eligible else "INELIGIBLE",
                   blockers=tuple(blockers), reasons=tuple(reasons), score=score)


def _plugin_from_record(record: Mapping[str, Any]) -> StrategyPlugin:
    return StrategyPlugin(
        strategy_id=str(record["strategy_id"]), strategy_version=str(record["strategy_version"]),
        registry_state=RegistryState(record["registry_state"]), execution_enabled=bool(record["execution_enabled"]),
        execution_blocker=record.get("execution_blocker"),
        required_features=tuple(record["required_features"]), optional_features=tuple(record["optional_features"]),
        accepted_feature_statuses=tuple(record["accepted_feature_statuses"]),
        accepted_pit_statuses=tuple(record["accepted_pit_statuses"]),
        accepted_price_bases=tuple(record["accepted_price_bases"]),
        accepted_volume_bases=tuple(record["accepted_volume_bases"]),
        applicable_instrument_classes=tuple(record["applicable_instrument_classes"]),
        applicable_sectors=tuple(record["applicable_sectors"]),
        eligibility_rules=tuple(record["eligibility_rules"]),
        scoring_handler=record.get("scoring_handler"), scoring_contract=record.get("scoring_contract", {}),
        suspect_input_policy=SuspectInputPolicy(record["suspect_input_policy"]),
        lineage_version=str(record["lineage_version"]),
    )


def load_strategy_registry(path: Path = REGISTRY_PATH) -> dict[str, StrategyPlugin]:
    """Load and validate the JSON registry without attaching signal implementations."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FRAMEWORK_VERSION:
        raise ValueError("strategy registry schema version is not supported")
    records = payload.get("strategies", [])
    identifiers = [record.get("strategy_id") for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("strategy registry contains duplicate identifiers")
    registry = {record["strategy_id"]: _plugin_from_record(record) for record in records}
    validate_registry(registry)
    return dict(sorted(registry.items()))


def validate_registry(registry: Mapping[str, StrategyPlugin]) -> None:
    """Reject incomplete, duplicate, or executable-without-hook registry declarations."""
    if not registry:
        raise ValueError("strategy registry is empty")
    if len(registry) != len(set(registry)):
        raise ValueError("strategy registry contains duplicate identifiers")
    for strategy_id, plugin in registry.items():
        if strategy_id != plugin.strategy_id:
            raise ValueError("strategy registry key does not match strategy identifier")
        if plugin.registry_state == RegistryState.DECLARED_NON_EXECUTABLE and plugin.execution_enabled:
            raise ValueError(f"{strategy_id}: declared non-executable strategy cannot execute")
        if plugin.registry_state == RegistryState.IMPLEMENTATION_READY_FRAMEWORK and (plugin.execution_enabled or plugin.scoring_hook is not None):
            raise ValueError(f"{strategy_id}: Phase 4A framework entry cannot include scoring logic")
        if plugin.registry_state == RegistryState.IMPLEMENTED and (not plugin.execution_enabled or not plugin.scoring_handler):
            raise ValueError(f"{strategy_id}: implemented strategy requires executable handler")


def registry_records(registry: Mapping[str, StrategyPlugin] | None = None) -> list[dict[str, Any]]:
    """Return the registry in JSON-safe deterministic order for external consumers."""
    source = registry or load_strategy_registry()
    return [{
        "strategy_id": plugin.strategy_id, "strategy_version": plugin.strategy_version,
        "registry_state": plugin.registry_state.value, "execution_enabled": plugin.execution_enabled,
        "execution_blocker": plugin.execution_blocker, "required_features": list(plugin.required_features),
        "optional_features": list(plugin.optional_features),
        "accepted_feature_statuses": list(plugin.accepted_feature_statuses),
        "accepted_pit_statuses": list(plugin.accepted_pit_statuses),
        "accepted_price_bases": list(plugin.accepted_price_bases),
        "accepted_volume_bases": list(plugin.accepted_volume_bases),
        "applicable_instrument_classes": list(plugin.applicable_instrument_classes),
        "applicable_sectors": list(plugin.applicable_sectors),
        "eligibility_rules": list(plugin.eligibility_rules),
        "scoring_handler": plugin.scoring_handler, "scoring_contract": dict(plugin.scoring_contract),
        "suspect_input_policy": plugin.suspect_input_policy.value,
        "lineage_version": plugin.lineage_version, "contract_lineage_id": plugin.contract_lineage_id,
    } for _, plugin in sorted(source.items())]
