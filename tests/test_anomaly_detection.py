import pandas as pd
from src.anomaly_detection import build_anomaly_tables

def make_data(counts):
    rows = []
    for day, count in enumerate(counts, start=1):
        for j in range(count):
            rows.append({
                "latitude": 29.0 + j * 0.0001,
                "longitude": 76.0 + j * 0.0001,
                "acq_date": f"2023-03-{day:02d}",
                "platform": "NOAA-20",
                "observation_uid": f"{day}-{j}",
            })
    return pd.DataFrame(rows)

def test_insufficient_history_is_not_alert():
    activity, alerts = build_anomaly_tables(make_data([2, 2, 2]), min_prior_active_days=3)
    assert (activity["severity"] == "insufficient_history").all()
    assert alerts.empty

def test_spike_is_flagged_after_sufficient_history():
    activity, alerts = build_anomaly_tables(make_data([2] * 10 + [30]), min_prior_active_days=7)
    last = activity.sort_values("date").iloc[-1]
    assert last["severity"] in {"medium", "high"}
    assert len(alerts) >= 1

def test_missing_dates_are_not_filled_as_zero():
    data = make_data([2, 2, 2])
    data = data[data["acq_date"] != "2023-03-02"]
    activity, _ = build_anomaly_tables(data, min_prior_active_days=1)
    assert "2023-03-02" not in set(activity["date"].astype(str))

def test_platforms_are_kept_separate():
    data = make_data([2] * 8)
    other = data.copy()
    other["platform"] = "Aqua"
    other["observation_uid"] = "a-" + other["observation_uid"]
    activity, _ = build_anomaly_tables(pd.concat([data, other]), min_prior_active_days=2)
    assert set(activity["platform"]) == {"NOAA-20", "Aqua"}

def test_required_columns_checked():
    try:
        build_anomaly_tables(pd.DataFrame({"latitude": [1]}))
    except ValueError as exc:
        assert "Missing required columns" in str(exc)
    else:
        raise AssertionError("Expected missing-column validation")

