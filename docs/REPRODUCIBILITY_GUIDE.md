# FireHarmonics Reproducibility Guide

Run from the project root with the virtual environment activated.

## Tests
`python -m pytest -q`

## Dashboard
`python -m streamlit run app.py`

## Data
- NASA archive: `data/raw/historical_sp_archive/`
- Harmonized data: `data/staging/problem1_nasa_20261115_193025/processed/`
- Analysis scripts: `scripts/`
- Source modules: `src/`
- Generated audit outputs: `data/staging/`

Satellite detections are observations, not confirmed fire events. DORA matches are candidates. HLS metadata availability does not prove pixel-level validation.
