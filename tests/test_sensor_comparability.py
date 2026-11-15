import pandas as pd
import pytest

from src.sensor_comparability import analyze_sensor_comparability


@pytest.fixture
def observations():
    return pd.DataFrame([
        {
            "observation_uid": "M1", "sensor": "MODIS",
            "platform": "Aqua", "frp_mw": 10.0,
            "brightness_native_kelvin": 310.0,
            "confidence_scheme": "numeric_native",
            "confidence_native": "80",
        },
        {
            "observation_uid": "M2", "sensor": "MODIS",
            "platform": "Aqua", "frp_mw": 12.0,
            "brightness_native_kelvin": 312.0,
            "confidence_scheme": "numeric_native",
            "confidence_native": "70",
        },
        {
            "observation_uid": "M3", "sensor": "MODIS",
            "platform": "Aqua", "frp_mw": 8.0,
            "brightness_native_kelvin": 308.0,
            "confidence_scheme": "numeric_native",
            "confidence_native": "60",
        },
        {
            "observation_uid": "V1", "sensor": "VIIRS",
            "platform": "NOAA-20", "frp_mw": 4.0,
            "brightness_native_kelvin": 335.0,
            "confidence_scheme": "categorical",
            "confidence_native": "n",
        },
        {
            "observation_uid": "V2", "sensor": "VIIRS",
            "platform": "NOAA-20", "frp_mw": 5.0,
            "brightness_native_kelvin": 336.0,
            "confidence_scheme": "categorical",
            "confidence_native": "h",
        },
        {
            "observation_uid": "V3", "sensor": "VIIRS",
            "platform": "NOAA-20", "frp_mw": 6.4,
            "brightness_native_kelvin": 337.0,
            "confidence_scheme": "categorical",
            "confidence_native": "l",
        },
    ])


@pytest.fixture
def candidates():
    return pd.DataFrame([
        {
            "modis_uid": "M1", "viirs_uid": "V1",
            "date": "2025-11-01", "viirs_platform": "NOAA-20",
            "distance_km": 0.2, "time_gap_minutes": 30,
            "modis_frp_mw": 10.0, "viirs_frp_mw": 4.0,
        },
        {
            "modis_uid": "M1", "viirs_uid": "V2",
            "date": "2025-11-01", "viirs_platform": "NOAA-20",
            "distance_km": 0.1, "time_gap_minutes": 20,
            "modis_frp_mw": 10.0, "viirs_frp_mw": 5.0,
        },
        {
            "modis_uid": "M2", "viirs_uid": "V1",
            "date": "2025-11-01", "viirs_platform": "NOAA-20",
            "distance_km": 0.3, "time_gap_minutes": 40,
            "modis_frp_mw": 12.0, "viirs_frp_mw": 4.0,
        },
        {
            "modis_uid": "M3", "viirs_uid": "V3",
            "date": "2025-11-02", "viirs_platform": "NOAA-20",
            "distance_km": 1.5, "time_gap_minutes": 100,
            "modis_frp_mw": 8.0, "viirs_frp_mw": 6.4,
        },
    ])


def run_analysis(observations, candidates, seed=123):
    return analyze_sensor_comparability(
        observations,
        candidates,
        bootstrap_replicates=300,
        random_seed=seed,
    )


def test_greedy_matching_prevents_reuse(observations, candidates):
    result = run_analysis(observations, candidates)
    baseline = result["one_to_one_baseline"].iloc[0]

    assert baseline["one_to_one_pairs"] == 3
    assert baseline["unique_modis"] == 3
    assert baseline["unique_viirs"] == 3


def test_nearest_candidate_wins_for_shared_modis(observations, candidates):
    result = run_analysis(observations, candidates)
    baseline = result["one_to_one_baseline"].iloc[0]

    # M1-V2 is nearer than M1-V1; M2-V1 can then be selected.
    assert baseline["one_to_one_pairs"] == 3


def test_threshold_outputs_are_generated(observations, candidates):
    result = run_analysis(observations, candidates)

    assert len(result["threshold_bootstrap"]) == 5
    assert set(result["threshold_bootstrap"]["radius_km"]) == {1, 2}


def test_bootstrap_is_reproducible(observations, candidates):
    first = run_analysis(observations, candidates)
    second = run_analysis(observations, candidates)

    pd.testing.assert_frame_equal(
        first["date_cluster_bootstrap"],
        second["date_cluster_bootstrap"],
    )
    pd.testing.assert_frame_equal(
        first["threshold_bootstrap"],
        second["threshold_bootstrap"],
    )


def test_native_confidence_schemes_remain_separate(observations, candidates):
    result = run_analysis(observations, candidates)
    confidence = result["native_confidence_counts"]

    assert set(confidence["confidence_scheme"]) == {
        "numeric_native", "categorical"
    }


def test_missing_candidate_column_raises_error(observations, candidates):
    broken = candidates.drop(columns=["distance_km"])

    with pytest.raises(ValueError, match="distance_km"):
        run_analysis(observations, broken)


def test_missing_observation_column_raises_error(observations, candidates):
    broken = observations.drop(columns=["confidence_scheme"])

    with pytest.raises(ValueError, match="confidence_scheme"):
        run_analysis(broken, candidates)


def test_output_csvs_are_written(observations, candidates, tmp_path):
    result = analyze_sensor_comparability(
        observations,
        candidates,
        output_dir=tmp_path,
        bootstrap_replicates=300,
        random_seed=123,
    )

    for name in result:
        path = tmp_path / f"sensor_{name}.csv"
        assert path.exists()
        assert path.stat().st_size > 0



def test_missing_candidate_uid_is_rejected(observations, candidates):
    broken = candidates.copy()
    broken.loc[0, "modis_uid"] = None

    with pytest.raises(ValueError, match="modis_uid"):
        run_analysis(observations, broken)


def test_blank_candidate_platform_is_rejected(observations, candidates):
    broken = candidates.copy()
    broken.loc[0, "viirs_platform"] = " "

    with pytest.raises(ValueError, match="viirs_platform"):
        run_analysis(observations, broken)


def test_duplicate_observation_uid_is_rejected(observations, candidates):
    broken = observations.copy()
    broken.loc[1, "observation_uid"] = "M1"

    with pytest.raises(ValueError, match="must be unique"):
        run_analysis(broken, candidates)


def test_blank_observation_uid_is_rejected(observations, candidates):
    broken = observations.copy()
    broken.loc[0, "observation_uid"] = " "

    with pytest.raises(ValueError, match="missing or blank"):
        run_analysis(broken, candidates)


def test_non_integer_bootstrap_count_is_rejected(observations, candidates):
    with pytest.raises(ValueError, match="integer"):
        analyze_sensor_comparability(
            observations, candidates, bootstrap_replicates=100.5
        )


def test_empty_candidates_return_empty_pair_outputs(observations, candidates):
    empty = candidates.iloc[0:0].copy()
    result = run_analysis(observations, empty)

    assert result["one_to_one_baseline"].empty
    assert result["date_cluster_bootstrap"].empty
    assert result["threshold_bootstrap"].empty
    assert not result["raw_platform_summary"].empty
