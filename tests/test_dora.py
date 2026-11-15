import json

import pandas as pd
import pytest

from src.dora import run_dora


def make_observations():
    rows = [
        {
            "observation_id": "M1",
            "latitude": 30.0,
            "longitude": 75.0,
            "acq_date": "2026-11-10",
            "observation_datetime_utc": "2026-11-10T10:00:00Z",
            "sensor": "MODIS",
            "platform": "Aqua",
            "daynight": "D",
        },
        {
            "observation_id": "M2",
            "latitude": 31.0,
            "longitude": 76.0,
            "acq_date": "2026-11-10",
            "observation_datetime_utc": "2026-11-10T10:00:00Z",
            "sensor": "MODIS",
            "platform": "Aqua",
            "daynight": "D",
        },
        {
            "observation_id": "V1",
            "latitude": 30.0045,
            "longitude": 75.0,
            "acq_date": "2026-11-10",
            "observation_datetime_utc": "2026-11-10T11:00:00Z",
            "sensor": "VIIRS",
            "platform": "NOAA-20",
            "daynight": "D",
        },
        {
            "observation_id": "V2",
            "latitude": 30.0135,
            "longitude": 75.0,
            "acq_date": "2026-11-10",
            "observation_datetime_utc": "2026-11-10T11:30:00Z",
            "sensor": "VIIRS",
            "platform": "NOAA-21",
            "daynight": "D",
        },
        {
            "observation_id": "V3",
            "latitude": 31.0,
            "longitude": 76.0,
            "acq_date": "2026-11-10",
            "observation_datetime_utc": "2026-11-10T11:00:00Z",
            "sensor": "VIIRS",
            "platform": "NOAA-20",
            "daynight": "N",
        },
        {
            "observation_id": "V4",
            "latitude": 30.0,
            "longitude": 75.0,
            "acq_date": "2026-11-11",
            "observation_datetime_utc": "2026-11-11T11:00:00Z",
            "sensor": "VIIRS",
            "platform": "NOAA-20",
            "daynight": "D",
        },
    ]
    return pd.DataFrame(rows)


def test_dora_finds_expected_candidate_pairs(tmp_path):
    source = tmp_path / "observations.csv"
    make_observations().to_csv(source, index=False)

    summary = run_dora(input_path=source, output_dir=tmp_path / "out")

    pairs = pd.read_csv(tmp_path / "out" / "dora_candidate_pairs.csv")

    assert len(pairs) == 2
    assert set(pairs["modis_id"]) == {"M1"}
    assert set(pairs["viirs_id"]) == {"V1", "V2"}
    assert summary["baseline_candidate_pairs"] == 2


def test_date_and_daynight_must_match(tmp_path):
    source = tmp_path / "observations.csv"
    make_observations().to_csv(source, index=False)

    run_dora(input_path=source, output_dir=tmp_path / "out")

    pairs = pd.read_csv(tmp_path / "out" / "dora_candidate_pairs.csv")

    assert "V3" not in set(pairs["viirs_id"])
    assert "V4" not in set(pairs["viirs_id"])


def test_multiple_and_unmatched_statuses(tmp_path):
    source = tmp_path / "observations.csv"
    make_observations().to_csv(source, index=False)

    run_dora(input_path=source, output_dir=tmp_path / "out")

    status = pd.read_csv(tmp_path / "out" / "dora_observation_status.csv")
    status = status.set_index("observation_id")

    assert status.loc["M1", "candidate_status"] == "multiple_candidates"
    assert status.loc["M1", "candidate_count"] == 2
    assert status.loc["M2", "candidate_status"] == "unmatched_under_criteria"
    assert status.loc["V3", "candidate_status"] == "unmatched_under_criteria"


def test_threshold_sensitivity_is_monotonic(tmp_path):
    source = tmp_path / "observations.csv"
    make_observations().to_csv(source, index=False)

    run_dora(input_path=source, output_dir=tmp_path / "out")

    sensitivity = pd.read_csv(
        tmp_path / "out" / "dora_threshold_sensitivity.csv"
    )

    one_km = sensitivity[
        (sensitivity.radius_km == 1)
        & (sensitivity.time_window_minutes == 240)
    ]["candidate_pairs"].iloc[0]

    two_km = sensitivity[
        (sensitivity.radius_km == 2)
        & (sensitivity.time_window_minutes == 240)
    ]["candidate_pairs"].iloc[0]

    five_km = sensitivity[
        (sensitivity.radius_km == 5)
        & (sensitivity.time_window_minutes == 240)
    ]["candidate_pairs"].iloc[0]

    assert one_km <= two_km <= five_km
    assert one_km == 1
    assert two_km == 2


def test_expected_output_files_are_created(tmp_path):
    source = tmp_path / "observations.csv"
    make_observations().to_csv(source, index=False)

    output = tmp_path / "out"
    run_dora(input_path=source, output_dir=output)

    expected = [
        "dora_spatial_candidates_5km.csv",
        "dora_candidate_pairs.csv",
        "dora_observation_status.csv",
        "dora_threshold_sensitivity.csv",
        "dora_run_summary.json",
    ]

    for name in expected:
        assert (output / name).is_file()

    summary = json.loads(
        (output / "dora_run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["baseline_candidate_pairs"] == 2


def test_missing_required_column_raises_error(tmp_path):
    source = tmp_path / "invalid.csv"
    pd.DataFrame({"latitude": [30.0]}).to_csv(source, index=False)

    with pytest.raises(ValueError, match="Missing required columns"):
        run_dora(input_path=source, output_dir=tmp_path / "out")

def test_dora_exports_stable_uids_in_pair_reports(tmp_path):
    observations = make_observations()
    observations["observation_uid"] = [
        "UID-" + value for value in observations["observation_id"]
    ]

    source = tmp_path / "observations_with_uid.csv"
    observations.to_csv(source, index=False)

    run_dora(input_path=source, output_dir=tmp_path / "out")

    pairs = pd.read_csv(tmp_path / "out" / "dora_candidate_pairs.csv")

    assert {"modis_uid", "viirs_uid"}.issubset(pairs.columns)
    assert set(pairs["modis_uid"]) == {"UID-M1"}
    assert set(pairs["viirs_uid"]) == {"UID-V1", "UID-V2"}


def test_dora_exports_stable_uids_in_observation_status(tmp_path):
    observations = make_observations()
    observations["observation_uid"] = [
        "UID-" + value for value in observations["observation_id"]
    ]

    source = tmp_path / "observations_with_uid.csv"
    observations.to_csv(source, index=False)

    run_dora(input_path=source, output_dir=tmp_path / "out")

    status = pd.read_csv(tmp_path / "out" / "dora_observation_status.csv")
    status = status.set_index("observation_id")

    assert "observation_uid" in status.columns
    assert status.loc["M1", "observation_uid"] == "UID-M1"
    assert status.loc["V1", "observation_uid"] == "UID-V1"


def test_dora_rejects_missing_observation_uid(tmp_path):
    observations = make_observations()
    observations["observation_uid"] = [
        "UID-" + value for value in observations["observation_id"]
    ]
    observations.loc[0, "observation_uid"] = None

    source = tmp_path / "observations_invalid_uid.csv"
    observations.to_csv(source, index=False)

    with pytest.raises(ValueError, match="observation_uid contains missing"):
        run_dora(input_path=source, output_dir=tmp_path / "out")

def test_dora_scope_accounting_captures_all_exclusions(tmp_path):
    observations = make_observations()

    terra = observations.iloc[0].copy()
    terra["observation_id"] = "TERRA1"
    terra["platform"] = "Terra"

    viirs_no_aqua = observations.iloc[2].copy()
    viirs_no_aqua["observation_id"] = "V5"
    viirs_no_aqua["acq_date"] = "2026-11-12"
    viirs_no_aqua["observation_datetime_utc"] = "2026-11-12T11:00:00Z"

    aqua_no_viirs = observations.iloc[0].copy()
    aqua_no_viirs["observation_id"] = "M3"
    aqua_no_viirs["acq_date"] = "2026-11-13"
    aqua_no_viirs["observation_datetime_utc"] = "2026-11-13T10:00:00Z"

    invalid = observations.iloc[0].copy()
    invalid["observation_id"] = "BAD1"
    invalid["latitude"] = 91.0

    observations = pd.concat(
        [observations, pd.DataFrame([terra, viirs_no_aqua, aqua_no_viirs, invalid])],
        ignore_index=True,
    )

    source = tmp_path / "observations.csv"
    output = tmp_path / "out"
    observations.to_csv(source, index=False)

    summary = run_dora(input_path=source, output_dir=output)

    exclusions = pd.read_csv(output / "dora_scope_exclusions.csv")
    reasons = exclusions.set_index("observation_id")["exclusion_reason"]

    assert reasons["TERRA1"] == "modis_non_aqua_platform"
    assert reasons["V4"] == "no_same_date_modis_aqua"
    assert reasons["V5"] == "no_same_date_modis_aqua"
    assert reasons["M3"] == "no_same_date_viirs"
    assert reasons["BAD1"] == "latitude_out_of_range"
    assert summary["input_observations"] == 10
    assert summary["audited_observations"] == 5
    assert summary["excluded_observations"] == 5
    assert summary["scope_accounting_complete"] is True


def test_dora_scope_exclusion_report_preserves_input_row_numbers(tmp_path):
    observations = make_observations()
    source = tmp_path / "observations.csv"
    output = tmp_path / "out"
    observations.to_csv(source, index=False)

    run_dora(input_path=source, output_dir=output)
    exclusions = pd.read_csv(output / "dora_scope_exclusions.csv")

    assert "input_row_number" in exclusions.columns
    assert exclusions["input_row_number"].is_unique
    assert set(exclusions["observation_id"]) == {"V4"}


def test_dora_scope_accounting_summary_matches_output_files(tmp_path):
    observations = make_observations()
    source = tmp_path / "observations.csv"
    output = tmp_path / "out"
    observations.to_csv(source, index=False)

    summary = run_dora(input_path=source, output_dir=output)
    status = pd.read_csv(output / "dora_observation_status.csv")
    exclusions = pd.read_csv(output / "dora_scope_exclusions.csv")

    assert len(status) == summary["audited_observations"]
    assert len(exclusions) == summary["excluded_observations"]
    assert len(status) + len(exclusions) == summary["input_observations"]
    assert summary["scope_accounting_complete"] is True

def test_dora_rejects_blank_observation_id(tmp_path):
    observations = make_observations()
    observations.loc[0, "observation_id"] = "   "

    source = tmp_path / "observations.csv"
    output = tmp_path / "out"
    observations.to_csv(source, index=False)

    summary = run_dora(input_path=source, output_dir=output)

    exclusions = pd.read_csv(output / "dora_scope_exclusions.csv")

    assert "missing_observation_id" in exclusions["exclusion_reason"].values
    assert summary["scope_accounting_complete"] is True
    assert summary["input_observations"] == (
        summary["audited_observations"] + summary["excluded_observations"]
    )
