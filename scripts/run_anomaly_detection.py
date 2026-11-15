from __future__ import annotations
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.anomaly_detection import run_anomaly_detection

def main():
    parser = argparse.ArgumentParser(description="Run FireHarmonics explainable anomaly detection.")
    parser.add_argument("--input", default="data/processed/historical_20230301_20230531/harmonized_observations.csv")
    parser.add_argument("--output-dir", default="data/processed/anomaly_20230301_20230531")
    parser.add_argument("--grid-km", type=float, default=5.0)
    parser.add_argument("--baseline-days", type=int, default=28)
    parser.add_argument("--min-prior-active-days", type=int, default=7)
    args = parser.parse_args()
    result = run_anomaly_detection(args.input, args.output_dir, grid_km=args.grid_km,
                                   baseline_days=args.baseline_days,
                                   min_prior_active_days=args.min_prior_active_days)
    print("ANOMALY DETECTION COMPLETE")
    for key, value in result.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()

