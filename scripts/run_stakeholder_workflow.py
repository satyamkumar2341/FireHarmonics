from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging"

def latest_folder(pattern):
    matches = sorted(STAGING.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No staging folder found for {pattern}")
    return matches[-1]

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def date_key(series):
    return pd.to_datetime(series, errors="coerce", utc=True).dt.strftime("%Y-%m-%d")

# Resolve verified inputs.
p6 = latest_folder("problem6_historical_anomaly_*")
p1 = latest_folder("problem1_nasa_*")
p7 = latest_folder("problem7_critical_burning_windows_*")

alerts_path = p6 / "anomaly_alerts.csv"
daily_path = p1 / "problem2_activity_calendar" / "daily_activity_calendar.csv"
critical_path = p7 / "critical_months.csv"

for path in (alerts_path, daily_path, critical_path):
    if not path.is_file():
        raise FileNotFoundError(f"Required input missing: {path}")

alerts = pd.read_csv(alerts_path)
daily = pd.read_csv(daily_path)
critical = pd.read_csv(critical_path)

required_alerts = {
    "date", "platform", "grid_id", "observation_count",
    "latitude_center", "longitude_center", "robust_score",
    "severity", "interpretation"
}
required_daily = {"date", "observation_count", "unique_platforms"}
required_critical = {"month", "critical_month"}

for label, frame, required in (
    ("anomaly alerts", alerts, required_alerts),
    ("daily activity", daily, required_daily),
    ("critical months", critical, required_critical),
):
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label}: required columns missing: {missing}")

alerts = alerts.copy()
daily = daily.copy()
critical = critical.copy()

alerts["date_key"] = date_key(alerts["date"])
daily["date_key"] = date_key(daily["date"])

if alerts["date_key"].isna().any():
    raise ValueError("Anomaly alerts contain invalid dates.")
if daily["date_key"].isna().any():
    raise ValueError("Daily activity calendar contains invalid dates.")

# Normalize the historical critical-month lookup.
critical["month_num"] = pd.to_numeric(critical["month"], errors="coerce")
if critical["month_num"].isna().all() and "month_name" in critical.columns:
    critical["month_num"] = pd.to_datetime(
        critical["month_name"], format="%B", errors="coerce"
    ).dt.month

if critical["month_num"].isna().any():
    raise ValueError("Could not interpret critical-month values.")

critical_lookup = {}
for _, row in critical.iterrows():
    value = row["critical_month"]
    is_critical = str(value).strip().lower() in {"true", "1", "yes"}
    critical_lookup[int(row["month_num"])] = is_critical

# Attach contextual activity without interpreting missing dates as zero.
daily_context = daily[
    ["date_key", "observation_count", "unique_platforms"]
].drop_duplicates("date_key").rename(columns={
    "observation_count": "all_platform_daily_observations",
    "unique_platforms": "daily_unique_platforms"
})

queue = alerts.merge(daily_context, on="date_key", how="left", validate="many_to_one")
queue["month_num"] = pd.to_datetime(queue["date_key"]).dt.month
queue["historical_critical_month"] = queue["month_num"].map(critical_lookup).fillna(False)

queue["severity_normalized"] = queue["severity"].astype(str).str.strip().str.lower()

priority_map = {
    "high": "P1 — PRIORITY REVIEW",
    "medium": "P2 — REVIEW",
    "low": "P3 — MONITOR",
    "normal": "NO ANOMALY FLAG",
    "insufficient_history": "NOT RANKED — INSUFFICIENT HISTORY"
}
queue["review_priority"] = queue["severity_normalized"].map(priority_map).fillna(
    "MANUAL REVIEW — UNKNOWN SEVERITY"
)

stakeholder_map = {
    "high": "Fire analyst / emergency-management liaison",
    "medium": "Fire analyst",
    "low": "Monitoring analyst",
    "normal": "No anomaly escalation",
    "insufficient_history": "Data-quality analyst"
}
queue["primary_stakeholder"] = queue["severity_normalized"].map(stakeholder_map).fillna(
    "Data-quality analyst"
)

action_map = {
    "high": (
        "Prioritize human verification; inspect the underlying satellite observations, "
        "available cross-platform evidence and independent local information."
    ),
    "medium": (
        "Queue for analyst review; inspect source observations and compare available "
        "independent evidence before drawing conclusions."
    ),
    "low": (
        "Monitor subsequent observations and review the local time-series context; "
        "do not treat this flag as a confirmed incident."
    ),
    "normal": (
        "No anomaly-based escalation suggested by this baseline; normal monitoring may continue."
    ),
    "insufficient_history": (
        "Do not rank as an anomaly; collect more historical active-observation days "
        "before interpreting this grid-platform baseline."
    )
}
queue["recommended_next_step"] = queue["severity_normalized"].map(action_map).fillna(
    "Review source data and confirm the severity interpretation."
)

queue["verification_requirement"] = (
    "Verify original FIRMS observations and seek independent corroboration; "
    "satellite detections alone do not confirm a fire or justify dispatch."
)

queue["historical_context_note"] = queue["historical_critical_month"].map({
    True: "Month is flagged in the historical satellite-observation activity profile; this is not a fire-risk forecast.",
    False: "Month is not flagged in the historical critical-month profile; this does not imply absence of fire."
})

queue = queue.sort_values(
    ["severity_normalized", "robust_score", "date_key"],
    ascending=[True, False, True]
).reset_index(drop=True)

# Explicitly retain non-actionable records for transparency.
actionable = queue[queue["severity_normalized"].isin(["high", "medium", "low"])].copy()

guidance = pd.DataFrame([
    {
        "stakeholder": "Fire / geospatial analyst",
        "workflow_step": "Inspect source observations, timestamps, platform, confidence fields and spatial context.",
        "decision_boundary": "A satellite hotspot is an observation, not a confirmed fire event."
    },
    {
        "stakeholder": "Emergency-management liaison",
        "workflow_step": "Use analyst-reviewed evidence alongside trusted local reports and official channels.",
        "decision_boundary": "This prototype is not an operational dispatch or evacuation system."
    },
    {
        "stakeholder": "Fire-response organization",
        "workflow_step": "Follow established agency procedures and independently verify incident information.",
        "decision_boundary": "Do not dispatch solely on this research queue."
    },
    {
        "stakeholder": "Data / research team",
        "workflow_step": "Review insufficient-history records, missing coverage, sensor differences and provenance.",
        "decision_boundary": "Missing satellite observations must not be interpreted as zero fire activity."
    },
    {
        "stakeholder": "Public-information team",
        "workflow_step": "Communicate only verified information through authorized official channels.",
        "decision_boundary": "Do not publish candidate detections as confirmed incidents."
    }
])

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out = STAGING / f"problem9_stakeholder_workflow_{timestamp}"
out.mkdir(parents=True, exist_ok=False)

# Keep source identifiers and the evidence trail in the outputs.
queue_path = out / "stakeholder_review_queue.csv"
actionable_path = out / "actionable_review_queue.csv"
guidance_path = out / "stakeholder_guidance_matrix.csv"

queue.to_csv(queue_path, index=False)
actionable.to_csv(actionable_path, index=False)
guidance.to_csv(guidance_path, index=False)

# Output integrity checks.
queue_check = pd.read_csv(queue_path)
action_check = pd.read_csv(actionable_path)
if len(queue_check) != len(alerts):
    raise RuntimeError("Review queue row-count mismatch.")
if len(action_check) != len(actionable):
    raise RuntimeError("Actionable queue row-count mismatch.")
if not set(action_check["severity_normalized"]).issubset({"high", "medium", "low"}):
    raise RuntimeError("Non-actionable severity leaked into actionable queue.")

key_cols = ["date_key", "platform", "grid_id"]
duplicate_keys = int(queue.duplicated(key_cols).sum())

summary = {
    "project": "FireHarmonics",
    "problem": 9,
    "title": "Stakeholder Impact and Action Workflow",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "inputs": {
        "anomaly_alerts": str(alerts_path.relative_to(ROOT)),
        "daily_activity_calendar": str(daily_path.relative_to(ROOT)),
        "critical_months": str(critical_path.relative_to(ROOT))
    },
    "input_sha256": {
        "anomaly_alerts": sha256(alerts_path),
        "daily_activity_calendar": sha256(daily_path),
        "critical_months": sha256(critical_path)
    },
    "counts": {
        "total_review_records": int(len(queue)),
        "actionable_records_high_medium_low": int(len(actionable)),
        "high": int((queue["severity_normalized"] == "high").sum()),
        "medium": int((queue["severity_normalized"] == "medium").sum()),
        "low": int((queue["severity_normalized"] == "low").sum()),
        "normal": int((queue["severity_normalized"] == "normal").sum()),
        "insufficient_history": int((queue["severity_normalized"] == "insufficient_history").sum()),
        "invalid_or_unknown_severity": int((~queue["severity_normalized"].isin(
            ["high", "medium", "low", "normal", "insufficient_history"]
        )).sum()),
        "duplicate_date_platform_grid_keys": duplicate_keys,
        "records_with_daily_context": int(queue["all_platform_daily_observations"].notna().sum())
    },
    "outputs": {
        "review_queue": str(queue_path.relative_to(ROOT)),
        "actionable_queue": str(actionable_path.relative_to(ROOT)),
        "stakeholder_guidance": str(guidance_path.relative_to(ROOT))
    },
    "interpretation_and_limitations": [
        "This is a retrospective research triage workflow, not a live alerting service.",
        "Satellite hotspot observations are not confirmed fire events.",
        "Priority labels are review-order suggestions, not emergency severity classifications.",
        "Independent local verification is required before operational decisions.",
        "Historical critical-month labels describe satellite-observation activity, not fire probability.",
        "Missing satellite observations do not mean zero fire activity.",
        "The anomaly baseline is platform/grid-specific and requires sufficient prior active-observation days."
    ]
}

audit_path = out / "problem9_workflow_audit.json"
audit_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

print("\nPROBLEM9_OK")
print("Output directory:", out)
print("Total review records:", len(queue))
print("Actionable records:", len(actionable))
print("Priority counts:", json.dumps(summary["counts"], indent=2))
print("Audit:", audit_path)