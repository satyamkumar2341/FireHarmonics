import pandas as pd
import pytest

from src.harmonizer import normalize_file, build_harmonized_dataset


def make_modis_file(path):
    pd.DataFrame({
        "latitude": [30.0, 31.0],
        "longitude": [75.0, 76.0],
        "brightness": [320.5, 315.2],
        "scan": [1.0, 1.1],
        "track": [1.0, 1.1],
        "acq_date": ["2026-11-10", "2026-11-10"],
        "acq_time": [1030, 1045],
        "satellite": ["Aqua", "Terra"],
        "instrument": ["MODIS", "MODIS"],
        "confidence": [65, 72],
        "frp": [12.5, 20.0],
        "daynight": ["D", "N"],
    }).to_csv(path, index=False)


def make_viirs_file(path):
    pd.DataFrame({
        "latitude": [30.1],
        "longitude": [75.1],
        "bright_ti4": [340.2],
        "scan": [0.5],
        "track": [0.6],
        "acq_date": ["2026-11-10"],
        "acq_time": [1130],
        "satellite": ["N20"],
        "instrument": ["VIIRS"],
        "confidence": ["n"],
        "frp": [8.5],
        "daynight": ["D"],
    }).to_csv(path, index=False)


def test_modis_preserves_aqua_and_terra_platforms(tmp_path):
    path = tmp_path / "MODIS_NRT_20261110_120000.csv"
    make_modis_file(path)

    result = normalize_file(path)

    assert len(result) == 2
    assert set(result["platform"]) == {"Aqua", "Terra"}
    assert set(result["sensor"]) == {"MODIS"}
    assert set(result["confidence_scheme"]) == {"numeric_native"}
    assert set(result["brightness_band"]) == {"MODIS brightness"}


def test_viirs_preserves_native_confidence_and_platform(tmp_path):
    path = tmp_path / "VIIRS_NOAA20_NRT_20261110_120000.csv"
    make_viirs_file(path)

    result = normalize_file(path)

    assert len(result) == 1
    assert result.iloc[0]["sensor"] == "VIIRS"
    assert result.iloc[0]["platform"] == "NOAA-20"
    assert result.iloc[0]["confidence_native"] == "n"
    assert result.iloc[0]["confidence_scheme"] == "nominal"
    assert result.iloc[0]["brightness_band"] == "VIIRS I4"


def test_invalid_required_columns_raise_clear_error(tmp_path):
    path = tmp_path / "MODIS_NRT_20261110_120000.csv"
    pd.DataFrame({"latitude": [30.0]}).to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing columns"):
        normalize_file(path)


def test_build_dataset_writes_expected_rows_and_ids(tmp_path, monkeypatch):
    import src.harmonizer as harmonizer

    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    raw_dir.mkdir()

    make_modis_file(raw_dir / "MODIS_NRT_20261110_120000.csv")
    make_viirs_file(raw_dir / "VIIRS_NOAA20_NRT_20261110_120000.csv")

    monkeypatch.setattr(harmonizer, "RAW_DIR", raw_dir)
    monkeypatch.setattr(harmonizer, "OUTPUT_DIR", output_dir)

    result = build_harmonized_dataset()

    saved = pd.read_csv(output_dir / "harmonized_observations.csv")

    assert len(result) == 3
    assert len(saved) == 3
    assert saved["observation_id"].is_unique
    assert saved["observation_id"].tolist() == [
        "FH-0000001", "FH-0000002", "FH-0000003"
    ]
    assert set(saved["sensor"]) == {"MODIS", "VIIRS"}
    assert "observation_uid" in saved.columns
    assert saved["observation_uid"].notna().all()
    assert saved["observation_uid"].str.startswith("FHUID-").all()

def test_observation_uid_is_stable_across_snapshot_filenames(tmp_path):
    first_path = tmp_path / "MODIS_NRT_20261110_120000.csv"
    second_path = tmp_path / "MODIS_NRT_20261110_130000.csv"

    make_modis_file(first_path)
    make_modis_file(second_path)

    first = normalize_file(first_path)
    second = normalize_file(second_path)

    first_uids = dict(zip(first["platform"], first["observation_uid"]))
    second_uids = dict(zip(second["platform"], second["observation_uid"]))

    assert first_uids == second_uids
    assert len(set(first["observation_uid"])) == 2


def test_build_dataset_removes_duplicate_uids_across_snapshots(
    tmp_path, monkeypatch
):
    import src.harmonizer as harmonizer

    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    raw_dir.mkdir()

    make_modis_file(raw_dir / "MODIS_NRT_20261110_120000.csv")
    make_modis_file(raw_dir / "MODIS_NRT_20261110_130000.csv")

    monkeypatch.setattr(harmonizer, "RAW_DIR", raw_dir)
    monkeypatch.setattr(harmonizer, "OUTPUT_DIR", output_dir)

    result = build_harmonized_dataset()

    assert len(result) == 2
    assert result["observation_uid"].is_unique
    assert result["observation_id"].is_unique

def test_build_dataset_preserves_legacy_ids_when_new_observations_arrive(
    tmp_path, monkeypatch
):
    import src.harmonizer as harmonizer

    raw_dir = tmp_path / "raw"
    output_dir = tmp_path / "processed"
    raw_dir.mkdir()

    first_file = raw_dir / "MODIS_NRT_20261110_120000.csv"
    second_file = raw_dir / "MODIS_NRT_20261110_130000.csv"

    make_modis_file(first_file)

    monkeypatch.setattr(harmonizer, "RAW_DIR", raw_dir)
    monkeypatch.setattr(harmonizer, "OUTPUT_DIR", output_dir)

    first_result = build_harmonized_dataset()
    old_ids = dict(zip(
        first_result["observation_uid"],
        first_result["observation_id"]
    ))

    updated_data = pd.read_csv(first_file)
    new_observation = updated_data.iloc[[0]].copy()
    new_observation["latitude"] = 30.5
    new_observation["longitude"] = 75.5
    new_observation["brightness"] = 330.0
    new_observation["acq_time"] = 1100
    new_observation["confidence"] = 80
    new_observation["frp"] = 25.0

    updated_data = pd.concat(
        [updated_data, new_observation],
        ignore_index=True
    )
    updated_data.to_csv(second_file, index=False)

    second_result = build_harmonized_dataset()

    new_ids = dict(zip(
        second_result["observation_uid"],
        second_result["observation_id"]
    ))

    for uid, old_id in old_ids.items():
        assert new_ids[uid] == old_id

    added = second_result[
        ~second_result["observation_uid"].isin(old_ids)
    ]

    assert len(added) == 1
    assert added.iloc[0]["observation_id"] == "FH-0000003"


def test_staging_build_preserves_production_ids(tmp_path):
    import hashlib
    import src.harmonizer as harmonizer

    raw_dir = tmp_path / "raw"
    production_dir = tmp_path / "production"
    staging_dir = tmp_path / "staging"

    raw_dir.mkdir()
    make_modis_file(raw_dir / "MODIS_NRT_20261110_120000.csv")

    production = harmonizer.build_harmonized_dataset(
        raw_dir=raw_dir,
        output_dir=production_dir,
    )

    production_file = production_dir / "harmonized_observations.csv"
    production_hash_before = hashlib.sha256(
        production_file.read_bytes()
    ).hexdigest()

    production_ids = dict(zip(
        production["observation_uid"],
        production["observation_id"],
    ))

    staging = harmonizer.build_harmonized_dataset(
        raw_dir=raw_dir,
        output_dir=staging_dir,
        previous_dataset_path=production_file,
    )

    staging_ids = dict(zip(
        staging["observation_uid"],
        staging["observation_id"],
    ))

    assert staging_ids == production_ids
    assert len(staging) == len(production)
    assert staging["observation_uid"].is_unique
    assert staging["observation_id"].is_unique

    production_hash_after = hashlib.sha256(
        production_file.read_bytes()
    ).hexdigest()

    assert production_hash_before == production_hash_after
    assert (staging_dir / "harmonized_observations.csv").exists()
