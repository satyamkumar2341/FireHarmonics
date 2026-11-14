from pathlib import Path
import hashlib
import json
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

SUPPORTED_PREFIXES = (
    "MODIS_NRT_",
    "VIIRS_NOAA20_NRT_",
    "VIIRS_NOAA21_NRT_",
)


def normalize_confidence(value, sensor):
    """Preserve native confidence meaning without cross-sensor scoring."""
    value = str(value).strip().lower()

    if sensor == "MODIS":
        return "numeric_native"

    if value == "h":
        return "high"
    if value == "n":
        return "nominal"
    if value == "l":
        return "low"

    return "unknown"



def stable_observation_uid(row):
    """Create a deterministic fingerprint for a normalized sensor observation."""
    fields = (
        "sensor",
        "platform",
        "instrument",
        "observation_datetime_utc",
        "latitude",
        "longitude",
        "frp_mw",
        "brightness_native_kelvin",
        "confidence_native",
        "daynight",
        "scan",
        "track",
    )

    payload = {}

    for field in fields:
        value = row[field]

        if pd.isna(value):
            payload[field] = None
        elif field == "observation_datetime_utc":
            payload[field] = value.isoformat()
        elif field in {
            "latitude", "longitude", "frp_mw",
            "brightness_native_kelvin", "scan", "track"
        }:
            payload[field] = format(float(value), ".12g")
        else:
            payload[field] = str(value).strip()

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":")
    )

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"FHUID-{digest[:20]}"

def normalize_file(file_path):
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip().str.lower()

    source = file_path.name.split("_20", 1)[0]

    if source == "MODIS_NRT":
        sensor = "MODIS"
        brightness_column = "brightness"
        brightness_band = "MODIS brightness"
        required = [
            "latitude", "longitude", "acq_date",
            "acq_time", "satellite", "instrument",
            "confidence", "frp", brightness_column, "daynight"
        ]
    elif source in ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"):
        sensor = "VIIRS"
        platform = (
            "NOAA-20" if source == "VIIRS_NOAA20_NRT"
            else "NOAA-21"
        )
        brightness_column = "bright_ti4"
        brightness_band = "VIIRS I4"
        required = [
            "latitude", "longitude", "acq_date",
            "acq_time", "instrument", "confidence",
            "frp", brightness_column, "daynight"
        ]
    else:
        raise ValueError(f"Unsupported file: {file_path.name}")

    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(
            f"{file_path.name} missing columns: {sorted(missing)}"
        )

    result = pd.DataFrame()

    result["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    result["acq_date"] = pd.to_datetime(
        df["acq_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    time_values = (
        df["acq_time"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(4)
    )

    result["acq_time_utc"] = time_values.str[:2] + ":" + time_values.str[2:4]

    result["observation_datetime_utc"] = pd.to_datetime(
        result["acq_date"] + " " + result["acq_time_utc"],
        format="%Y-%m-%d %H:%M",
        errors="coerce",
        utc=True
    )

    result["sensor"] = sensor
    result["platform"] = (
        df["satellite"].astype(str)
        if sensor == "MODIS"
        else platform
    )
    result["instrument"] = df["instrument"].astype(str)

    result["confidence_native"] = df["confidence"].astype(str)
    result["confidence_scheme"] = result["confidence_native"].apply(
        lambda value: normalize_confidence(value, sensor)
    )

    result["frp_mw"] = pd.to_numeric(df["frp"], errors="coerce")
    result["brightness_native_kelvin"] = pd.to_numeric(
        df[brightness_column], errors="coerce"
    )
    result["brightness_band"] = brightness_band

    result["daynight"] = df["daynight"].astype(str).str.upper()
    result["scan"] = pd.to_numeric(df["scan"], errors="coerce")
    result["track"] = pd.to_numeric(df["track"], errors="coerce")

    result["source_file"] = file_path.name
    result["region"] = "Punjab-Haryana"

    result = result.dropna(
        subset=[
            "latitude", "longitude", "acq_date",
            "observation_datetime_utc", "frp_mw"
        ]
    )

    result["observation_uid"] = result.apply(
        stable_observation_uid,
        axis=1
    )

    return result


def build_harmonized_dataset(
    raw_dir=None,
    output_dir=None,
    previous_dataset_path=None,
):
    raw_directory = Path(raw_dir) if raw_dir is not None else RAW_DIR
    output_directory = (
        Path(output_dir) if output_dir is not None else OUTPUT_DIR
    )

    files = sorted(
        file for file in raw_directory.glob("*.csv")
        if file.name.startswith(SUPPORTED_PREFIXES)
    )

    if not files:
        raise FileNotFoundError("No supported raw sensor CSV files found.")

    frames = [normalize_file(file) for file in files]
    combined = pd.concat(frames, ignore_index=True)

    # Prefer the earliest snapshot when the same stable UID appears more
    # than once across overlapping FIRMS downloads.
    combined = combined.sort_values(
        ["source_file", "observation_datetime_utc", "sensor", "platform"]
    )
    combined = combined.drop_duplicates(
        subset=["observation_uid"],
        keep="first"
    )

    combined = combined.sort_values(
        ["observation_datetime_utc", "sensor", "platform"]
    ).reset_index(drop=True)

    output_directory.mkdir(parents=True, exist_ok=True)
    output_file = output_directory / "harmonized_observations.csv"

    previous_file = (
        Path(previous_dataset_path)
        if previous_dataset_path is not None
        else output_file
    )

    # Preserve IDs from the previously published dataset.
    existing_ids = {}
    next_id = 1

    if previous_file.exists():
        previous = pd.read_csv(
            previous_file,
            usecols=["observation_id", "observation_uid"],
            dtype=str
        )

        if previous["observation_uid"].duplicated().any():
            raise ValueError(
                "Existing dataset contains duplicate UIDs; refusing to "
                "change legacy observation IDs."
            )

        if previous["observation_id"].duplicated().any():
            raise ValueError(
                "Existing dataset contains duplicate observation IDs."
            )

        id_numbers = previous["observation_id"].str.extract(
            r"^FH-(\d+)$",
            expand=False
        )

        if id_numbers.isna().any():
            raise ValueError(
                "Existing dataset contains invalid observation IDs."
            )

        existing_ids = dict(zip(
            previous["observation_uid"],
            previous["observation_id"]
        ))

        next_id = int(id_numbers.astype(int).max()) + 1

    combined.insert(
        0,
        "observation_id",
        combined["observation_uid"].map(existing_ids).astype(object)
    )

    new_rows = combined["observation_id"].isna()

    for index in combined.index[new_rows]:
        combined.at[index, "observation_id"] = f"FH-{next_id:07d}"
        next_id += 1
    combined.to_csv(output_file, index=False)

    print("\nHARMONIZATION SUCCESSFUL")
    print("Input files:", len(files))
    print("Total observations:", len(combined))
    print("Output:", output_file)

    print("\nObservations by sensor and platform:")
    print(
        combined.groupby(["sensor", "platform"])
        .size()
        .to_string()
    )

    print("\nDate coverage:")
    date_summary = (
        combined.assign(
            acq_date=combined["acq_date"].astype("object")
        )
        .groupby("sensor")["acq_date"]
        .agg(["min", "max", "count"])
    )
    print(date_summary.to_string())

    print("\nMissing values in harmonized dataset:")
    print(combined.isna().sum().to_string())

    print("\nFirst five records:")
    print(combined.head().to_string(index=False))

    return combined


if __name__ == "__main__":
    build_harmonized_dataset()
