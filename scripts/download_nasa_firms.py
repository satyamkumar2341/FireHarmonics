import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.firms_client import (
    fetch_area_data,
    save_raw_data,
    PUNJAB_HARYANA_BBOX,
)

SOURCES = [
    "MODIS_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
]

DAY_RANGE = 1
records = []
failures = []

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

print("NASA FIRMS SNAPSHOT DOWNLOAD")
print("Region: Punjab-Haryana")
print("Bounding box:", PUNJAB_HARYANA_BBOX)
print("Day range:", DAY_RANGE)
print("Existing raw files will not be overwritten.\n")

for source in SOURCES:
    print(f"Fetching {source}...")

    try:
        df = fetch_area_data(
            source=source,
            bbox=PUNJAB_HARYANA_BBOX,
            day_range=DAY_RANGE,
        )

        if df.empty:
            print("No observations returned.")
            records.append({
                "source": source,
                "status": "success_empty",
                "row_count": 0,
                "file": None,
            })
            continue

        output = save_raw_data(df, source)

        if output is None or not Path(output).is_file():
            raise RuntimeError("Raw CSV was not saved.")

        output = Path(output)

        item = {
            "source": source,
            "status": "success",
            "row_count": int(len(df)),
            "file": str(output).replace("\\", "/"),
            "sha256": sha256_file(output),
            "date_min": str(df["acq_date"].min()),
            "date_max": str(df["acq_date"].max()),
            "platforms": sorted(
                df["satellite"].astype(str).unique().tolist()
            ),
            "versions": sorted(
                df["version"].astype(str).unique().tolist()
            ) if "version" in df.columns else [],
        }

        records.append(item)
        print("Saved:", output.name)
        print("Rows:", len(df))

    except Exception as exc:
        failures.append({"source": source, "error": str(exc)})
        records.append({
            "source": source,
            "status": "failed",
            "error": str(exc),
        })
        print("FAILED:", exc)

manifest = {
    "project": "FireHarmonics",
    "provider": "NASA FIRMS",
    "api_base": "https://firms.modaps.eosdis.nasa.gov/api/area/csv",
    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    "region": "Punjab-Haryana",
    "bounding_box_west_south_east_north": PUNJAB_HARYANA_BBOX,
    "day_range": DAY_RANGE,
    "data_type": "Near-real-time active fire detections",
    "scientific_warning": (
        "NRT detections are not independently confirmed fire events. "
        "Absence of a detection does not establish absence of fire."
    ),
    "results": records,
    "failures": failures,
}

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
manifest_path = (
    Path("data/raw/manifests")
    / f"nasa_firms_manifest_{timestamp}.json"
)

manifest_path.write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8",
)

print("\n========== DOWNLOAD SUMMARY ==========")
print("Successful sources:", sum(
    x["status"] in ("success", "success_empty") for x in records
))
print("Failed sources:", len(failures))
print("Manifest:", manifest_path)

if failures:
    raise SystemExit("Incomplete NASA snapshot. Check failures above.")

print("NASA snapshot download completed.")
