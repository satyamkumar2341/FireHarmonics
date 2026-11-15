"""Explainable, sensor-stratified anomaly detection for FireHarmonics.

Important interpretation:
- Counts are satellite observations, not deduplicated fire events or ground truth.
- Missing dates are NOT filled with zero: no detection is not evidence of no fire.
- Baselines are calculated separately by platform and spatial grid.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import numpy as np

REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "platform", "observation_uid"}


def build_anomaly_tables(
    observations: pd.DataFrame,
    *,
    grid_km: float = 5.0,
    baseline_days: int = 28,
    min_prior_active_days: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (daily_grid_activity, anomaly_alerts).

    Each daily row is a count of observations for one platform and spatial grid.
    Only dates with observed records are represented; missing dates are never
    interpreted as zero-activity days.
    """
    missing = REQUIRED_COLUMNS - set(observations.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if grid_km <= 0 or baseline_days < 1 or min_prior_active_days < 1:
        raise ValueError("grid_km, baseline_days and min_prior_active_days must be positive")

    df = observations[list(REQUIRED_COLUMNS)].copy()
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["date"] = pd.to_datetime(df["acq_date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["latitude", "longitude", "date", "platform"])
    df = df[(df["latitude"].between(-90, 90)) & (df["longitude"].between(-180, 180))]
    if df.empty:
        columns = ["date", "platform", "grid_id", "observation_count",
                   "baseline_median", "baseline_mad", "prior_active_days",
                   "robust_score", "severity", "interpretation"]
        empty = pd.DataFrame(columns=columns)
        return empty, empty.copy()

    # Fixed Punjab-Haryana regional origin keeps grid IDs stable when
    # additional date batches are downloaded and processed later.
    ref_lat = 30.0
    origin_lon, origin_lat = 73.5, 27.5
    km_per_lon_degree = 111.32 * np.cos(np.deg2rad(ref_lat))
    df["grid_x"] = np.floor((df["longitude"] - origin_lon) *
                            km_per_lon_degree / grid_km).astype("int64")
    df["grid_y"] = np.floor((df["latitude"] - origin_lat) *
                            111.32 / grid_km).astype("int64")
    df["grid_id"] = "G" + df["grid_x"].astype(str) + "_" + df["grid_y"].astype(str)

    daily = (df.groupby(["date", "platform", "grid_id"], as_index=False)
               .agg(observation_count=("observation_uid", "nunique"),
                    latitude_center=("latitude", "mean"),
                    longitude_center=("longitude", "mean")))
    daily = daily.sort_values(["platform", "grid_id", "date"]).reset_index(drop=True)

    result = []
    for (_, _), group in daily.groupby(["platform", "grid_id"], sort=False):
        group = group.copy().sort_values("date")
        counts = group["observation_count"].astype(float).to_numpy()
        dates = group["date"].to_numpy()
        medians, mads, n_prior, scores, severities, notes = [], [], [], [], [], []
        for i, current_date in enumerate(dates):
            start = pd.Timestamp(current_date) - pd.Timedelta(days=baseline_days)
            prior_mask = (group["date"].to_numpy() < current_date) & (group["date"].to_numpy() >= start.to_datetime64())
            prior = counts[prior_mask]
            n = int(len(prior))
            if n:
                median = float(np.median(prior))
                mad = float(np.median(np.abs(prior - median)))
            else:
                median, mad = np.nan, np.nan

            if n < min_prior_active_days:
                score, severity = np.nan, "insufficient_history"
                note = f"Only {n} prior active-observation days in the {baseline_days}-day window; no alert scored."
            else:
                # Robust scale with a count-dependent floor to avoid division by
                # zero for sparse or constant series.
                scale = max(1.4826 * mad, np.sqrt(median + 1.0), 1.0)
                score = float((counts[i] - median) / scale)
                if score >= 5:
                    severity = "high"
                elif score >= 3:
                    severity = "medium"
                elif score >= 2:
                    severity = "low"
                else:
                    severity = "normal"
                note = (f"{int(counts[i])} observations vs prior active-day median "
                        f"{median:.1f}; robust score {score:.2f}. Observation volume "
                        "is not a count of unique fires.")
            medians.append(median)
            mads.append(mad)
            n_prior.append(n)
            scores.append(score)
            severities.append(severity)
            notes.append(note)
        group["baseline_median"] = medians
        group["baseline_mad"] = mads
        group["prior_active_days"] = n_prior
        group["robust_score"] = scores
        group["severity"] = severities
        group["interpretation"] = notes
        result.append(group)

    activity = pd.concat(result, ignore_index=True) if result else daily
    alerts = activity[activity["severity"].isin(["low", "medium", "high"])].copy()
    activity["date"] = pd.to_datetime(activity["date"]).dt.strftime("%Y-%m-%d")
    alerts["date"] = pd.to_datetime(alerts["date"]).dt.strftime("%Y-%m-%d")
    return activity, alerts


def run_anomaly_detection(
    input_csv: str | Path,
    output_dir: str | Path,
    *,
    grid_km: float = 5.0,
    baseline_days: int = 28,
    min_prior_active_days: int = 7,
) -> dict:
    input_csv = Path(input_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    observations = pd.read_csv(input_csv)
    activity, alerts = build_anomaly_tables(
        observations, grid_km=grid_km, baseline_days=baseline_days,
        min_prior_active_days=min_prior_active_days
    )
    activity_path = output_dir / "daily_grid_activity.csv"
    alerts_path = output_dir / "anomaly_alerts.csv"
    activity.to_csv(activity_path, index=False)
    alerts.to_csv(alerts_path, index=False)
    summary = {
        "input_csv": str(input_csv),
        "input_observations": int(len(observations)),
        "daily_grid_platform_rows": int(len(activity)),
        "alert_rows": int(len(alerts)),
        "severity_counts": {str(k): int(v) for k, v in
                            activity["severity"].value_counts().to_dict().items()},
        "date_min": str(observations["acq_date"].min()) if len(observations) else None,
        "date_max": str(observations["acq_date"].max()) if len(observations) else None,
        "grid_km": grid_km,
        "baseline_days": baseline_days,
        "min_prior_active_days": min_prior_active_days,
        "method": "platform-stratified, grid-level, trailing active-observation-day median/MAD",
        "limitations": [
            "Observation counts are not deduplicated fire-event counts.",
            "Missing dates are not treated as zero activity.",
            "Alerts indicate unusual observation volume, not confirmed fire outbreaks.",
            "A three-month archive is insufficient for annual or seasonal baselines.",
            "Sparse grids may remain insufficient_history and produce no alert."
        ],
    }
    summary_path = output_dir / "anomaly_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"activity": activity_path, "alerts": alerts_path, "summary": summary_path,
            "rows": len(activity), "alerts_count": len(alerts)}


