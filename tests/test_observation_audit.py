import json

import pandas as pd
import pytest

from src.observation_audit import run_observation_audit


def make_status_file(path):
    df = pd.DataFrame([
        {
            "observation_id": "M1",
            "observation_uid": "UID-M1",
            "sensor": "MODIS",
            "platform": "Aqua",
            "candidate_count": 0,
            "candidate_status": "unmatched_under_criteria",
        },
        {
            "observation_id": "M2",
            "observation_uid": "UID-M2",
            "sensor": "MODIS",
            "platform": "Aqua",
            "candidate_count": 1,
            "candidate_status": "single_candidate",
        },
        {
            "observation_id": "M3",
            "observation_uid": "UID-M3",
            "sensor": "MODIS",
            "platform": "Aqua",
            "candidate_count": 2,
            "candidate_status": "multiple_candidates",
        },
        {
            "observation_id": "V1",
            "observation_uid": "UID-V1",
            "sensor": "VIIRS",
            "platform": "NOAA-20",
            "candidate_count": 0,
            "candidate_status": "unmatched_under_criteria",
        },
    ])
    df.to_csv(path, index=False)


def test_audit_outputs_and_percentages(tmp_path):
    source = tmp_path / "status.csv"
    output = tmp_path / "output"
    make_status_file(source)

    summary = run_observation_audit(source, output)

    audit = pd.read_csv(
        output / "dora_observation_ambiguity_audit.csv"
    )
    saved = json.loads(
        (output / "dora_observation_ambiguity_audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["total_observations"] == 4
    assert saved["unique_observation_uids"] == 4
    assert summary["overall_status_counts"] == {
        "unmatched_under_criteria": 2,
        "single_candidate": 1,
        "multiple_candidates": 1,
    }
    assert len(audit) == 6
    assert audit["observation_count"].sum() == 4
    assert saved["validation"]["candidate_count_status_consistency"] == "PASS"


def test_duplicate_observation_ids_rejected(tmp_path):
    source = tmp_path / "status.csv"
    make_status_file(source)
    df = pd.read_csv(source)
    df.loc[1, "observation_id"] = df.loc[0, "observation_id"]
    df.to_csv(source, index=False)

    with pytest.raises(ValueError, match="Duplicate observation IDs"):
        run_observation_audit(source, tmp_path / "out")


def test_candidate_status_mismatch_rejected(tmp_path):
    source = tmp_path / "status.csv"
    make_status_file(source)
    df = pd.read_csv(source)
    df.loc[0, "candidate_status"] = "single_candidate"
    df.to_csv(source, index=False)

    with pytest.raises(ValueError, match="does not match candidate count"):
        run_observation_audit(source, tmp_path / "out")


def test_negative_candidate_count_rejected(tmp_path):
    source = tmp_path / "status.csv"
    make_status_file(source)
    df = pd.read_csv(source)
    df.loc[0, "candidate_count"] = -1
    df.to_csv(source, index=False)

    with pytest.raises(ValueError, match="cannot be negative"):
        run_observation_audit(source, tmp_path / "out")


def test_duplicate_uids_rejected(tmp_path):
    source = tmp_path / "status.csv"
    make_status_file(source)
    df = pd.read_csv(source)
    df.loc[1, "observation_uid"] = df.loc[0, "observation_uid"]
    df.to_csv(source, index=False)

    with pytest.raises(ValueError, match="Duplicate observation UIDs"):
        run_observation_audit(source, tmp_path / "out")
