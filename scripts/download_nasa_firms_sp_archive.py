import argparse
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

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

SOURCES = {
    "MODIS_SP": {
        "start": date(2000, 11, 1),
        "required": {
            "latitude", "longitude", "acq_date", "acq_time",
            "satellite", "instrument", "confidence", "frp",
            "brightness", "daynight",
        },
    },
    "VIIRS_SNPP_SP": {
        "start": date(2012, 1, 20),
        "required": {
            "latitude", "longitude", "acq_date", "acq_time",
            "instrument", "confidence", "frp", "bright_ti4",
            "daynight",
        },
    },
    "VIIRS_NOAA20_SP": {
        "start": date(2018, 4, 1),
        "required": {
            "latitude", "longitude", "acq_date", "acq_time",
            "instrument", "confidence", "frp", "bright_ti4",
            "daynight",
        },
    },
    "VIIRS_NOAA21_SP": {
        "start": date(2023, 3, 1),
        "required": {
            "latitude", "longitude", "acq_date", "acq_time",
            "instrument", "confidence", "frp", "bright_ti4",
            "daynight",
        },
    },
}

CHUNK_DAYS = 5
MAX_ATTEMPTS = 3
REQUEST_DELAY = 1.0
BBOX = [float(x) for x in PUNJAB_HARYANA_BBOX.split(",")]
BBOX_EDGE_TOLERANCE_DEGREES = 0.0001  # documented ~11 m latitude edge tolerance


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, payload):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def make_chunks(start, end, chunk_days):
    result = []
    current = start

    while current <= end:
        last = min(current + timedelta(days=chunk_days - 1), end)
        result.append((current, last))
        current = last + timedelta(days=1)

    return result


def get_availability(api_key):
    url = (
        "https://firms.modaps.eosdis.nasa.gov/"
        "api/data_availability/csv/"
        f"{quote(api_key, safe='')}/ALL"
    )
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    required = {"data_id", "min_date", "max_date"}

    if not required.issubset(df.columns):
        raise RuntimeError("Unexpected NASA availability response schema.")

    df["min_date"] = pd.to_datetime(
        df["min_date"], errors="raise"
    ).dt.date
    df["max_date"] = pd.to_datetime(
        df["max_date"], errors="raise"
    ).dt.date

    return df


def fetch_chunk(source, start, end, api_key):
    days = (end - start).days + 1
    area = ",".join(str(x) for x in BBOX)

    url = (
        f"{BASE_URL}/{quote(api_key, safe='')}/"
        f"{source}/{area}/{days}/{start.isoformat()}"
    )

    last_error = "Unknown request failure"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()

            if not response.text.strip():
                raise RuntimeError("NASA returned an empty response body.")

            df = pd.read_csv(StringIO(response.text))
            df.columns = df.columns.str.strip().str.lower()

            missing = SOURCES[source]["required"] - set(df.columns)
            if missing:
                raise RuntimeError(
                    f"Missing NASA CSV columns: {sorted(missing)}"
                )

            if not df.empty:
                dates = pd.to_datetime(
                    df["acq_date"], errors="raise"
                ).dt.date

                if ((dates < start) | (dates > end)).any():
                    raise RuntimeError(
                        "NASA response contains dates outside requested chunk."
                    )

                lat = pd.to_numeric(df["latitude"], errors="coerce")
                lon = pd.to_numeric(df["longitude"], errors="coerce")
                df["bbox_edge_tolerance_applied"] = (
                    (lat < BBOX[1]) | (lat > BBOX[3]) |
                    (lon < BBOX[0]) | (lon > BBOX[2])
                ) & lat.between(
                    BBOX[1] - BBOX_EDGE_TOLERANCE_DEGREES,
                    BBOX[3] + BBOX_EDGE_TOLERANCE_DEGREES
                ) & lon.between(
                    BBOX[0] - BBOX_EDGE_TOLERANCE_DEGREES,
                    BBOX[2] + BBOX_EDGE_TOLERANCE_DEGREES
                )


                if (
                    lat.isna().any()
                    or lon.isna().any()
                    or not lat.between(BBOX[1] - BBOX_EDGE_TOLERANCE_DEGREES, BBOX[3] + BBOX_EDGE_TOLERANCE_DEGREES).all()
                    or not lon.between(BBOX[0] - BBOX_EDGE_TOLERANCE_DEGREES, BBOX[2] + BBOX_EDGE_TOLERANCE_DEGREES).all()
                ):
                    raise RuntimeError(
                        "NASA response contains invalid/out-of-area coordinates."
                    )

            df["source_requested"] = source
            df["region"] = "Punjab-Haryana"
            df["requested_chunk_start"] = start.isoformat()
            df["requested_chunk_end"] = end.isoformat()

            return df

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

            if attempt < MAX_ATTEMPTS:
                wait = 2 ** attempt
                print(f"    Retry {attempt}/{MAX_ATTEMPTS} after {wait}s")
                time.sleep(wait)

    raise RuntimeError(last_error)


def main():
    parser = argparse.ArgumentParser(
        description="Download historical NASA FIRMS Standard Processing data."
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(SOURCES),
        default=list(SOURCES),
    )
    parser.add_argument("--chunk-days", type=int, default=CHUNK_DAYS)
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    if end < start:
        parser.error("end-date must not be earlier than start-date.")
    if not 1 <= args.chunk_days <= 5:
        parser.error("chunk-days must be between 1 and 5.")
    if args.delay < 0:
        parser.error("delay must be zero or positive.")

    chunks = make_chunks(start, end, args.chunk_days)
    api_key = get_api_key()

    print("Checking current NASA FIRMS archive availability...")
    availability = get_availability(api_key)

    for source in args.sources:
        record = availability.loc[availability["data_id"] == source]

        if record.empty:
            raise RuntimeError(f"NASA availability missing: {source}")

        minimum = record.iloc[0]["min_date"]
        maximum = record.iloc[0]["max_date"]

        if start < minimum or end > maximum:
            raise RuntimeError(
                f"{source}: requested period outside current coverage "
                f"({minimum} to {maximum})."
            )

        if start < SOURCES[source]["start"]:
            raise RuntimeError(f"{source}: before known product start date.")

        print(f"  Verified {source}: {minimum} to {maximum}")

    total_requests = len(chunks) * len(args.sources)

    print("\n========== ARCHIVE PLAN ==========")
    print("Period:", start, "to", end)
    print("Sources:", ", ".join(args.sources))
    print("Chunk size:", args.chunk_days, "days")
    print("Chunks per source:", len(chunks))
    print("Total potential requests:", total_requests)
    print("Bounding box W,S,E,N:", BBOX)
    print("Plan only:", args.plan_only)

    if args.plan_only:
        print("\nPLAN VERIFIED. No historical CSV files downloaded.")
        return

    output_dir = (
        PROJECT_ROOT / "data" / "raw" / "historical_sp_archive"
        / f"{start:%Y%m%d}_{end:%Y%m%d}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "historical_archive_manifest.json"

    config = {
        "project": "FireHarmonics",
        "provider": "NASA FIRMS",
        "processing": "Standard Processing",
        "region": "Punjab-Haryana",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "sources": args.sources,
        "chunk_size_days": args.chunk_days,
        "bbox_west_south_east_north": BBOX,
    }

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for field, value in config.items():
            if manifest.get(field) != value:
                raise RuntimeError(
                    f"Manifest configuration mismatch: {field}"
                )
    else:
        manifest = {
            **config,
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "availability_verified_at_utc": utc_now(),
            "chunks": {},
            "scientific_warning": (
                "Satellite active-fire detections are observations, "
                "not independently confirmed fire events. "
                "No detections do not establish absence of fire."
            ),
        }
        atomic_json(manifest_path, manifest)

    failures = []

    for source in args.sources:
        for chunk_start, chunk_end in chunks:
            key = (
                f"{source}_{chunk_start:%Y%m%d}_"
                f"{chunk_end:%Y%m%d}"
            )
            output = output_dir / f"{key}.csv"
            previous = manifest["chunks"].get(key)

            if previous and previous.get("status") in {
                "downloaded", "success_empty"
            }:
                if previous["status"] == "downloaded":
                    if not output.is_file():
                        raise RuntimeError(f"Completed file missing: {output}")
                    if sha256_file(output) != previous.get("sha256"):
                        raise RuntimeError(f"Checksum mismatch: {output}")
                    check = pd.read_csv(output)
                    if len(check) != previous.get("row_count"):
                        raise RuntimeError(f"Row-count mismatch: {output}")

                print("SKIP verified:", key)
                continue

            if output.exists():
                raise RuntimeError(
                    f"Untracked output exists; refusing to overwrite: {output}"
                )

            print(f"\nDownloading {key}")

            try:
                df = fetch_chunk(
                    source, chunk_start, chunk_end, api_key
                )

                if df.empty:
                    entry = {
                        "status": "success_empty",
                        "row_count": 0,
                    }
                    print("  Valid empty response.")
                else:
                    temp = output.with_suffix(".csv.tmp")
                    df.to_csv(temp, index=False)
                    temp.replace(output)

                    entry = {
                        "status": "downloaded",
                        "row_count": int(len(df)),
                        "file": output.relative_to(PROJECT_ROOT).as_posix(),
                        "sha256": sha256_file(output),
                        "columns": df.columns.tolist(),
                    }
                    print("  Rows:", len(df))

                manifest["chunks"][key] = {
                    "source": source,
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    **entry,
                    "retrieved_at_utc": utc_now(),
                }

            except Exception as exc:
                manifest["chunks"][key] = {
                    "source": source,
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1200],
                    "retrieved_at_utc": utc_now(),
                }
                failures.append(key)
                print("  FAILED:", type(exc).__name__, str(exc)[:500])

            manifest["updated_at_utc"] = utc_now()
            atomic_json(manifest_path, manifest)
            time.sleep(args.delay)

    statuses = [
        item["status"] for item in manifest["chunks"].values()
    ]

    print("\n========== DOWNLOAD SUMMARY ==========")
    print("Downloaded:", statuses.count("downloaded"))
    print("Empty responses:", statuses.count("success_empty"))
    print("Failed:", statuses.count("failed"))
    print("Manifest:", manifest_path)

    if failures:
        print("Failed chunks can be retried by running the same command.")
        raise SystemExit(1)

    print("ARCHIVE DOWNLOAD COMPLETED.")


if __name__ == "__main__":
    main()
