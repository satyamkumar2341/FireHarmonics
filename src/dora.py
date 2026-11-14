import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088


def run_dora(
    input_path="data/processed/harmonized_observations.csv",
    output_dir="data/processed",
    baseline_radius_km=2.0,
    baseline_time_minutes=240.0,
    max_search_radius_km=5.0,
):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)

    required = {
        "observation_id", "latitude", "longitude", "acq_date",
        "observation_datetime_utc", "sensor", "platform", "daynight",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    has_uid = "observation_uid" in df.columns

    if has_uid:
        df["observation_uid"] = (
            df["observation_uid"].astype("string").str.strip()
        )
        if df["observation_uid"].isna().any() or df["observation_uid"].eq("").any():
            raise ValueError("observation_uid contains missing or empty values")

    df["observation_datetime_utc"] = pd.to_datetime(
        df["observation_datetime_utc"], utc=True, errors="coerce"
    )
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["daynight"] = df["daynight"].astype(str).str.upper().str.strip()

    df = df.dropna(subset=[
        "observation_id", "latitude", "longitude", "acq_date",
        "observation_datetime_utc", "daynight",
    ])
    df = df[
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    ].copy()

    modis = df[
        (df["sensor"].str.upper() == "MODIS")
        & (df["platform"].str.upper() == "AQUA")
    ].copy()

    viirs = df[df["sensor"].str.upper() == "VIIRS"].copy()

    common_dates = sorted(
        set(modis["acq_date"].astype(str))
        & set(viirs["acq_date"].astype(str))
    )

    modis = modis[
        modis["acq_date"].astype(str).isin(common_dates)
    ].reset_index(drop=True)

    viirs = viirs[
        viirs["acq_date"].astype(str).isin(common_dates)
    ].reset_index(drop=True)

    pair_columns = [
        "modis_id", "viirs_id",
        *(["modis_uid", "viirs_uid"] if has_uid else []),
        "date", "daynight",
        "modis_platform", "viirs_platform",
        "distance_km", "time_gap_minutes",
        "modis_confidence_native", "modis_confidence_scheme",
        "modis_frp_mw",
        "viirs_confidence_native", "viirs_confidence_scheme",
        "viirs_frp_mw",
    ]

    records = []

    if not modis.empty and not viirs.empty:
        tree = BallTree(
            np.radians(
                viirs[["latitude", "longitude"]].to_numpy(dtype=float)
            ),
            metric="haversine",
        )

        indices, distances = tree.query_radius(
            np.radians(
                modis[["latitude", "longitude"]].to_numpy(dtype=float)
            ),
            r=max_search_radius_km / EARTH_RADIUS_KM,
            return_distance=True,
        )

        for i, (js, ds) in enumerate(zip(indices, distances)):
            m = modis.iloc[i]

            for j, distance in zip(js, ds):
                v = viirs.iloc[int(j)]

                if str(m["acq_date"]) != str(v["acq_date"]):
                    continue

                if m["daynight"] != v["daynight"]:
                    continue

                gap = abs(
                    (
                        m["observation_datetime_utc"]
                        - v["observation_datetime_utc"]
                    ).total_seconds()
                ) / 60

                row = {
                    "modis_id": m["observation_id"],
                    "viirs_id": v["observation_id"],
                    **(
                        {
                            "modis_uid": m["observation_uid"],
                            "viirs_uid": v["observation_uid"],
                        }
                        if has_uid else {}
                    ),
                    "date": str(m["acq_date"]),
                    "daynight": m["daynight"],
                    "modis_platform": m["platform"],
                    "viirs_platform": v["platform"],
                    "distance_km": float(distance * EARTH_RADIUS_KM),
                    "time_gap_minutes": float(gap),
                }

                for side, obs in [("modis", m), ("viirs", v)]:
                    for source, target in [
                        ("confidence_native", f"{side}_confidence_native"),
                        ("confidence_scheme", f"{side}_confidence_scheme"),
                        ("frp_mw", f"{side}_frp_mw"),
                    ]:
                        row[target] = obs.get(source, None)

                records.append(row)

    spatial = pd.DataFrame(records, columns=pair_columns)

    if not spatial.empty:
        spatial = spatial.sort_values(
            ["date", "distance_km", "time_gap_minutes"]
        ).reset_index(drop=True)

    sensitivity_rows = []

    for radius in [1, 2, 5]:
        for minutes in [60, 120, 240]:
            selected = spatial[
                (spatial["distance_km"] <= radius)
                & (spatial["time_gap_minutes"] <= minutes)
            ]

            sensitivity_rows.append({
                "radius_km": radius,
                "time_window_minutes": minutes,
                "candidate_pairs": len(selected),
                "unique_modis_observations": selected["modis_id"].nunique(),
                "unique_viirs_observations": selected["viirs_id"].nunique(),
            })

    sensitivity = pd.DataFrame(sensitivity_rows)

    baseline = spatial[
        (spatial["distance_km"] <= baseline_radius_km)
        & (spatial["time_gap_minutes"] <= baseline_time_minutes)
    ].copy().reset_index(drop=True)

    modis_counts = baseline.groupby("modis_id")["viirs_id"].nunique().to_dict()
    viirs_counts = baseline.groupby("viirs_id")["modis_id"].nunique().to_dict()

    status_rows = []

    for _, obs in modis.iterrows():
        count = int(modis_counts.get(obs["observation_id"], 0))
        status_rows.append({
            "observation_id": obs["observation_id"],
            **(
                {"observation_uid": obs["observation_uid"]}
                if has_uid else {}
            ),
            "sensor": "MODIS",
            "platform": obs["platform"],
            "date": obs["acq_date"],
            "daynight": obs["daynight"],
            "candidate_count": count,
            "candidate_status": (
                "unmatched_under_criteria" if count == 0
                else "multiple_candidates" if count > 1
                else "single_candidate"
            ),
        })

    for _, obs in viirs.iterrows():
        count = int(viirs_counts.get(obs["observation_id"], 0))
        status_rows.append({
            "observation_id": obs["observation_id"],
            **(
                {"observation_uid": obs["observation_uid"]}
                if has_uid else {}
            ),
            "sensor": "VIIRS",
            "platform": obs["platform"],
            "date": obs["acq_date"],
            "daynight": obs["daynight"],
            "candidate_count": count,
            "candidate_status": (
                "unmatched_under_criteria" if count == 0
                else "multiple_candidates" if count > 1
                else "single_candidate"
            ),
        })

    status = pd.DataFrame(status_rows)

    spatial.to_csv(output / "dora_spatial_candidates_5km.csv", index=False)
    baseline.to_csv(output / "dora_candidate_pairs.csv", index=False)
    status.to_csv(output / "dora_observation_status.csv", index=False)
    sensitivity.to_csv(
        output / "dora_threshold_sensitivity.csv", index=False
    )

    summary = {
        "method": "DORA exploratory candidate matching",
        "primary_modis_platform": "Aqua",
        "common_dates": common_dates,
        "modis_aqua_observations": len(modis),
        "viirs_observations": len(viirs),
        "spatial_candidates_within_5km": len(spatial),
        "baseline_radius_km": baseline_radius_km,
        "baseline_time_window_minutes": baseline_time_minutes,
        "baseline_candidate_pairs": len(baseline),
        "baseline_unique_modis": baseline["modis_id"].nunique(),
        "baseline_unique_viirs": baseline["viirs_id"].nunique(),
        "warning": (
            "Candidate relationships are not confirmed fire-event matches. "
            "Unmatched means no candidate under these criteria, "
            "not a confirmed sensor miss."
        ),
    }

    (output / "dora_run_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return summary


if __name__ == "__main__":
    print(json.dumps(run_dora(), indent=2))
    print("\nDORA output files saved in data/processed/")
