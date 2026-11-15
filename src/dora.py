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

    # Preserve original input rows for complete scope accounting.
    df["_input_row_number"] = np.arange(1, len(df) + 1)

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

    # Normalize classification fields without changing source columns.
    sensor = df["sensor"].astype("string").str.strip().str.upper()
    platform = df["platform"].astype("string").str.strip().str.upper()
    daynight = df["daynight"].astype("string").str.strip().str.upper()
    acq_date = df["acq_date"].astype("string").str.strip()

    exclusion_reason = pd.Series("", index=df.index, dtype="string")

    def mark_invalid(mask, reason):
        target = exclusion_reason.eq("")
        exclusion_reason.loc[mask & target] = reason

    observation_id = df["observation_id"].astype("string").str.strip()
    mark_invalid(
        observation_id.isna() | observation_id.eq(""),
        "missing_observation_id",
    )
    mark_invalid(df["latitude"].isna(), "invalid_latitude")
    mark_invalid(df["longitude"].isna(), "invalid_longitude")
    mark_invalid(acq_date.isna() | acq_date.eq(""), "invalid_acq_date")
    mark_invalid(
        df["observation_datetime_utc"].isna(),
        "invalid_observation_datetime_utc",
    )
    mark_invalid(daynight.isna() | ~daynight.isin(["D", "N"]), "invalid_daynight")
    mark_invalid(
        df["latitude"].notna() & ~df["latitude"].between(-90, 90),
        "latitude_out_of_range",
    )
    mark_invalid(
        df["longitude"].notna() & ~df["longitude"].between(-180, 180),
        "longitude_out_of_range",
    )
    mark_invalid(sensor.isna() | sensor.eq(""), "invalid_sensor")
    mark_invalid(platform.isna() | platform.eq(""), "invalid_platform")

    valid_mask = exclusion_reason.eq("")
    valid = df.loc[valid_mask].copy()
    valid["_sensor_normalized"] = sensor.loc[valid_mask]
    valid["_platform_normalized"] = platform.loc[valid_mask]
    valid["_daynight_normalized"] = daynight.loc[valid_mask]
    valid["_acq_date_normalized"] = acq_date.loc[valid_mask]

    # DORA scope: MODIS Aqua and VIIRS on dates represented by both.
    modis_aqua = valid[
        (valid["_sensor_normalized"] == "MODIS")
        & (valid["_platform_normalized"] == "AQUA")
    ].copy()

    viirs_all = valid[
        valid["_sensor_normalized"] == "VIIRS"
    ].copy()

    modis_dates = set(modis_aqua["_acq_date_normalized"])
    viirs_dates = set(viirs_all["_acq_date_normalized"])
    common_dates = sorted(modis_dates & viirs_dates)

    # Assign explicit exclusion reasons to otherwise valid observations.
    non_aqua_modis = (
        (valid["_sensor_normalized"] == "MODIS")
        & (valid["_platform_normalized"] != "AQUA")
    )
    exclusion_reason.loc[valid.index[non_aqua_modis]] = "modis_non_aqua_platform"

    unsupported = ~valid["_sensor_normalized"].isin(["MODIS", "VIIRS"])
    exclusion_reason.loc[valid.index[unsupported]] = "unsupported_sensor"

    aqua_without_viirs = (
        (valid["_sensor_normalized"] == "MODIS")
        & (valid["_platform_normalized"] == "AQUA")
        & ~valid["_acq_date_normalized"].isin(viirs_dates)
    )
    exclusion_reason.loc[valid.index[aqua_without_viirs]] = "no_same_date_viirs"

    viirs_without_aqua = (
        (valid["_sensor_normalized"] == "VIIRS")
        & ~valid["_acq_date_normalized"].isin(modis_dates)
    )
    exclusion_reason.loc[valid.index[viirs_without_aqua]] = "no_same_date_modis_aqua"

    eligible = valid[
        valid["_acq_date_normalized"].isin(common_dates)
        & (
            (
                (valid["_sensor_normalized"] == "MODIS")
                & (valid["_platform_normalized"] == "AQUA")
            )
            | (valid["_sensor_normalized"] == "VIIRS")
        )
    ].copy()

    modis = eligible[
        (eligible["_sensor_normalized"] == "MODIS")
        & (eligible["_platform_normalized"] == "AQUA")
    ].reset_index(drop=True)

    viirs = eligible[
        eligible["_sensor_normalized"] == "VIIRS"
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

                if str(m["_acq_date_normalized"]) != str(v["_acq_date_normalized"]):
                    continue

                if m["_daynight_normalized"] != v["_daynight_normalized"]:
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
                    "date": str(m["_acq_date_normalized"]),
                    "daynight": m["_daynight_normalized"],
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
            "date": obs["_acq_date_normalized"],
            "daynight": obs["_daynight_normalized"],
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
            "date": obs["_acq_date_normalized"],
            "daynight": obs["_daynight_normalized"],
            "candidate_count": count,
            "candidate_status": (
                "unmatched_under_criteria" if count == 0
                else "multiple_candidates" if count > 1
                else "single_candidate"
            ),
        })

    status = pd.DataFrame(status_rows)

    # Exclusion report includes invalid records and valid records outside DORA scope.
    excluded_mask = ~exclusion_reason.eq("")
    excluded = df.loc[excluded_mask].copy()
    excluded["exclusion_reason"] = exclusion_reason.loc[excluded_mask]

    exclusion_columns = [
        "_input_row_number", "observation_id",
        *(["observation_uid"] if has_uid else []),
        "sensor", "platform", "acq_date", "exclusion_reason",
    ]
    exclusions = excluded[exclusion_columns].rename(
        columns={"_input_row_number": "input_row_number"}
    )

    spatial.to_csv(output / "dora_spatial_candidates_5km.csv", index=False)
    baseline.to_csv(output / "dora_candidate_pairs.csv", index=False)
    status.to_csv(output / "dora_observation_status.csv", index=False)
    sensitivity.to_csv(
        output / "dora_threshold_sensitivity.csv", index=False
    )
    exclusions.to_csv(output / "dora_scope_exclusions.csv", index=False)

    reason_counts = (
        exclusions["exclusion_reason"].value_counts().sort_index().to_dict()
    )

    input_count = len(df)
    valid_count = int(valid_mask.sum())
    audited_count = len(eligible)
    excluded_count = len(exclusions)

    summary = {
        "method": "DORA exploratory candidate matching",
        "primary_modis_platform": "Aqua",
        "common_dates": common_dates,
        "input_observations": input_count,
        "valid_observations": valid_count,
        "audited_observations": audited_count,
        "excluded_observations": excluded_count,
        "scope_accounting_complete": (
            input_count == audited_count + excluded_count
        ),
        "exclusions_by_reason": reason_counts,
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
            "not a confirmed sensor miss. Excluded observations are outside "
            "the current MODIS Aqua/VIIRS common-date audit scope."
        ),
    }

    (output / "dora_run_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return summary


if __name__ == "__main__":
    print(json.dumps(run_dora(), indent=2))
    print("\nDORA output files saved in data/processed/")
