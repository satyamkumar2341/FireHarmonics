import json
from pathlib import Path

import pandas as pd


def run_ambiguity_analysis(
    input_path="data/processed/dora_candidate_pairs.csv",
    output_dir="data/processed",
):
    source = Path(input_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    pairs = pd.read_csv(source)

    required = {
        "modis_id", "viirs_id",
        "distance_km", "time_gap_minutes",
    }
    missing = required - set(pairs.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    if pairs.empty:
        raise ValueError("Candidate-pair dataset is empty.")

    pairs["distance_km"] = pd.to_numeric(
        pairs["distance_km"], errors="coerce"
    )
    pairs["time_gap_minutes"] = pd.to_numeric(
        pairs["time_gap_minutes"], errors="coerce"
    )

    if pairs[["distance_km", "time_gap_minutes"]].isna().any().any():
        raise ValueError("Invalid distance or time-gap values.")

    if (pairs["distance_km"] < 0).any() or (
        pairs["time_gap_minutes"] < 0
    ).any():
        raise ValueError("Distance and time gap cannot be negative.")

    if pairs.duplicated(["modis_id", "viirs_id"]).any():
        raise ValueError("Duplicate MODIS-VIIRS candidate pairs found.")

    pairs["modis_candidate_count"] = (
        pairs.groupby("modis_id")["viirs_id"].transform("nunique")
    )
    pairs["viirs_candidate_count"] = (
        pairs.groupby("viirs_id")["modis_id"].transform("nunique")
    )

    pairs["ambiguity_type"] = "unique_on_both_sides"

    pairs.loc[
        (pairs["modis_candidate_count"] > 1)
        & (pairs["viirs_candidate_count"] == 1),
        "ambiguity_type",
    ] = "ambiguous_for_modis"

    pairs.loc[
        (pairs["modis_candidate_count"] == 1)
        & (pairs["viirs_candidate_count"] > 1),
        "ambiguity_type",
    ] = "ambiguous_for_viirs"

    pairs.loc[
        (pairs["modis_candidate_count"] > 1)
        & (pairs["viirs_candidate_count"] > 1),
        "ambiguity_type",
    ] = "ambiguous_on_both_sides"

    # Lower rank means a higher investigation priority.
    # Distance is primary; time gap breaks distance ties.
    pairs = pairs.sort_values(
        ["distance_km", "time_gap_minutes", "modis_id", "viirs_id"]
    ).copy()

    pairs["rank_for_modis"] = (
        pairs.groupby("modis_id").cumcount() + 1
    )

    pairs["rank_for_viirs"] = (
        pairs.groupby("viirs_id").cumcount() + 1
    )

    pairs = pairs.sort_values(
        ["modis_id", "rank_for_modis"]
    ).reset_index(drop=True)

    pairs.to_csv(
        output / "dora_ranked_candidates.csv", index=False
    )

    modis_counts = pairs.groupby("modis_id")["viirs_id"].nunique()
    viirs_counts = pairs.groupby("viirs_id")["modis_id"].nunique()

    ambiguity_counts = (
        pairs["ambiguity_type"].value_counts().to_dict()
    )

    summary = {
        "method": "DORA candidate ambiguity analysis",
        "candidate_pairs": int(len(pairs)),
        "unique_modis_observations": int(pairs["modis_id"].nunique()),
        "unique_viirs_observations": int(pairs["viirs_id"].nunique()),
        "modis_multiple_candidate_observations": int(
            (modis_counts > 1).sum()
        ),
        "viirs_multiple_candidate_observations": int(
            (viirs_counts > 1).sum()
        ),
        "ambiguity_pair_distribution": {
            key: int(value)
            for key, value in ambiguity_counts.items()
        },
        "ranking_rule": (
            "Ascending distance, then ascending absolute time gap. "
            "Ranks are investigation priorities, not match probabilities."
        ),
        "warning": (
            "Candidate rankings do not establish confirmed fire-event "
            "matches or sensor detection accuracy."
        ),
    }

    (output / "dora_ambiguity_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print("Ranked candidates saved to dora_ranked_candidates.csv")

    return summary


if __name__ == "__main__":
    run_ambiguity_analysis()
