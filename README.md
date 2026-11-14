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

File: data/processed/harmonized_observations.csv

| Platform | Observations |
|---|---:|
| NOAA-20 | 2,448 |
| NOAA-21 | 2,206 |
| Aqua | 1,084 |
| Terra | 10 |
| **Total** | **5,748** |

Latest NASA FIRMS retrieval added 217 observations: MODIS 48, NOAA-20 123, NOAA-21 46. Raw files and retrieval manifests are stored in data/raw/.

## DORA Analysis

DORA (Detection Observation Relationship Analysis) explores spatial and temporal candidate relationships between MODIS Aqua and VIIRS NOAA-20/NOAA-21.

Baseline exploratory criteria: 2 km spatial radius, 240 minutes, same acquisition date and same day/night category.

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

These are exploratory candidate relationships, not confirmed matches or accuracy measurements.


## Dashboard

The Streamlit dashboard includes:
- Project overview and dataset summary
- DORA candidate and ambiguity analysis
- Data explorer and filters
- Methodology and limitations
- Sensor explorer, maps, charts and CSV exports

## Project Structure

- app.py - Streamlit dashboard
- src/firms_client.py - NASA FIRMS data client
- src/harmonizer.py - observation harmonization
- src/dora.py - candidate relationship analysis
- src/ambiguity.py - ambiguity analysis
- scripts/download_nasa_firms.py - NASA data retrieval
- data/raw/ - source observations and manifests
- data/processed/ - processed datasets and analysis outputs
- tests/ - automated tests

## Setup

Python 3.10 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
```

Create a .env file in the project root with your own NASA FIRMS key:

```text
FIRMS_MAP_KEY=YOUR_KEY_HERE
```

Never publish your actual API key or commit .env.

## Run the Pipeline

```powershell
$env:PYTHONPATH = (Get-Location).Path
python .\scripts\download_nasa_firms.py
python -m src.harmonizer
python -m src.dora
python -m src.ambiguity
```

Launch dashboard:

```powershell
python -m streamlit run app.py
```

Run tests:

```powershell
python -m pytest -q
```

Latest recorded test result: 22 passed.


## Scientific Limitations

- Near-real-time satellite detections are preliminary observations, not independently confirmed fire incidents.
- No independent ground-truth dataset is used to establish matching accuracy.
- Spatial and temporal thresholds are exploratory and influence candidate counts.
- An unmatched observation means no candidate was found under the selected criteria; it does not prove that a sensor missed a fire.
- Multiple candidate relationships create ambiguity; candidate rank is not match probability.
- FRP and confidence values from different sensors are not automatically comparable.
- Terra has limited representation in the current dataset.
- The current workflow does not match observations across UTC acquisition-date boundaries.

## AI Assistance Disclosure

AI tools assisted with coding support, debugging, documentation, and explanations. The project team is responsible for implementation, testing, data interpretation, and submitted claims.

## Attribution

Satellite observations are sourced from NASA FIRMS. Consult NASA FIRMS and NASA Earthdata documentation for data-use guidance and product-specific terms.

FireHarmonics is an independent project and does not imply NASA approval or endorsement.

## Independent Validation and Reproducibility

The DORA outputs were independently checked against the harmonized observation records.

### Candidate-pair validation
- All 203 candidate pairs successfully linked to their source MODIS and VIIRS observations using observation UIDs.
- All MODIS observations were from Aqua; VIIRS observations were from NOAA-20 or NOAA-21.
- All candidate pairs had matching acquisition dates and day/night categories.
- All 203 pairs satisfied the baseline spatial threshold (2 km) and temporal threshold (240 minutes).
- No duplicate UID pairs were found.
- Haversine distances were independently recomputed from source coordinates. The maximum absolute difference from the saved distances was approximately 0.00000276 km.
- All 203 temporal gaps were independently reproduced exactly from UTC timestamps.

### Threshold sensitivity validation
All 27 reported values across nine combinations of spatial radii (1, 2, and 5 km) and temporal windows (60, 120, and 240 minutes) were independently reproduced:
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
