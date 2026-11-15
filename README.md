# FireHarmonics

### NASA Space Apps Challenge 2026
**Challenge: Harmonization of MODIS and VIIRS Hot Spots**

FireHarmonics is an independent research prototype exploring the harmonization, comparison, and analysis of active-fire observations from NASA FIRMS MODIS and VIIRS sensors.

The project combines multi-year satellite observations, reproducible spatial-temporal analysis, sensor comparability research, anomaly screening, contextual satellite imagery discovery, and an interactive Streamlit research interface.

Satellite detections are observations, not confirmed fire incidents.

## Current Research Dataset

The latest locally audited harmonized dataset contains:

| Metric | Result |
|---|---:|
| Observation records | 769,672 |
| Unique observation IDs | 769,672 |
| Platforms | 5 |
| Sensors | MODIS and VIIRS |
| Coverage | 2023-03-01 to 2026-07-31 |

### Platform distribution

| Platform | Observations |
|---|---:|
| NOAA-20 | 249,054 |
| NOAA-21 | 240,730 |
| Suomi-NPP | 238,845 |
| Aqua | 32,701 |
| Terra | 8,342 |

**Data availability:** Raw NASA archive files and generated research datasets are maintained locally and are not included in this GitHub repository. The figures above refer to the locally audited dataset.

## Research and Implementation

### P1 — NASA archive integration and harmonization
- Integrated an archived NASA FIRMS dataset covering March 2023 to July 2026.
- Archive manifest: 1,000 chunks; 991 downloaded and 9 successful empty queries.
- Harmonized output: 769,672 records with unique observation identifiers.
- Raw source data and integration audit are retained in local staging.

### P2 — Multi-year activity analysis
- Generated daily, weekly, monthly, quarterly, yearly, seasonal, platform, and sensor summaries.
- Built day/night, hourly UTC, and approximate 5 km spatial-grid analyses.
- Calendar and aggregation totals reconcile to 769,672 observations.
- Missing observation dates are not interpreted as zero-fire days.

### P3 — DORA candidate correspondence analysis
- Implemented optimized date/day-night indexed spatial candidate generation.
- Generated 311,918 spatial candidates in the 5 km candidate-search stage.
- Baseline 2 km / 240-minute analysis produced 106,203 candidate pairs.
- 718,804 observations were in the audited comparison scope; 50,868 were excluded under the defined scope rules.
- Candidate pairs are not confirmed matches to the same physical fire.

### P4 — Sensor comparability
- Generated platform-level and native-confidence summaries.
- Added one-to-one baseline and bootstrap-based exploratory comparisons.
- Confidence schemes differ by sensor and are not directly interchangeable.
- FRP comparisons do not establish calibration bias or sensor accuracy against ground truth.

### P5 — NASA HLS Landsat contextual inventory
- Queried NASA HLSL30 v2.0 through NASA CMR-STAC for 36 stratified candidate locations.
- 34 locations returned HLS scenes; 52 scene items were identified.
- Reviewed metadata for 30 priority scenes, including Fmask and RGB asset availability.
- No imagery download or pixel-level validation was completed.
- HLS surface reflectance is contextual evidence, not thermal active-fire ground truth.

### P6 — Historical anomaly screening
- Generated 2,610 anomaly-review alerts from daily platform/grid activity.
- Uses a 28-day historical lookback and requires at least 7 prior active days.
- Robust-score thresholds: low >=2, medium >=3, high >=5.
- Alerts indicate unusual satellite-observation activity, not confirmed fire outbreaks.

### P7 — Critical activity windows
- Compared complete calendar years 2024 and 2025.
- Identified May and October-November as recurring high-activity observation windows.
- These are satellite-observation patterns, not validated fire seasons or forecasts.
- Observation coverage and sampling affect measured activity.

### P8 — Interactive Research Explorer
- Added a Research Explorer to the Streamlit application.
- Integrates harmonized observations, DORA candidates, sensor comparisons, anomaly alerts, critical activity windows, and HLS inventory.
- Presents research caveats alongside the analysis.

### P9 — Stakeholder review workflow
- Generated a retrospective review queue containing 2,610 anomaly records.
- Includes analyst review priorities and daily contextual information.
- This is not a live emergency dispatch or response system.

### P10 — Final release audit
- Final release audit status: `AUDIT_PASS_WITH_LIMITATIONS`.
- Checked key research artifacts, integration markers, and Python syntax.
- Python test suite: **56 passed**.
- This is a project release audit, not independent scientific validation.

## Project Structure

```text
FireHarmonics/
|-- app.py
|-- src/
|-- scripts/
|-- tests/
|-- docs/
|-- data/
|   |-- raw/
|   `-- staging/
|-- requirements.txt
|-- README.md
`-- .gitignore
```

Large raw and generated datasets are kept outside the tracked repository where appropriate.

## Run Locally

### Requirements
- Python 3.10 or later
- Dependencies listed in `requirements.txt`
- NASA FIRMS access key for data-download workflows

### Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a local `.env` file for your FIRMS key when running download workflows. Never commit API keys or credentials.

### Launch the dashboard

```powershell
python -m streamlit run app.py
```

The dashboard expects the required locally generated datasets to be available in the expected project data paths.

### Run tests

```powershell
python -m pytest -q
```

Latest recorded result: **56 passed** (15 November 2026).

## Scientific Limitations

- Active-fire detections are satellite observations, not verified fire incidents.
- DORA candidate pairs do not prove that two sensors observed the same physical fire.
- Sensor confidence categories are not directly interchangeable.
- FRP comparisons do not establish calibration bias.
- Observation counts depend on satellite coverage, acquisition timing, and sampling.
- Missing dates or records must not be interpreted as zero fire activity.
- HLS L30 inventory does not constitute thermal ground-truth validation; pixel-level validation remains incomplete.
- Anomaly alerts are screening signals, not confirmed outbreaks.
- Critical activity windows are descriptive observation patterns, not causal risk forecasts.
- The stakeholder review queue is retrospective and does not provide live emergency response.

## NASA Data Sources and Attribution

This project uses NASA FIRMS active-fire data and NASA Earthdata resources. HLS L30 scene discovery uses NASA CMR-STAC and the HLS L30 v2.0 collection.

- [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)
- [NASA Earthdata](https://www.earthdata.nasa.gov/)
- [NASA HLS Data Access](https://hls.gsfc.nasa.gov/data-access-and-tools/)
- [NASA CMR STAC](https://cmr.earthdata.nasa.gov/stac/LPCLOUD/search)

FireHarmonics is an independent project and is not endorsed by or officially affiliated with NASA.

## Responsible Use

FireHarmonics is a research and decision-support prototype. Its outputs should be interpreted with the stated data, methodological, and validation limitations. They should not be used as the sole basis for emergency decisions.
