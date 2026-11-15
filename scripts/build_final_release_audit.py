from pathlib import Path
import json, subprocess, sys
from datetime import datetime, timezone

root = Path.cwd()
staging = root / "data" / "staging"
checks = []

def check(name, ok, detail=""):
    checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": str(detail)})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

def find_file(name):
    found = list(staging.rglob(name))
    return max(found, key=lambda p: p.stat().st_mtime) if found else None

archive = root / "data/raw/historical_sp_archive/20230301_20260731/historical_archive_manifest.json"
data = root / "data/staging/problem1_nasa_20261115_193025/processed/harmonized_observations.csv"

check("NASA archive manifest", archive.is_file(), archive)
check("Harmonized observations", data.is_file(), data)

for name in [
    "daily_activity_calendar.csv",
    "dora_candidate_pairs.csv",
    "sensor_raw_platform_summary.csv",
    "all_scenes_ranked.csv",
    "best_scene_per_location.csv",
    "anomaly_alerts.csv",
    "problem6_validation_audit.json",
    "critical_burning_windows.csv",
    "problem7_analysis_audit.json",
    "stakeholder_review_queue.csv",
    "problem9_workflow_audit.json"
]:
    p = find_file(name)
    check(name, p is not None, p or "Missing")

app = root / "app.py"
app_text = app.read_text(encoding="utf-8-sig", errors="replace") if app.exists() else ""
check("Research Explorer integration",
      "Research Explorer" in app_text and "FIREHARMONICS_PROBLEM8_RESEARCH_EXPLORER" in app_text)

py_files = list((root / "src").rglob("*.py")) + list((root / "scripts").rglob("*.py"))
if app.exists():
    py_files.append(app)

errors = []
for p in py_files:
    try:
        compile(p.read_text(encoding="utf-8-sig"), str(p), "exec")
    except Exception as e:
        errors.append(f"{p}: {e}")
check("Python syntax", not errors, errors or f"{len(py_files)} files valid")

print("\n========== PYTEST ==========")
test = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
check("Pytest", test.returncode == 0, (test.stdout + test.stderr)[-1500:])

limitations = [
    "HLS L30 scene and asset metadata inventoried; pixel-level raster QA remains pending.",
    "HLS surface reflectance is not thermal active-fire ground truth.",
    "MODIS/VIIRS detections are satellite observations, not confirmed fire events.",
    "DORA outputs are candidate correspondences, not confirmed same-fire matches.",
    "Anomaly alerts describe unusual observation volume, not confirmed outbreaks.",
    "Critical windows describe observation activity, not causal fire-risk forecasts.",
    "Missing observations do not prove absence of fire."
]

failed = [x for x in checks if x["status"] == "FAIL"]
status = "AUDIT_PASS_WITH_LIMITATIONS" if not failed else "AUDIT_FAILED"

out = staging / ("final_release_audit_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
out.mkdir(parents=True, exist_ok=True)

manifest = {
    "project": "FireHarmonics",
    "status": status,
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "checks": checks,
    "limitations": limitations
}
(out / "final_release_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

report = [
    "# FireHarmonics Final Release Audit",
    "",
    f"**Status:** `{status}`",
    f"**Checks passed:** {len(checks)-len(failed)}/{len(checks)}",
    "",
    "| Check | Status | Detail |",
    "|---|---|---|"
]
for x in checks:
    report.append(f"| {x['check']} | {x['status']} | {x['detail']} |")
report += ["", "## Scientific and technical limitations", ""] + [f"- {x}" for x in limitations]
(root / "docs").mkdir(exist_ok=True)
(root / "docs/FINAL_RELEASE_AUDIT.md").write_text("\n".join(report), encoding="utf-8")

(root / "docs/REPRODUCIBILITY_GUIDE.md").write_text(
"""# FireHarmonics Reproducibility Guide

Run from the project root with the virtual environment activated.

## Tests
`python -m pytest -q`

## Dashboard
`python -m streamlit run app.py`

## Data
- NASA archive: `data/raw/historical_sp_archive/`
- Harmonized data: `data/staging/problem1_nasa_20261115_193025/processed/`
- Analysis scripts: `scripts/`
- Source modules: `src/`
- Generated audit outputs: `data/staging/`

Satellite detections are observations, not confirmed fire events. DORA matches are candidates. HLS metadata availability does not prove pixel-level validation.
""", encoding="utf-8")

print("\nFINAL STATUS:", status)
print("REPORT:", root / "docs/FINAL_RELEASE_AUDIT.md")
print("MANIFEST:", out / "final_release_manifest.json")

if failed:
    sys.exit(2)
print("PROBLEM10_AUDIT_COMPLETE")
