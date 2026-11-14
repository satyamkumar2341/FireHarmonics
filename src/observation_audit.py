import json
from pathlib import Path

import pandas as pd


VALID_STATUSES = {
    "unmatched_under_criteria",
    "single_candidate",
    "multiple_candidates",
}

REQUIRED_COLUMNS = {
    "observation_id",
    "sensor",
    "platform",
    "candidate_count",
    "candidate_status",
}


def run_observation_audit(
    input_path="data/processed/dora_observation_status.csv",
    output_dir="data/processed",
):
    source = Path(input_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(f"Observation status file not found: {source}")

    df = pd.read_csv(source)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    if df.empty:
        raise ValueError("Observation status dataset is empty.")

    if df["observation_id"].isna().any():
        raise ValueError("Observation IDs cannot be missing.")

    if df["observation_id"].duplicated().any():
        raise ValueError("Duplicate observation IDs found.")

    df["candidate_count"] = pd.to_numeric(
        df["candidate_count"], errors="coerce"
    )

    if df["candidate_count"].isna().any():
        raise ValueError("Invalid candidate counts found.")

    if (df["candidate_count"] < 0).any():
        raise ValueError("Candidate counts cannot be negative.")

    expected_status = df["candidate_count"].map(
        lambda count: (
            "unmatched_under_criteria" if count == 0
            else "single_candidate" if count == 1
            else "multiple_candidates"
        )
    )

    if not expected_status.equals(df["candidate_status"]):
        raise ValueError("Candidate status does not match candidate count.")

    if df[["sensor", "platform"]].isna().any().any():
        raise ValueError("Sensor or platform values cannot be missing.")

    if "observation_uid" in df.columns:
        if df["observation_uid"].isna().any():
            raise ValueError("Observation UIDs cannot be missing.")
        if df["observation_uid"].duplicated().any():
            raise ValueError("Duplicate observation UIDs found.")

    unknown_statuses = set(df["candidate_status"]) - VALID_STATUSES
    if unknown_statuses:
        raise ValueError(f"Unknown candidate statuses: {unknown_statuses}")

    status_order = [
        "unmatched_under_criteria",
        "single_candidate",
        "multiple_candidates",
    ]

    total = len(df)
    rows = []

    grouped = df.groupby(["sensor", "platform"], dropna=False)

    for (sensor, platform), group in grouped:
        platform_total = len(group)

        for status in status_order:
            count = int((group["candidate_status"] == status).sum())

            rows.append({
                "sensor": sensor,
                "platform": platform,
                "candidate_status": status,
                "observation_count": count,
                "percentage_of_platform": round(
                    count / platform_total * 100, 4
                ),
                "percentage_of_all_observations": round(
                    count / total * 100, 4
                ),
            })

    audit = pd.DataFrame(rows)

    audit.to_csv(
        output / "dora_observation_ambiguity_audit.csv",
        index=False,
    )

    overall_counts = {
        status: int((df["candidate_status"] == status).sum())
        for status in status_order
    }

    summary = {
        "method": "DORA observation-level candidate status audit",
        "input_file": str(source),
        "total_observations": total,
        "unique_observation_ids": int(df["observation_id"].nunique()),
        "unique_observation_uids": (
            int(df["observation_uid"].nunique())
            if "observation_uid" in df.columns else None
        ),
        "overall_status_counts": overall_counts,
        "overall_status_percentages": {
            status: round(count / total * 100, 4)
            for status, count in overall_counts.items()
        },
        "platform_groups": int(
            df[["sensor", "platform"]].drop_duplicates().shape[0]
        ),
        "validation": {
            "duplicate_observation_ids": 0,
            "duplicate_observation_uids": (
                0 if "observation_uid" in df.columns else None
            ),
            "candidate_count_status_consistency": "PASS",
        },
        "interpretation": (
            "Unmatched observations have no candidate under the selected "
            "DORA criteria. This does not establish sensor failure or "
            "absence of a fire. Candidate relationships are exploratory, "
            "not confirmed fire-event matches."
        ),
    }

    (output / "dora_observation_ambiguity_audit.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print("Observation audit CSV and JSON reports saved.")

    return summary


if __name__ == "__main__":
    run_observation_audit()
