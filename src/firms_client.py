import os
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Approximate bounding box covering Punjab and Haryana.
PUNJAB_HARYANA_BBOX = "73.5,27.5,77.8,32.5"

SUPPORTED_SOURCES = {
    "MODIS_NRT",
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
}

REQUIRED_COLUMNS = {
    "latitude",
    "longitude",
    "acq_date",
}


def get_api_key():
    """Read the NASA FIRMS MAP_KEY from the local .env file."""
    api_key = os.getenv("FIRMS_MAP_KEY")

    if not api_key:
        raise RuntimeError(
            "FIRMS_MAP_KEY missing. Add it to your local .env file."
        )

    return api_key.strip()


def fetch_area_data(
    source="VIIRS_SNPP_NRT",
    bbox=PUNJAB_HARYANA_BBOX,
    day_range=3,
):
    """
    Fetch recent NASA FIRMS observations for a geographic bounding box.

    NASA Area API supports a day range from 1 to 5 days.
    """

    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"Unsupported FIRMS source: {source}")

    if not 1 <= day_range <= 5:
        raise ValueError("day_range must be between 1 and 5.")

    coordinates = bbox.split(",")

    if len(coordinates) != 4:
        raise ValueError("bbox must contain west,south,east,north.")

    try:
        west, south, east, north = map(float, coordinates)
    except ValueError as exc:
        raise ValueError("Bounding box coordinates must be numeric.") from exc

    if not (
        -180 <= west < east <= 180
        and -90 <= south < north <= 90
    ):
        raise ValueError("Invalid geographic bounding box.")

    api_key = quote(get_api_key(), safe="")
    area = ",".join(coordinates)

    url = (
        f"{BASE_URL}/{api_key}/"
        f"{source}/{area}/{day_range}"
    )

    try:
        response = requests.get(url, timeout=60)

        if response.status_code == 400:
            raise RuntimeError(
                "NASA FIRMS rejected the request. Check MAP_KEY and parameters."
            )

        if response.status_code == 401:
            raise RuntimeError(
                "NASA FIRMS authorization failed. Verify your MAP_KEY."
            )

        if response.status_code == 429:
            raise RuntimeError(
                "NASA FIRMS rate limit reached. Try again later."
            )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not connect to NASA FIRMS: {exc}"
        ) from exc

    try:
        df = pd.read_csv(StringIO(response.text))
    except Exception as exc:
        raise RuntimeError(
            "NASA FIRMS returned data that could not be read as CSV."
        ) from exc

    if df.empty:
        return df

    df.columns = df.columns.str.strip().str.lower()

    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(
            f"NASA response is missing required columns: {sorted(missing)}"
        )

    for column in ("latitude", "longitude"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=["latitude", "longitude", "acq_date"])

    df = df[
        df["latitude"].between(south, north)
        & df["longitude"].between(west, east)
    ].copy()

    df["source_requested"] = source
    df["region"] = "Punjab-Haryana"

    return df.reset_index(drop=True)


def save_raw_data(df, source):
    """Save original sensor observations in the project's raw data folder."""

    if df.empty:
        return None

    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    output_file = output_dir / f"{source}_{timestamp}.csv"

    df.to_csv(output_file, index=False)

    return output_file