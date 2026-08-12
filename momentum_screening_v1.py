"""Vectorized, non-recommendation Momentum V1 screening over Phase 3 features."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from market_feature_store_v1 import snapshot
from strategy_framework import RegistryState, StrategyPlugin, evaluate_eligibility, load_strategy_registry


MOMENTUM_ID = "MOMENTUM_V1"
MOMENTUM_DEPENDENCIES = ("market.return_5d", "market.distance_ma_5", "market.volatility_5")
RANKING_RULE = "score_desc_then_canonical_instrument_id_asc_ordinal_rank"


@dataclass(frozen=True)
class MomentumRun:
    as_of: pd.Timestamp
    eligibility: pd.DataFrame
    ranked: pd.DataFrame
    report: Mapping[str, Any]


def momentum_plugin() -> StrategyPlugin:
    plugin = load_strategy_registry()[MOMENTUM_ID]
    if plugin.registry_state != RegistryState.IMPLEMENTED or not plugin.execution_enabled:
        raise ValueError("MOMENTUM_V1 must be implemented and executable")
    if tuple(plugin.required_features) != MOMENTUM_DEPENDENCIES:
        raise ValueError("MOMENTUM_V1 dependencies do not match the V1 evaluator")
    return plugin


def _as_timestamp(as_of: Any, frame: pd.DataFrame) -> pd.Timestamp:
    timestamp = pd.to_datetime(as_of, utc=True) if as_of is not None else pd.to_datetime(frame["session"], utc=True).max()
    if pd.isna(timestamp):
        raise ValueError("as_of is required when historical features are empty")
    return timestamp


def _plain(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None or (not isinstance(value, (list, dict, tuple)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps({key: _plain(item) for key, item in value.items()}, sort_keys=True, separators=(",", ":"))


def _result_record(result: Any) -> dict[str, Any]:
    return {
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "canonical_instrument_id": result.instrument_id,
        "as_of": result.as_of,
        "eligible": result.eligible,
        "status": result.status,
        "blockers": json.dumps(result.blockers),
        "reasons": json.dumps(result.reasons),
        "score": result.score,
        "rank": result.rank,
        "component_values": _json(result.component_values),
        "component_statuses": _json(result.component_statuses),
        "quality_metadata": _json(result.quality_metadata),
        "pit_metadata": _json(result.pit_metadata),
        "basis_metadata": _json(result.basis_metadata),
        "feature_lineage": _json(result.feature_lineage),
        "strategy_lineage": _json(result.strategy_lineage),
    }


def evaluate_momentum(historical: pd.DataFrame, *, as_of: Any | None = None,
                      instruments: Iterable[str] | None = None,
                      plugin: StrategyPlugin | None = None) -> MomentumRun:
    """Evaluate a single observed session only; later sessions are never read into the rank.

    Contract evaluation is row-level because its blockers are feature-specific.  Normalization,
    score calculation, and rank are vectorized across the resulting eligible population.
    """
    plugin = plugin or momentum_plugin()
    required_columns = {"canonical_instrument_id", "session", "instrument_class", "price_basis_status",
                        "volume_basis_status", "pit_status", "quality_status", "feature_version",
                        *MOMENTUM_DEPENDENCIES,
                        *(f"{feature}__status" for feature in MOMENTUM_DEPENDENCIES),
                        *(f"{feature}__reason" for feature in MOMENTUM_DEPENDENCIES)}
    missing = sorted(required_columns - set(historical.columns))
    if missing:
        raise ValueError(f"Phase 3 historical frame missing Momentum columns: {missing}")
    frame = historical.copy()
    frame["session"] = pd.to_datetime(frame["session"], utc=True)
    selected_as_of = _as_timestamp(as_of, frame)
    # Phase 3's snapshot contract is one latest feature-bearing row per instrument on or before
    # as_of.  An exact-session filter would silently omit instruments with a missing latest
    # session rather than returning their explicit feature and basis blockers.
    candidates = snapshot(frame, selected_as_of).copy()
    if instruments is not None:
        candidates = candidates[candidates["canonical_instrument_id"].isin(tuple(instruments))]
    candidates = candidates.sort_values("canonical_instrument_id", kind="stable").reset_index(drop=True)
    candidates["feature_session"] = candidates["session"]
    candidates["as_of"] = selected_as_of.isoformat()
    records = [_result_record(evaluate_eligibility(plugin, row)) for row in candidates.to_dict("records")]
    output = pd.DataFrame(records)
    if output.empty:
        output = pd.DataFrame(columns=["strategy_id", "strategy_version", "canonical_instrument_id", "as_of",
                                       "eligible", "status", "blockers", "reasons", "score", "rank"])
    for feature in MOMENTUM_DEPENDENCIES:
        output[feature] = candidates[feature].to_numpy() if len(candidates) else pd.Series(dtype=float)
        output[f"{feature}__status"] = candidates[f"{feature}__status"].to_numpy() if len(candidates) else pd.Series(dtype=str)
    output["feature_session"] = candidates["feature_session"].to_numpy() if len(candidates) else pd.Series(dtype="datetime64[ns, UTC]")
    output["normalization"] = ""
    output["weights"] = ""
    eligible = output["eligible"].fillna(False).astype(bool)
    scored = output.loc[eligible].copy()
    components = plugin.scoring_contract["components"]
    weights = {item["feature_id"]: float(item["weight"]) for item in components}
    if tuple(item["feature_id"] for item in components) != MOMENTUM_DEPENDENCIES or not np.isclose(sum(weights.values()), 1.0):
        raise ValueError("MOMENTUM_V1 scoring contract is inconsistent")
    for item in components:
        feature = item["feature_id"]
        ascending = item["normalization"] == "cross_sectional_percentile_ascending"
        if item["normalization"] not in {"cross_sectional_percentile_ascending", "cross_sectional_percentile_descending"}:
            raise ValueError(f"unsupported normalization: {item['normalization']}")
        scored[f"{feature}__normalized"] = scored[feature].rank(method="average", pct=True, ascending=ascending) * 100.0
        scored[f"{feature}__contribution"] = scored[f"{feature}__normalized"] * weights[feature]
    contribution_columns = [f"{feature}__contribution" for feature in MOMENTUM_DEPENDENCIES]
    scored["score"] = scored[contribution_columns].sum(axis=1).round(10)
    scored = scored.sort_values(["score", "canonical_instrument_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    scored["rank"] = pd.Series(range(1, len(scored) + 1), dtype="Int64")
    normalization = {item["feature_id"]: item["normalization"] for item in components}
    scored["normalization"] = json.dumps(normalization, sort_keys=True, separators=(",", ":"))
    scored["weights"] = json.dumps(weights, sort_keys=True, separators=(",", ":"))
    if not scored.empty:
        score_columns = ["score", "rank", "normalization", "weights",
                         *(f"{feature}__normalized" for feature in MOMENTUM_DEPENDENCIES),
                         *(f"{feature}__contribution" for feature in MOMENTUM_DEPENDENCIES)]
        score_by_instrument = scored.set_index("canonical_instrument_id")[score_columns]
        output = output.drop(columns=["score", "rank", "normalization", "weights"]).merge(
            score_by_instrument, how="left", left_on="canonical_instrument_id", right_index=True, sort=False)
    output["score"] = output["score"].where(output["eligible"].fillna(False), None)
    output["rank"] = output["rank"].where(output["eligible"].fillna(False), None)
    output = output.sort_values("canonical_instrument_id", kind="stable").reset_index(drop=True)
    ranked = output[output["eligible"].fillna(False)].sort_values("rank", kind="stable").reset_index(drop=True)
    blocker_counts: dict[str, int] = {}
    for value in output.loc[~output["eligible"].fillna(False), "blockers"]:
        for blocker in json.loads(value):
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    candidate_count = len(output)
    eligible_count = int(output["eligible"].fillna(False).sum())
    scored_count = int(output["score"].notna().sum())
    ranked_count = int(output["rank"].notna().sum())
    report = {
        "schema_version": "1.0.0", "strategy_id": plugin.strategy_id,
        "strategy_version": plugin.strategy_version, "as_of": selected_as_of.isoformat(),
        "candidate_instruments": candidate_count, "eligible": eligible_count,
        "blocked": candidate_count - eligible_count, "scored": scored_count, "ranked": ranked_count,
        "eligible_unscored_exceptional": eligible_count - scored_count,
        "candidate_reconciliation": candidate_count == eligible_count + (candidate_count - eligible_count),
        "eligible_reconciliation": eligible_count == scored_count and scored_count == ranked_count,
        "exact_reconciliation": candidate_count == eligible_count + (candidate_count - eligible_count) and eligible_count == scored_count == ranked_count,
        "blocker_distribution": dict(sorted(blocker_counts.items())), "ranking_rule": RANKING_RULE,
        "candidate_universe_rule": "latest_phase3_feature_row_per_instrument_on_or_before_as_of",
        "feature_session_at_as_of": int(candidates["feature_session"].eq(selected_as_of).sum()),
        "feature_session_before_as_of": int(candidates["feature_session"].lt(selected_as_of).sum()),
        "feature_session_distribution": {timestamp.isoformat(): int(count) for timestamp, count in
                                           candidates["feature_session"].value_counts().sort_index().items()},
        "scoring_contract": plugin.scoring_contract,
        "not_investment_recommendation": True,
    }
    return MomentumRun(selected_as_of, output, ranked, report)


def screen_momentum(results: pd.DataFrame, *, eligible_only: bool = True, top_n: int | None = None,
                    max_rank: int | None = None, min_score: float | None = None,
                    instruments: Iterable[str] | None = None, statuses: Iterable[str] | None = None,
                    blockers: Iterable[str] | None = None) -> pd.DataFrame:
    """Apply deterministic reusable filters; rank is never fabricated for blocked rows."""
    output = results.copy()
    if eligible_only:
        output = output[output["eligible"].fillna(False)]
    if max_rank is not None:
        output = output[output["rank"].le(max_rank)]
    if min_score is not None:
        output = output[output["score"].ge(min_score)]
    if instruments is not None:
        output = output[output["canonical_instrument_id"].isin(tuple(instruments))]
    if statuses is not None:
        output = output[output["status"].isin(tuple(statuses))]
    if blockers is not None:
        expected = set(blockers)
        output = output[output["blockers"].map(lambda item: bool(expected & set(json.loads(item))))]
    output = output.sort_values(["rank", "canonical_instrument_id"], kind="stable", na_position="last")
    return output.head(top_n) if top_n is not None else output.reset_index(drop=True)


def load_phase3_historical(root: Path) -> pd.DataFrame:
    """Read retained Phase 3 partitions without contacting any provider."""
    paths = sorted(root.glob("historical_partitioned/session_month=*/part-000.parquet"))
    if not paths:
        raise ValueError(f"no Phase 3 partitions found at {root}")
    columns = ["canonical_instrument_id", "session", "instrument_class", "price_basis_status", "price_basis_reason",
               "volume_basis_status", "pit_status", "pit_reason", "quality_status", "feature_version",
               "raw_observation_id", *MOMENTUM_DEPENDENCIES,
               *(f"{feature}__status" for feature in MOMENTUM_DEPENDENCIES),
               *(f"{feature}__reason" for feature in MOMENTUM_DEPENDENCIES)]
    return pd.concat([pd.read_parquet(path, columns=columns) for path in paths], ignore_index=True)


def write_momentum_artifacts(run: MomentumRun, root: Path, *, top_n: int = 25) -> Mapping[str, Path]:
    """Write only Phase 4B derived outputs, including an explicit empty-ranked artifact when blocked."""
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "eligibility": root / "momentum_eligibility.parquet",
        "ranked_results": root / "momentum_ranked.parquet",
        "screener": root / "momentum_screener_top_n.parquet",
        "report": root / "coverage_report.json",
    }
    run.eligibility.to_parquet(paths["eligibility"], index=False)
    run.ranked.to_parquet(paths["ranked_results"], index=False)
    screen_momentum(run.eligibility, top_n=top_n).to_parquet(paths["screener"], index=False)
    paths["report"].write_text(json.dumps(run.report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return paths
