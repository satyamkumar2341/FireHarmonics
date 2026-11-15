import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088
NANOSECONDS_PER_MINUTE = 60_000_000_000


def run_dora(
    input_path="data/processed/harmonized_observations.csv",
    output_dir="data/processed",
    baseline_radius_km=2.0,
    baseline_time_minutes=240.0,
    max_search_radius_km=5.0,
):
    if not (0 < baseline_radius_km <= max_search_radius_km):
        raise ValueError("Baseline radius must be positive and <= max search radius.")
    if baseline_time_minutes <= 0 or max_search_radius_km <= 0:
        raise ValueError("Time and search thresholds must be positive.")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_path, low_memory=False)

    required = {
        "observation_id", "latitude", "longitude", "acq_date",
        "observation_datetime_utc", "sensor", "platform", "daynight",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    has_uid = "observation_uid" in df.columns
    df["_input_row_number"] = np.arange(1, len(df) + 1)

    if has_uid:
        df["observation_uid"] = df["observation_uid"].astype("string").str.strip()
        if df["observation_uid"].isna().any() or df["observation_uid"].eq("").any():
            raise ValueError("observation_uid contains missing or empty values")

    df["observation_datetime_utc"] = pd.to_datetime(
        df["observation_datetime_utc"], utc=True, errors="coerce"
    )
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    sensor = df["sensor"].astype("string").str.strip().str.upper()
    platform = df["platform"].astype("string").str.strip().str.upper()
    daynight = df["daynight"].astype("string").str.strip().str.upper()
    acq_date = df["acq_date"].astype("string").str.strip()

    exclusion_reason = pd.Series("", index=df.index, dtype="string")

    def mark_invalid(mask, reason):
        target = exclusion_reason.eq("")
        exclusion_reason.loc[mask & target] = reason

    observation_id = df["observation_id"].astype("string").str.strip()
    mark_invalid(observation_id.isna() | observation_id.eq(""), "missing_observation_id")
    mark_invalid(df["latitude"].isna(), "invalid_latitude")
    mark_invalid(df["longitude"].isna(), "invalid_longitude")
    mark_invalid(acq_date.isna() | acq_date.eq(""), "invalid_acq_date")
    mark_invalid(df["observation_datetime_utc"].isna(), "invalid_observation_datetime_utc")
    mark_invalid(daynight.isna() | ~daynight.isin(["D", "N"]), "invalid_daynight")
    mark_invalid(df["latitude"].notna() & ~df["latitude"].between(-90, 90), "latitude_out_of_range")
    mark_invalid(df["longitude"].notna() & ~df["longitude"].between(-180, 180), "longitude_out_of_range")
    mark_invalid(sensor.isna() | sensor.eq(""), "invalid_sensor")
    mark_invalid(platform.isna() | platform.eq(""), "invalid_platform")

    valid_mask = exclusion_reason.eq("")
    valid = df.loc[valid_mask].copy()
    valid["_sensor_normalized"] = sensor.loc[valid_mask]
    valid["_platform_normalized"] = platform.loc[valid_mask]
    valid["_daynight_normalized"] = daynight.loc[valid_mask]
    valid["_acq_date_normalized"] = acq_date.loc[valid_mask]

    modis_aqua = valid[
        (valid["_sensor_normalized"] == "MODIS")
        & (valid["_platform_normalized"] == "AQUA")
    ]
    viirs_all = valid[valid["_sensor_normalized"] == "VIIRS"]

    modis_dates = set(modis_aqua["_acq_date_normalized"])
    viirs_dates = set(viirs_all["_acq_date_normalized"])
    common_dates = sorted(modis_dates & viirs_dates)

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
        "date", "daynight", "modis_platform", "viirs_platform",
        "distance_km", "time_gap_minutes",
        "modis_confidence_native", "modis_confidence_scheme", "modis_frp_mw",
        "viirs_confidence_native", "viirs_confidence_scheme", "viirs_frp_mw",
    ]

    pair_frames = []

    # Critical optimization: construct separate spatial indexes for each
    # acquisition date and day/night class. No cross-date candidate search.
    viirs_groups = {
        key: group.reset_index(drop=True)
        for key, group in viirs.groupby(
            ["_acq_date_normalized", "_daynight_normalized"], sort=False
        )
    }

    modis_grouped = modis.groupby(
        ["_acq_date_normalized", "_daynight_normalized"], sort=False
    )
    total_groups = len(modis_grouped)
    print(
        f"DORA spatial indexing: {total_groups} MODIS date/day-night groups",
        flush=True,
    )

    def optional_values(frame, column, positions):
        if column in frame.columns:
            return frame[column].to_numpy()[positions]
        return np.full(len(positions), None, dtype=object)

    for group_number, (key, mg_raw) in enumerate(modis_grouped, 1):
        vg = viirs_groups.get(key)
        if vg is None or vg.empty:
            continue

        mg = mg_raw.reset_index(drop=True)

        tree = BallTree(
            np.radians(vg[["latitude", "longitude"]].to_numpy(dtype=float)),
            metric="haversine",
        )
        neighbours, distances = tree.query_radius(
            np.radians(mg[["latitude", "longitude"]].to_numpy(dtype=float)),
            r=max_search_radius_km / EARTH_RADIUS_KM,
            return_distance=True,
        )

        counts = np.fromiter((len(x) for x in neighbours), dtype=np.int64)
        total = int(counts.sum())

        if total:
            mi = np.repeat(np.arange(len(mg)), counts)
            vi = np.concatenate(neighbours).astype(np.int64, copy=False)
            distance_km = np.concatenate(distances) * EARTH_RADIUS_KM

            m_time = mg["observation_datetime_utc"].astype("int64").to_numpy()
            v_time = vg["observation_datetime_utc"].astype("int64").to_numpy()
            gap_minutes = (
                np.abs(m_time[mi] - v_time[vi]) / NANOSECONDS_PER_MINUTE
            )

            data = {
                "modis_id": mg["observation_id"].to_numpy()[mi],
                "viirs_id": vg["observation_id"].to_numpy()[vi],
                "date": np.repeat(str(key[0]), total),
                "daynight": np.repeat(str(key[1]), total),
                "modis_platform": mg["platform"].to_numpy()[mi],
                "viirs_platform": vg["platform"].to_numpy()[vi],
                "distance_km": distance_km,
                "time_gap_minutes": gap_minutes,
                "modis_confidence_native": optional_values(mg, "confidence_native", mi),
                "modis_confidence_scheme": optional_values(mg, "confidence_scheme", mi),
                "modis_frp_mw": optional_values(mg, "frp_mw", mi),
                "viirs_confidence_native": optional_values(vg, "confidence_native", vi),
                "viirs_confidence_scheme": optional_values(vg, "confidence_scheme", vi),
                "viirs_frp_mw": optional_values(vg, "frp_mw", vi),
            }

            if has_uid:
                data["modis_uid"] = mg["observation_uid"].to_numpy()[mi]
                data["viirs_uid"] = vg["observation_uid"].to_numpy()[vi]

            pair_frames.append(pd.DataFrame(data, columns=pair_columns))

        if group_number % 100 == 0 or group_number == total_groups:
            print(
                f"  Processed {group_number}/{total_groups} groups; "
                f"spatial candidates so far: {sum(len(x) for x in pair_frames):,}",
                flush=True,
            )

    if pair_frames:
        spatial = pd.concat(pair_frames, ignore_index=True)
        spatial = spatial.sort_values(
            ["date", "distance_km", "time_gap_minutes"]
        ).reset_index(drop=True)
    else:
        spatial = pd.DataFrame(columns=pair_columns)

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

    def make_status(frame, side, counts):
        ids = frame["observation_id"]
        candidate_count = ids.map(counts).fillna(0).astype(int)
        status_values = np.where(
            candidate_count.eq(0), "unmatched_under_criteria",
            np.where(candidate_count.gt(1), "multiple_candidates", "single_candidate")
        )
        data = {
            "observation_id": ids.to_numpy(),
            "sensor": side.upper(),
            "platform": frame["platform"].to_numpy(),
            "date": frame["_acq_date_normalized"].to_numpy(),
            "daynight": frame["_daynight_normalized"].to_numpy(),
            "candidate_count": candidate_count.to_numpy(),
            "candidate_status": status_values,
        }
        if has_uid:
            data["observation_uid"] = frame["observation_uid"].to_numpy()
        return pd.DataFrame(data)

    status = pd.concat([
        make_status(modis, "MODIS", modis_counts),
        make_status(viirs, "VIIRS", viirs_counts),
    ], ignore_index=True)

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
    sensitivity.to_csv(output / "dora_threshold_sensitivity.csv", index=False)
    exclusions.to_csv(output / "dora_scope_exclusions.csv", index=False)

    reason_counts = (
        exclusions["exclusion_reason"].value_counts().sort_index().to_dict()
    )
    input_count = len(df)
    valid_count = int(valid_mask.sum())
    audited_count = len(eligible)
    excluded_count = len(exclusions)

    summary = {
        "method": "DORA exploratory candidate matching; date/day-night indexed BallTree",
        "primary_modis_platform": "Aqua",
        "common_dates": common_dates,
        "input_observations": input_count,
        "valid_observations": valid_count,
        "audited_observations": audited_count,
        "excluded_observations": excluded_count,
        "scope_accounting_complete": input_count == audited_count + excluded_count,
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
            "Unmatched means no candidate under these criteria, not a confirmed "
            "sensor miss. Excluded observations are outside the current MODIS "
            "Aqua/VIIRS common-date audit scope."
        ),
    }

    (output / "dora_run_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
