import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.firms_client import get_api_key, PUNJAB_HARYANA_BBOX


TARGET_DATE = "2025-11-10"
DAY_RANGE = 1

SOURCES = [
    "MODIS_SP",
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
]

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

RAW_DIR = Path("data/raw")
MANIFEST_DIR = RAW_DIR / "manifests"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_sp_source(source, api_key, bbox):
    area = ",".join(bbox.split(","))

    url = (
        f"{BASE_URL}/{quote(api_key, safe='')}/"
        f"{source}/{area}/{DAY_RANGE}/{TARGET_DATE}"
    )

    try:
        response = requests.get(url, timeout=90)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"NASA request failed: {type(exc).__name__}"
        ) from None

    try:
        df = pd.read_csv(StringIO(response.text))
    except Exception:
        raise RuntimeError("NASA response was not valid CSV.") from None

    if df.empty:
        raise RuntimeError(f"{source}: no observations returned.")

    df.columns = df.columns.str.strip().str.lower()

    required = {"latitude", "longitude", "acq_date"}
    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            f"{source}: missing columns {sorted(missing)}"
        )

    if not df["acq_date"].astype(str).eq(TARGET_DATE).all():
        raise RuntimeError(
            f"{source}: response contains unexpected acquisition dates."
        )

    # Preserve all NASA columns; append provenance fields.
    df["source_requested"] = source
    df["region"] = "Punjab-Haryana"

    return df


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    api_key = get_api_key()
    results = []

    print("NASA FIRMS STANDARD PROCESSING PILOT")
    print("Date:", TARGET_DATE)
    print("Region: Punjab-Haryana")
    print("Existing files will not be overwritten.\n")

    for source in SOURCES:
        output = RAW_DIR / f"{source}_{TARGET_DATE.replace('-', '')}.csv"

        if output.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing file: {output}"
            )

        print(f"Fetching {source}...")

        df = fetch_sp_source(
            source=source,
            api_key=api_key,
            bbox=PUNJAB_HARYANA_BBOX,
        )

        df.to_csv(output, index=False)

        item = {
            "source": source,
            "processing": "Standard Processing",
            "date": TARGET_DATE,
            "row_count": int(len(df)),
            "file": output.as_posix(),
            "sha256": sha256_file(output),
            "columns": df.columns.tolist(),
            "platforms": sorted(
                df["satellite"].astype(str).unique().tolist()
            ) if "satellite" in df.columns else [],
            "versions": sorted(
                df["version"].astype(str).unique().tolist()
            ) if "version" in df.columns else [],
        }

        results.append(item)

        print(f"Saved: {output}")
        print(f"Rows: {len(df)}\n")

    manifest = {
        "project": "FireHarmonics",
        "provider": "NASA FIRMS",
        "endpoint": "NASA FIRMS Area API",
        "processing": "Standard Processing",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": TARGET_DATE,
        "region": "Punjab-Haryana",
        "bounding_box_west_south_east_north": PUNJAB_HARYANA_BBOX,
        "day_range": DAY_RANGE,
        "results": results,
        "scientific_warning": (
            "Active fire detections are satellite observations, "
            "not independently confirmed fire events. "
            "Absence of a detection does not establish absence of fire."
        ),
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path = (
        MANIFEST_DIR / f"nasa_firms_sp_pilot_{timestamp}.json"
    )

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("========== PILOT SUMMARY ==========")
    for item in results:
        print(f"{item['source']}: {item['row_count']} rows")

    print("Total observations:", sum(x["row_count"] for x in results))
    print("Manifest:", manifest_path)


if __name__ == "__main__":
    main()
