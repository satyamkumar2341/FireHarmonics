import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.firms_client import get_api_key, PUNJAB_HARYANA_BBOX


START_DATE = date(2025, 11, 1)
END_DATE = date(2025, 11, 30)
CHUNK_SIZE = 5
MAX_ATTEMPTS = 3
REQUEST_DELAY_SECONDS = 1.0

SOURCES = [
    "MODIS_SP",
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
]

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AVAILABILITY_URL = (
    "https://firms.modaps.eosdis.eosdis.nasa.gov/"
    "api/data_availability/csv"
)

OUTPUT_DIR = (
    Path("data/raw/historical_sp")
    / f"{START_DATE:%Y-%m}"
)
MANIFEST_PATH = OUTPUT_DIR / "historical_download_manifest.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_manifest():
    expected = {
        "project": "FireHarmonics",
        "provider": "NASA FIRMS",
        "processing": "Standard Processing",
        "region": "Punjab-Haryana",
        "period_start": START_DATE.isoformat(),
        "period_end": END_DATE.isoformat(),
        "chunk_size_days": CHUNK_SIZE,
    }

    if MANIFEST_PATH.exists():
        manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )

        for field, expected_value in expected.items():
            if manifest.get(field) != expected_value:
                raise RuntimeError(
                    f"Manifest configuration mismatch: {field}. "
                    "Review the manifest before continuing."
                )

        if list(manifest.get("bbox_west_south_east_north", [])) != list(
            PUNJAB_HARYANA_BBOX
        ):
            raise RuntimeError(
                "Manifest bounding box mismatch. "
                "Review the manifest before continuing."
            )

        if not isinstance(manifest.get("chunks"), dict):
            raise RuntimeError("Manifest chunks field is invalid.")

        return manifest

    return {
        **expected,
        "bbox_west_south_east_north": list(PUNJAB_HARYANA_BBOX),
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "chunks": {},
        "scientific_warning": (
            "Active fire detections are satellite observations, "
            "not independently confirmed fire events. "
            "No detections do not establish absence of fire."
        ),
    }


def save_manifest(manifest):
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(MANIFEST_PATH, manifest)


def get_availability(api_key):
    url = (
        "https://firms.modaps.eosdis.nasa.gov/"
        "api/data_availability/csv/"
        f"{quote(api_key, safe='')}/ALL"
    )

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Availability request failed: {type(exc).__name__}"
        ) from None

    df = pd.read_csv(StringIO(response.text))
    required = {"data_id", "min_date", "max_date"}

    if not required.issubset(df.columns):
        raise RuntimeError(
            "Unexpected NASA availability API schema."
        )

    df["min_date"] = pd.to_datetime(
        df["min_date"], errors="raise"
    ).dt.date
    df["max_date"] = pd.to_datetime(
        df["max_date"], errors="raise"
    ).dt.date

    return df


def make_chunks():
    chunks = []
    current = START_DATE

    while current <= END_DATE:
        chunk_end = min(
            current + timedelta(days=CHUNK_SIZE - 1),
            END_DATE,
        )
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)

    return chunks


def fetch_chunk(source, start, end, api_key):
    day_range = (end - start).days + 1
    url = (
        f"{BASE_URL}/{quote(api_key, safe='')}/"
        f"{source}/{PUNJAB_HARYANA_BBOX}/"
        f"{day_range}/{start.isoformat()}"
    )

    last_error = "Unknown request failure"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()

            df = pd.read_csv(StringIO(response.text))
            df.columns = df.columns.str.strip().str.lower()

            required = {"latitude", "longitude", "acq_date"}
            missing = required - set(df.columns)

            if missing:
                raise RuntimeError(
                    f"Missing required CSV columns: {sorted(missing)}"
                )

            if df.empty:
                return df

            dates = pd.to_datetime(
                df["acq_date"], errors="raise"
            ).dt.date

            if ((dates < start) | (dates > end)).any():
                raise RuntimeError(
                    "NASA response contains dates outside requested chunk."
                )

            df["source_requested"] = source
            df["region"] = "Punjab-Haryana"
            df["requested_chunk_start"] = start.isoformat()
            df["requested_chunk_end"] = end.isoformat()

            return df

        except Exception as exc:
            last_error = f"{type(exc).__name__} (details redacted)"

            if attempt < MAX_ATTEMPTS:
                wait = 2 ** attempt
                print(
                    f"  Attempt {attempt} failed; "
                    f"retrying in {wait}s ({type(exc).__name__})"
                )
                time.sleep(wait)

    raise RuntimeError(last_error)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    api_key = get_api_key()
    manifest = load_manifest()

    print("NASA FIRMS HISTORICAL SP DOWNLOAD")
    print("Period:", START_DATE, "to", END_DATE)
    print("Region: Punjab-Haryana")
    print("Output:", OUTPUT_DIR)
    print("Existing completed chunks will be skipped.\n")

    availability = get_availability(api_key)

    for source in SOURCES:
        rows = availability.loc[
            availability["data_id"] == source
        ]

        if rows.empty:
            raise RuntimeError(
                f"Source missing from NASA availability API: {source}"
            )

        minimum = rows.iloc[0]["min_date"]
        maximum = rows.iloc[0]["max_date"]

        if START_DATE < minimum or END_DATE > maximum:
            raise RuntimeError(
                f"{source} does not cover requested period "
                f"({minimum} to {maximum})."
            )

        print(f"Availability verified: {source}")

    chunks = make_chunks()
    failures = []

    for source in SOURCES:
        for start, end in chunks:
            key = f"{source}_{start:%Y%m%d}_{end:%Y%m%d}"
            output = OUTPUT_DIR / f"{key}.csv"

            previous = manifest["chunks"].get(key)

            if previous and previous.get("status") in {
                "downloaded",
                "success_empty",
            }:
                if previous["status"] == "downloaded":
                    if not output.is_file():
                        raise RuntimeError(
                            f"Manifest says downloaded but file is missing: {output}"
                        )
                    if sha256_file(output) != previous.get("sha256"):
                        raise RuntimeError(
                            f"Checksum mismatch; refusing to skip: {output}"
                        )

                print(f"SKIP completed: {key}")
                continue

            if output.exists():
                raise FileExistsError(
                    f"File exists without a verified completed manifest entry: {output}"
                )

            print(f"\nFetching {key}...")

            try:
                df = fetch_chunk(source, start, end, api_key)

                if df.empty:
                    manifest["chunks"][key] = {
                        "source": source,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "status": "success_empty",
                        "row_count": 0,
                        "retrieved_at_utc": utc_now(),
                    }
                    print("  Successful response: zero observations.")

                else:
                    temporary = output.with_suffix(".csv.tmp")
                    df.to_csv(temporary, index=False)
                    temporary.replace(output)

                    manifest["chunks"][key] = {
                        "source": source,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "status": "downloaded",
                        "row_count": int(len(df)),
                        "file": output.as_posix(),
                        "sha256": sha256_file(output),
                        "columns": df.columns.tolist(),
                        "retrieved_at_utc": utc_now(),
                    }

                    print("  Rows:", len(df))
                    print("  Saved:", output)

                save_manifest(manifest)

            except Exception as exc:
                manifest["chunks"][key] = {
                    "source": source,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": f"{type(exc).__name__} (details redacted)",
                    "retrieved_at_utc": utc_now(),
                }
                save_manifest(manifest)

                failures.append(key)
                print("  FAILED:", type(exc).__name__, "(details redacted)")

            time.sleep(REQUEST_DELAY_SECONDS)

    print("\n========== DOWNLOAD SUMMARY ==========")

    statuses = [
        item.get("status")
        for item in manifest["chunks"].values()
    ]

    print("Completed with data:", statuses.count("downloaded"))
    print("Completed empty:", statuses.count("success_empty"))
    print("Failed:", statuses.count("failed"))
    print("Manifest:", MANIFEST_PATH)

    if failures:
        print("\nFailed chunks (retry by running this script again):")
        for key in failures:
            print(" -", key)
        raise SystemExit(1)

    print("\nHISTORICAL DOWNLOAD BATCH COMPLETED.")


if __name__ == "__main__":
    main()
