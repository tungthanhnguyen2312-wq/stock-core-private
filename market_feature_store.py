"""Deterministic, vectorized market-feature foundation.

The production target is Polars/Parquet/Arrow.  This first pure foundation uses pandas, already
present in the repository, to keep the contract executable before adding a runtime migration.
It performs no network or AI work and does not loop over individual tickers.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

import pandas as pd

from market_data_contracts import ExceptionDisposition, FeatureStatus, PriceBasis, QualityException


REQUIRED_MARKET_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class StrategyDeclaration:
    strategy_id: str
    required_features: tuple[str, ...]
    acceptable_statuses: tuple[FeatureStatus, ...]
    acceptable_price_bases: tuple[PriceBasis, ...]
    pit_required: bool = False
    applicable_instrument_classes: tuple[str, ...] = ("EQUITY",)


def validate_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_MARKET_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"market frame missing required columns: {missing}")
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.upper()
    result["date"] = pd.to_datetime(result["date"], utc=False)
    return result.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def build_historical_features(frame: pd.DataFrame, *, price_basis: PriceBasis,
                              window: int = 3) -> pd.DataFrame:
    """Build a deterministic historical table with vectorized per-instrument windows."""
    if window < 2:
        raise ValueError("window must be at least 2")
    result = validate_market_frame(frame)
    grouped = result.groupby("ticker", sort=False, group_keys=False)
    result["market.close"] = result["close"]
    result["market.return_1d"] = grouped["close"].pct_change(fill_method=None)
    result[f"market.ma_{window}"] = grouped["close"].transform(
        lambda values: values.rolling(window, min_periods=window).mean())
    result[f"market.volatility_{window}"] = grouped["market.return_1d"].transform(
        lambda values: values.rolling(window, min_periods=window).std(ddof=0))
    result["market.volume_ratio"] = result["volume"] / grouped["volume"].transform(
        lambda values: values.rolling(window, min_periods=window).median())
    result["feature_status"] = FeatureStatus.DERIVED.value
    result["price_basis"] = price_basis.value
    result["pit_status"] = (FeatureStatus.QUALIFIED.value if price_basis == PriceBasis.PIT_OBSERVED
                            else FeatureStatus.HISTORICAL_ONLY.value)
    return result


def build_cross_sectional_snapshot(historical_features: pd.DataFrame, *, session: Any | None = None) -> pd.DataFrame:
    """One latest/selected session row per instrument for screening and comparison.

    Values and status columns are copied rather than recomputed, so the snapshot preserves the
    historical table's feature lineage and cannot silently widen a feature's authority.
    """
    result = validate_market_frame(historical_features)
    selected = pd.to_datetime(session) if session is not None else result["date"].max()
    snapshot = result[result["date"].eq(selected)].copy()
    return snapshot.sort_values("ticker", kind="stable").reset_index(drop=True)


def build_temporal_feature_records(historical_features: pd.DataFrame, *,
                                   reference_at: Any,
                                   knowledge_cutoff: Any = None,
                                   domain: str = "daily_market") -> list[dict[str, Any]]:
    """Convert feature dataframe into deterministic records with field-level temporal envelopes."""
    from field_temporal_contract import wrap_temporal_fields

    frame = validate_market_frame(historical_features)
    records = []
    for row in frame.to_dict(orient="records"):
        date_val = row["date"]
        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
        ticker = str(row["ticker"])
        price_basis = str(row.get("price_basis", PriceBasis.UNKNOWN.value))
        raw_fields = {
            k: v for k, v in row.items()
            if k not in {"ticker", "date", "feature_status", "price_basis", "pit_status"}
        }
        temporal_fields = wrap_temporal_fields(
            raw_fields,
            observed_at=date_str,
            as_of=date_str,
            domain=domain,
            reference_at=reference_at,
            knowledge_cutoff=knowledge_cutoff,
            price_basis=price_basis,
            quality_status=row.get("feature_status", FeatureStatus.DERIVED.value),
            source="market_feature_store",
        )
        records.append({
            "ticker": ticker,
            "date": date_str,
            "feature_status": row.get("feature_status", FeatureStatus.DERIVED.value),
            "price_basis": price_basis,
            "pit_status": row.get("pit_status", FeatureStatus.HISTORICAL_ONLY.value),
            "temporal_fields": {k: tf.record() for k, tf in temporal_fields.items()},
        })
    return records


def quality_exceptions(records: Iterable[Mapping[str, Any]]) -> list[QualityException]:
    """Evaluate raw rows without deleting or rewriting them.

    Rules are domain-aware: OHLC order, non-negative quantities, and log-scale price/volume
    jumps.  Statistical flags are review candidates, not automatic source-error verdicts.
    """
    frame = pd.DataFrame(list(records))
    if frame.empty:
        return []
    required = {"observation_id", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"quality records missing columns: {missing}")
    output: list[QualityException] = []
    duplicated_ids = frame[frame.duplicated("observation_id", keep=False)]
    for oid in sorted(duplicated_ids["observation_id"].astype(str).unique()):
        output.append(QualityException(oid, "duplicate_observation_identity", "high", None,
                                       {"duplicate_count": int((frame["observation_id"].astype(str) == oid).sum())},
                                       ExceptionDisposition.UNRESOLVED))
    for row in frame.itertuples(index=False):
        data = row._asdict()
        oid = str(data["observation_id"])
        numeric = {key: data[key] for key in ("open", "high", "low", "close", "volume")}
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
               for value in numeric.values()):
            output.append(QualityException(oid, "invalid_numeric_value", "high", numeric,
                                           {}, ExceptionDisposition.UNRESOLVED))
            continue
        if data["high"] < max(data["open"], data["close"], data["low"]) or data["low"] > min(data["open"], data["close"], data["high"]):
            output.append(QualityException(oid, "impossible_ohlc_relation", "high", numeric,
                                           {}, ExceptionDisposition.UNRESOLVED))
    ordered = frame.sort_values([column for column in ("ticker", "date") if column in frame.columns], kind="stable")
    if {"ticker", "date"}.issubset(ordered.columns):
        previous = ordered.groupby("ticker", sort=False)["close"].shift(1)
        changes = (ordered["close"] / previous).where((ordered["close"] > 0) & (previous > 0))
        for index in ordered.index[changes.gt(3) | changes.lt(1 / 3)]:
            data = ordered.loc[index].to_dict()
            output.append(QualityException(str(data["observation_id"]), "extreme_log_return", "medium",
                                           data["close"], {"previous_close": previous.loc[index], "ratio": changes.loc[index]},
                                           ExceptionDisposition.UNRESOLVED))
        returns = changes.where(changes > 0).map(lambda value: None if pd.isna(value) else math.log(value))
        median = returns.groupby(ordered["ticker"], sort=False).transform(
            lambda values: values.rolling(20, min_periods=5).median())
        mad = (returns - median).abs().groupby(ordered["ticker"], sort=False).transform(
            lambda values: values.rolling(20, min_periods=5).median())
        robust_outlier = (returns - median).abs() > (8 * mad).where(mad > 0)
        for index in ordered.index[robust_outlier.fillna(False)]:
            data = ordered.loc[index].to_dict()
            output.append(QualityException(str(data["observation_id"]), "rolling_mad_return_outlier", "medium",
                                           data["close"], {"log_return": returns.loc[index], "rolling_median": median.loc[index], "rolling_mad": mad.loc[index]},
                                           ExceptionDisposition.UNRESOLVED))
        volume_ratio = (ordered["volume"] / ordered.groupby("ticker", sort=False)["volume"].shift(1)).where(
            lambda values: values > 0)
        for index in ordered.index[volume_ratio.gt(10) | volume_ratio.lt(.1)]:
            data = ordered.loc[index].to_dict()
            output.append(QualityException(str(data["observation_id"]), "extreme_log_volume_change", "medium",
                                           data["volume"], {"volume_ratio": volume_ratio.loc[index]},
                                           ExceptionDisposition.UNRESOLVED))
        stale = ordered.groupby("ticker", sort=False)["close"].transform(
            lambda values: values.rolling(5, min_periods=5).apply(lambda window: float(window.nunique() == 1), raw=False).eq(1))
        for index in ordered.index[stale.fillna(False)]:
            data = ordered.loc[index].to_dict()
            output.append(QualityException(str(data["observation_id"]), "stale_or_frozen_series", "low",
                                           data["close"], {"window_sessions": 5}, ExceptionDisposition.UNRESOLVED))
        if "exchange_limit_pct" in ordered.columns:
            limit_breach = (changes - 1).abs() > ordered["exchange_limit_pct"]
            for index in ordered.index[limit_breach.fillna(False)]:
                data = ordered.loc[index].to_dict()
                output.append(QualityException(str(data["observation_id"]), "exchange_limit_anomaly", "medium",
                                               data["close"], {"return": changes.loc[index] - 1,
                                                               "exchange_limit_pct": data["exchange_limit_pct"]},
                                               ExceptionDisposition.UNRESOLVED))
    if "reconciliation_residual" in frame.columns:
        for data in frame[frame["reconciliation_residual"].notna() & frame["reconciliation_residual"].ne(0)].to_dict("records"):
            output.append(QualityException(str(data["observation_id"]), "source_reconciliation_failure", "medium",
                                           data["reconciliation_residual"], {}, ExceptionDisposition.UNRESOLVED))
    return sorted(output, key=lambda item: (item.observation_id, item.rule))


def strategy_is_eligible(declaration: StrategyDeclaration, row: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Fail closed if feature availability, basis, PIT, or applicability is absent."""
    if row.get("instrument_class") not in declaration.applicable_instrument_classes:
        return False, "instrument_class_not_applicable"
    if PriceBasis(str(row.get("price_basis", PriceBasis.UNKNOWN))) not in declaration.acceptable_price_bases:
        return False, "price_basis_not_accepted"
    if declaration.pit_required and row.get("pit_status") != FeatureStatus.QUALIFIED.value:
        return False, "pit_requirement_not_met"
    statuses = row.get("feature_statuses", {})
    for feature in declaration.required_features:
        if feature not in row or pd.isna(row[feature]):
            return False, f"missing_feature:{feature}"
        if FeatureStatus(str(statuses.get(feature, FeatureStatus.UNKNOWN))) not in declaration.acceptable_statuses:
            return False, f"feature_status_not_accepted:{feature}"
    return True, None
