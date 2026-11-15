"""Exploratory cross-sensor FRP comparability analysis.

Candidate associations are not independently verified fire-event matches.
No calibration correction or sensor accuracy estimate is produced.
"""

from pathlib import Path

import numpy as np
import pandas as pd


THRESHOLDS = [(1, 60), (1, 120), (2, 60), (2, 120), (2, 240)]

CANDIDATE_COLUMNS = [
    "modis_uid", "viirs_uid", "date", "viirs_platform",
    "distance_km", "time_gap_minutes",
    "modis_frp_mw", "viirs_frp_mw",
]


def _greedy_one_to_one(group):
    """Select non-overlapping pairs, prioritizing distance then time."""
    group = group.sort_values(
        ["distance_km", "time_gap_minutes", "modis_uid", "viirs_uid"]
    )

    used_modis, used_viirs, selected = set(), set(), []

    for row in group.itertuples(index=False):
        if row.modis_uid in used_modis or row.viirs_uid in used_viirs:
            continue
        used_modis.add(row.modis_uid)
        used_viirs.add(row.viirs_uid)
        selected.append(row._asdict())

    return pd.DataFrame(selected)


def _cluster_interval(daily_values, rng, replicates):
    values = np.asarray(daily_values, dtype=float)

    if len(values) == 0:
        return np.nan, np.nan

    boot = np.empty(replicates)

    for i in range(replicates):
        sample = rng.choice(values, size=len(values), replace=True)
        boot[i] = np.median(sample)

    return (
        float(np.percentile(boot, 2.5)),
        float(np.percentile(boot, 97.5)),
    )


def analyze_sensor_comparability(
    observations,
    spatial_candidates,
    output_dir=None,
    bootstrap_replicates=3000,
    random_seed=20261115,
):
    """Generate reproducible sensor summaries and FRP sensitivity outputs.

    Parameters
    ----------
    observations : pandas.DataFrame
        Harmonized observation-level dataset.
    spatial_candidates : pandas.DataFrame
        DORA spatial candidate pairs, normally the 5 km candidate output.
    output_dir : path-like, optional
        If supplied, write all result tables as CSV files.
    bootstrap_replicates : int
        Number of date-cluster bootstrap replicates.
    random_seed : int
        Seed for reproducibility.

    Returns
    -------
    dict[str, pandas.DataFrame]
        raw_platform_summary, native_confidence_counts,
        one_to_one_baseline, date_cluster_bootstrap,
        threshold_bootstrap.
    """
    if (
        isinstance(bootstrap_replicates, bool)
        or not isinstance(bootstrap_replicates, (int, np.integer))
        or bootstrap_replicates < 100
    ):
        raise ValueError("bootstrap_replicates must be an integer >= 100.")

    missing = sorted(set(CANDIDATE_COLUMNS) - set(spatial_candidates.columns))
    if missing:
        raise ValueError(f"Missing candidate columns: {missing}")

    obs_required = {
        "sensor", "platform", "frp_mw",
        "brightness_native_kelvin", "confidence_scheme",
        "confidence_native", "observation_uid",
    }
    missing_obs = sorted(obs_required - set(observations.columns))
    if missing_obs:
        raise ValueError(f"Missing observation columns: {missing_obs}")

    raw = observations.copy()

    uid = raw["observation_uid"].astype("string").str.strip()
    if uid.isna().any() or uid.eq("").any():
        raise ValueError("observation_uid contains missing or blank values.")
    if uid.duplicated().any():
        raise ValueError("observation_uid values must be unique.")

    for col in ["frp_mw", "brightness_native_kelvin"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")

    raw_summary = (
        raw.groupby(["sensor", "platform"], dropna=False)
        .agg(
            observations=("observation_uid", "size"),
            frp_median_mw=("frp_mw", "median"),
            frp_mean_mw=("frp_mw", "mean"),
            frp_p90_mw=("frp_mw", lambda x: x.quantile(0.90)),
            brightness_median_native_k=("brightness_native_kelvin", "median"),
            brightness_mean_native_k=("brightness_native_kelvin", "mean"),
        )
        .reset_index()
    )

    confidence = (
        raw.groupby(
            ["sensor", "platform", "confidence_scheme", "confidence_native"],
            dropna=False,
        )
        .size()
        .reset_index(name="observations")
    )

    pairs = spatial_candidates.copy()

    for col in ["modis_uid", "viirs_uid", "viirs_platform"]:
        values = pairs[col].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"{col} contains missing or blank values.")

    for col in [
        "distance_km", "time_gap_minutes",
        "modis_frp_mw", "viirs_frp_mw",
    ]:
        pairs[col] = pd.to_numeric(pairs[col], errors="coerce")

    pairs["date"] = pd.to_datetime(
        pairs["date"], errors="coerce"
    ).dt.date

    pairs = pairs[
        pairs["date"].notna()
        & pairs["distance_km"].notna()
        & pairs["time_gap_minutes"].notna()
        & (pairs["modis_frp_mw"] > 0)
        & (pairs["viirs_frp_mw"] > 0)
    ].copy()

    pairs["frp_ratio"] = (
        pairs["viirs_frp_mw"] / pairs["modis_frp_mw"]
    )

    rng = np.random.default_rng(random_seed)
    baseline_rows, date_rows, threshold_rows = [], [], []

    for platform, platform_data in pairs.groupby("viirs_platform"):
        baseline = None

        for radius, minutes in THRESHOLDS:
            eligible = platform_data[
                (platform_data["distance_km"] <= radius)
                & (platform_data["time_gap_minutes"] <= minutes)
            ]

            one = _greedy_one_to_one(eligible)

            if one.empty:
                continue

            one["frp_ratio"] = (
                one["viirs_frp_mw"] / one["modis_frp_mw"]
            )

            daily = one.groupby("date")["frp_ratio"].median()
            values = daily.to_numpy()

            low, high = _cluster_interval(
                values, rng, bootstrap_replicates
            )

            threshold_rows.append({
                "platform": platform,
                "radius_km": radius,
                "time_minutes": minutes,
                "one_to_one_pairs": len(one),
                "unique_dates": len(values),
                "median_pair_ratio": one["frp_ratio"].median(),
                "median_daily_ratio": np.median(values),
                "ci95_low": low,
                "ci95_high": high,
                "dates_below_1_pct": (values < 1).mean() * 100,
            })

            if (radius, minutes) == (2, 240):
                baseline = one.copy()
                baseline_rows.append({
                    "platform": platform,
                    "candidate_pairs": len(eligible),
                    "one_to_one_pairs": len(one),
                    "unique_modis": one["modis_uid"].nunique(),
                    "unique_viirs": one["viirs_uid"].nunique(),
                    "median_frp_ratio": one["frp_ratio"].median(),
                    "median_frp_difference_pct": (
                        (one["frp_ratio"] - 1) * 100
                    ).median(),
                    "median_distance_km": one["distance_km"].median(),
                    "median_time_gap_min": one["time_gap_minutes"].median(),
                })

                date_rows.append({
                    "platform": platform,
                    "one_to_one_pairs": len(one),
                    "unique_dates": len(values),
                    "median_pair_ratio": one["frp_ratio"].median(),
                    "median_daily_ratio": np.median(values),
                    "cluster_bootstrap_95_low": low,
                    "cluster_bootstrap_95_high": high,
                    "dates_ratio_below_1_pct": (
                        (values < 1).mean() * 100
                    ),
                })

    outputs = {
        "raw_platform_summary": raw_summary,
        "native_confidence_counts": confidence,
        "one_to_one_baseline": pd.DataFrame(baseline_rows),
        "date_cluster_bootstrap": pd.DataFrame(date_rows),
        "threshold_bootstrap": pd.DataFrame(threshold_rows),
    }

    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)

        for name, frame in outputs.items():
            frame.to_csv(destination / f"sensor_{name}.csv", index=False)

    return outputs
