# FireHarmonics
NASA Space Apps Challenge 2026

An independent project exploring harmonization of MODIS and VIIRS active-fire observations using NASA FIRMS data.

## NASA Data Sources

- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/
- NASA Earthdata: https://www.earthdata.nasa.gov/
- MODIS: https://modis.gsfc.nasa.gov/
- VIIRS: https://viirsland.gsfc.nasa.gov/
- FIRMS API: https://firms.modaps.eosdis.nasa.gov/api/area/csv

## Current Dataset

File: `data/processed/harmonized_observations.csv`

| Platform | Observations |
|---|---:|
| NOAA-20 | 2,448 |
| NOAA-21 | 2,206 |
| Aqua | 1,084 |
| Terra | 10 |
| **Total** | **5,748** |

The dataset covers November 7–14, 2026. No observations are present for November 12–13 in the current snapshot. These gaps represent missing observations in this dataset, not evidence of zero fire activity.

The latest NASA FIRMS retrieval added 217 observations: MODIS 48, NOAA-20 123, and NOAA-21 46.

Raw source CSVs and retrieval manifests are stored in `data/raw/`. The November 14 retrieval snapshots have corresponding manifests, and all 12 referenced local file hashes were verified against their manifests. The November 11 source CSVs currently have no corresponding manifests in the repository; therefore, manifest-level provenance verification for those files is incomplete.

## DORA Analysis

DORA (Detection Observation Relationship Analysis) explores spatial and temporal candidate relationships between MODIS Aqua and VIIRS NOAA-20/NOAA-21.

Baseline exploratory criteria: 2 km spatial radius, 240 minutes, same acquisition date, and same day/night category.

- Candidate pairs: 203
- Unique MODIS observations: 140
- Unique VIIRS observations: 165
- MODIS observations with multiple candidates: 40
- VIIRS observations with multiple candidates: 36

### Threshold sensitivity

| Radius | 60 min | 120 min | 240 min |
|---|---:|---:|---:|
| 1 km | 0 | 20 | 61 |
| 2 km | 0 | 42 | 203 |
| 5 km | 0 | 154 | 1,087 |

These are exploratory candidate relationships, not confirmed fire-event matches or accuracy measurements. Candidate rankings are investigation priorities, not match probabilities.

## Cross-Sensor FRP Comparability

Exploratory comparison of MODIS Aqua with candidate VIIRS NOAA-20 and NOAA-21 observations, using the 5 km DORA candidate file.

### Raw platform observations

| Platform | Observations | Median FRP (MW) | Mean FRP (MW) | 90th percentile FRP (MW) |
|---|---:|---:|---:|---:|
| MODIS Aqua | 1,084 | 14.93 | 21.07 | 40.52 |
| MODIS Terra | 10 | 8.04 | 9.75 | 13.575 |
| VIIRS NOAA-20 | 2,448 | 4.18 | 5.90 | 11.59 |
| VIIRS NOAA-21 | 2,206 | 4.55 | 6.09 | 11.46 |

### One-to-one candidate comparison

FRP ratio = VIIRS FRP / MODIS FRP.

| Platform | Candidate pairs | One-to-one pairs | Median FRP ratio | Median FRP difference | Median distance | Median time gap |
|---|---:|---:|---:|---:|---:|---:|
| NOAA-20 | 80 | 52 | 0.2718 | -72.82% | 1.405 km | 172 min |
| NOAA-21 | 123 | 80 | 0.4303 | -56.97% | 1.227 km | 137 min |

### Date-cluster bootstrap

| Platform | Pairs | Unique dates | Median daily ratio | 95% bootstrap interval |
|---|---:|---:|---:|---:|
| NOAA-20 | 52 | 4 | 0.2861 | 0.2169-0.3003 |
| NOAA-21 | 80 | 4 | 0.2841 | 0.1115-0.5588 |

These estimates use only four unique dates per platform and are limited exploratory evidence.

### Interpretation and limitations

- Ratios below 1 indicate lower VIIRS FRP within selected candidate associations; they do not establish general sensor bias.
- Candidate associations are not verified same-fire matches or independent ground truth.
- These results are not calibration factors, accuracy estimates, or justification for calibration corrections.
- MODIS numeric confidence and VIIRS low/nominal/high categories retain their native meanings and are not interchangeable.
- Platform distributions are affected by coverage, acquisition timing, sampling, and detected-observation characteristics.
- The small number of date clusters limits the strength and generalizability of bootstrap estimates.
- MODIS Terra has only 10 observations in this production snapshot.

Reproduce the analysis:

    python scripts/run_sensor_comparability.py --observations data/processed/harmonized_observations.csv --candidates data/processed/dora_spatial_candidates_5km.csv --output-dir data/processed
## Dashboard

The Streamlit dashboard includes:

- Project overview and dataset summary
- DORA candidate and ambiguity analysis
- Data explorer and filters
- Methodology and limitations
- Sensor explorer, maps, charts, and CSV exports

The dashboard reads local processed files. It does not automatically refresh from NASA FIRMS.

## Project Structure

- `app.py` - Streamlit dashboard
- `src/firms_client.py` - NASA FIRMS data client
- `src/harmonizer.py` - Observation harmonization
- `src/dora.py` - Candidate relationship analysis
- `src/ambiguity.py` - Ambiguity analysis
- `scripts/download_nasa_firms.py` - NASA data retrieval
- `data/raw/` - Source observations and retrieval manifests
- `data/processed/` - Processed datasets and analysis outputs
- `tests/` - Automated tests

## Setup

Python 3.10 or newer is recommended.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root with your own NASA FIRMS key:

```text
FIRMS_MAP_KEY=YOUR_KEY_HERE
```

Never publish your actual API key or commit `.env`.

## Run the Pipeline

```powershell
$env:PYTHONPATH = (Get-Location).Path
python .\scripts\download_nasa_firms.py
python -m src.harmonizer
python -m src.dora
python -m src.ambiguity
```

Launch the dashboard:

```powershell
python -m streamlit run app.py
```

Run automated tests:

```powershell
python -m pytest -q
```

Latest verified test result on November 15, 2026: **51 passed**.

## Scientific Limitations

- Near-real-time satellite detections are preliminary observations, not independently confirmed fire incidents.
- No independent ground-truth dataset is used to establish matching accuracy.
- Spatial and temporal thresholds are exploratory and influence candidate counts.
- An unmatched observation means no candidate was found under the selected criteria; it does not prove that a sensor missed a fire.
- Multiple candidate relationships create ambiguity; candidate rank is not match probability.
- FRP and confidence values from different sensors are not automatically comparable.
- Terra has limited representation in the current dataset.
- The current workflow does not match observations across UTC acquisition-date boundaries.
- Missing observations in the dataset must not be interpreted as evidence of no fire activity.

## AI Assistance Disclosure

AI tools assisted with coding support, debugging, documentation, and explanations. The project team is responsible for implementation, testing, data interpretation, and submitted claims.

## Attribution

Satellite observations are sourced from NASA FIRMS. Consult NASA FIRMS and NASA Earthdata documentation for data-use guidance and product-specific terms.

FireHarmonics is an independent project and does not imply NASA approval or endorsement.

## Independent Validation and Reproducibility

The DORA outputs were subjected to independent computational consistency checks against the harmonized observation records.

### Candidate-pair validation

- All 203 candidate pairs were checked for links to their source MODIS and VIIRS observations using observation UIDs.
- MODIS observations were from Aqua; VIIRS observations were from NOAA-20 or NOAA-21.
- Candidate pairs were checked for matching acquisition dates and day/night categories.
- All 203 pairs satisfied the baseline spatial threshold (2 km) and temporal threshold (240 minutes).
- No duplicate UID pairs were found.
- Haversine distances were independently recomputed from source coordinates. The maximum absolute difference from the saved distances was approximately 0.00000276 km.
- Temporal gaps were independently reproduced from UTC timestamps.

### Threshold sensitivity validation

The 27 reported values across nine combinations of spatial radii (1, 2, and 5 km) and temporal windows (60, 120, and 240 minutes) were independently reproduced:

- Candidate-pair counts
- Unique MODIS observation counts
- Unique VIIRS observation counts

### Ambiguity validation

The independently recomputed pair classification matched the saved ambiguity report:

- Ambiguous for MODIS: 69 pairs
- Unique on both sides: 60 pairs
- Ambiguous for VIIRS: 40 pairs
- Ambiguous on both sides: 34 pairs

The analysis also identified 40 MODIS observations and 36 VIIRS observations with multiple candidates.

### Scope of validation

These checks establish computational consistency and reproducibility against the current harmonized dataset. They do not establish ground-truth fire-event matches, sensor detection accuracy, or causal relationships. Candidate rankings are investigation priorities, not match probabilities.
