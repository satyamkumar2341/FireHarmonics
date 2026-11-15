from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.sensor_comparability import analyze_sensor_comparability


def main():
    parser = ArgumentParser(
        description="Generate reproducible FireHarmonics sensor comparability outputs."
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=ROOT / "data" / "processed" / "harmonized_observations.csv",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "data" / "processed" / "dora_spatial_candidates_5km.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Explicit output directory; must be chosen deliberately.",
    )
    parser.add_argument("--bootstrap-replicates", type=int, default=3000)
    args = parser.parse_args()

    for path in (args.observations, args.candidates):
        if not path.is_file():
            raise SystemExit(f"Required input not found: {path}")

    observations = pd.read_csv(args.observations)
    candidates = pd.read_csv(args.candidates)

    print(f"Observations: {len(observations):,}")
    print(f"Spatial candidates: {len(candidates):,}")
    print(f"Output directory: {args.output_dir.resolve()}")

    outputs = analyze_sensor_comparability(
        observations,
        candidates,
        output_dir=args.output_dir,
        bootstrap_replicates=args.bootstrap_replicates,
    )

    expected = [
        "sensor_raw_platform_summary.csv",
        "sensor_native_confidence_counts.csv",
        "sensor_one_to_one_baseline.csv",
        "sensor_date_cluster_bootstrap.csv",
        "sensor_threshold_bootstrap.csv",
    ]

    print("\nGenerated outputs:")
    for name in expected:
        path = args.output_dir / name
        if not path.is_file():
            raise SystemExit(f"Expected output missing: {path}")
        check = pd.read_csv(path)
        print(f"{name}: {len(check):,} rows")

    print("\nSensor comparability analysis completed successfully.")


if __name__ == "__main__":
    main()
