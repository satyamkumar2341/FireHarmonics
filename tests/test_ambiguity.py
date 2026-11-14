import json

import pandas as pd
import pytest

from src.ambiguity import run_ambiguity_analysis


def make_pairs(path):
    df = pd.DataFrame([
        {"modis_id": "M1", "viirs_id": "V1", "distance_km": 0.5, "time_gap_minutes": 10},
        {"modis_id": "M1", "viirs_id": "V2", "distance_km": 0.8, "time_gap_minutes": 5},
        {"modis_id": "M2", "viirs_id": "V3", "distance_km": 0.2, "time_gap_minutes": 20},
        {"modis_id": "M3", "viirs_id": "V4", "distance_km": 0.4, "time_gap_minutes": 15},
        {"modis_id": "M4", "viirs_id": "V4", "distance_km": 0.6, "time_gap_minutes": 25},
    ])
    df.to_csv(path, index=False)


def test_outputs_and_summary(tmp_path):
    source = tmp_path / "pairs.csv"
    output = tmp_path / "output"
    make_pairs(source)

    summary = run_ambiguity_analysis(source, output)

    ranked = pd.read_csv(output / "dora_ranked_candidates.csv")
    saved_summary = json.loads(
        (output / "dora_ambiguity_summary.json").read_text(encoding="utf-8")
    )

    assert len(ranked) == 5
    assert summary["candidate_pairs"] == 5
    assert saved_summary["candidate_pairs"] == 5
    assert ranked["modis_id"].nunique() == 4
    assert ranked["viirs_id"].nunique() == 4


def test_ranking_uses_distance_then_time(tmp_path):
    source = tmp_path / "pairs.csv"
    output = tmp_path / "output"
    make_pairs(source)

    run_ambiguity_analysis(source, output)
    ranked = pd.read_csv(output / "dora_ranked_candidates.csv")

    m1 = ranked[ranked["modis_id"] == "M1"].sort_values("rank_for_modis")

    assert m1.iloc[0]["viirs_id"] == "V1"
    assert m1.iloc[1]["viirs_id"] == "V2"
    assert list(m1["rank_for_modis"]) == [1, 2]


def test_ambiguity_classification(tmp_path):
    source = tmp_path / "pairs.csv"
    output = tmp_path / "output"
    make_pairs(source)

    run_ambiguity_analysis(source, output)
    ranked = pd.read_csv(output / "dora_ranked_candidates.csv")

    m1_v1 = ranked[
        (ranked["modis_id"] == "M1") & (ranked["viirs_id"] == "V1")
    ].iloc[0]

    m3_v4 = ranked[
        (ranked["modis_id"] == "M3") & (ranked["viirs_id"] == "V4")
    ].iloc[0]

    m4_v4 = ranked[
        (ranked["modis_id"] == "M4") & (ranked["viirs_id"] == "V4")
    ].iloc[0]

    assert m1_v1["ambiguity_type"] == "ambiguous_for_modis"
    assert m3_v4["ambiguity_type"] == "ambiguous_for_viirs"
    assert m4_v4["ambiguity_type"] == "ambiguous_for_viirs"


def test_duplicate_pairs_are_rejected(tmp_path):
    source = tmp_path / "pairs.csv"
    output = tmp_path / "output"

    df = pd.DataFrame([
        {"modis_id": "M1", "viirs_id": "V1", "distance_km": 0.5, "time_gap_minutes": 10},
        {"modis_id": "M1", "viirs_id": "V1", "distance_km": 0.6, "time_gap_minutes": 12},
    ])
    df.to_csv(source, index=False)

    with pytest.raises(ValueError, match="Duplicate"):
        run_ambiguity_analysis(source, output)

def test_ambiguity_preserves_stable_uids(tmp_path):
    source = tmp_path / "candidate_pairs.csv"

    pd.DataFrame([
        {
            "modis_id": "M1",
            "viirs_id": "V1",
            "modis_uid": "UID-M1",
            "viirs_uid": "UID-V1",
            "distance_km": 1.0,
            "time_gap_minutes": 10.0,
        },
        {
            "modis_id": "M1",
            "viirs_id": "V2",
            "modis_uid": "UID-M1",
            "viirs_uid": "UID-V2",
            "distance_km": 1.5,
            "time_gap_minutes": 20.0,
        },
    ]).to_csv(source, index=False)

    run_ambiguity_analysis(
        input_path=source,
        output_dir=tmp_path / "out",
    )

    ranked = pd.read_csv(
        tmp_path / "out" / "dora_ranked_candidates.csv"
    )

    assert {"modis_uid", "viirs_uid"}.issubset(ranked.columns)
    assert set(ranked["modis_uid"]) == {"UID-M1"}
    assert set(ranked["viirs_uid"]) == {"UID-V1", "UID-V2"}
