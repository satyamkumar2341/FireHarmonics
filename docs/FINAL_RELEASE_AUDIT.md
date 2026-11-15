# FireHarmonics Final Release Audit

**Status:** `AUDIT_PASS_WITH_LIMITATIONS`
**Checks passed:** 16/16

| Check | Status | Detail |
|---|---|---|
| NASA archive manifest | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\raw\historical_sp_archive\20230301_20260731\historical_archive_manifest.json |
| Harmonized observations | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem1_nasa_20261115_193025\processed\harmonized_observations.csv |
| daily_activity_calendar.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem1_nasa_20261115_193025\problem2_activity_calendar\daily_activity_calendar.csv |
| dora_candidate_pairs.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem1_nasa_20261115_193025\problem3_dora_optimized_20261115_195742\dora_candidate_pairs.csv |
| sensor_raw_platform_summary.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem1_nasa_20261115_193025\problem4_sensor_comparability_20261115_195934\sensor_raw_platform_summary.csv |
| all_scenes_ranked.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem5_nasa_hls_l30_inventory_20261115_200405\scene_suitability_review\all_scenes_ranked.csv |
| best_scene_per_location.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem5_nasa_hls_l30_inventory_20261115_200405\scene_suitability_review\best_scene_per_location.csv |
| anomaly_alerts.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem6_historical_anomaly_20261115_202004\anomaly_alerts.csv |
| problem6_validation_audit.json | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem6_historical_anomaly_20261115_202004\problem6_validation_audit.json |
| critical_burning_windows.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem7_critical_burning_windows_20261115\critical_burning_windows.csv |
| problem7_analysis_audit.json | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem7_critical_burning_windows_20261115\problem7_analysis_audit.json |
| stakeholder_review_queue.csv | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem9_stakeholder_workflow_20261115_150914\stakeholder_review_queue.csv |
| problem9_workflow_audit.json | PASS | C:\Users\yk719\OneDrive\FireHarmonics\data\staging\problem9_stakeholder_workflow_20261115_150914\problem9_workflow_audit.json |
| Research Explorer integration | PASS |  |
| Python syntax | PASS | 19 files valid |
| Pytest | PASS | ........................................................                 [100%]
56 passed in 5.25s
 |

## Scientific and technical limitations

- HLS L30 scene and asset metadata inventoried; pixel-level raster QA remains pending.
- HLS surface reflectance is not thermal active-fire ground truth.
- MODIS/VIIRS detections are satellite observations, not confirmed fire events.
- DORA outputs are candidate correspondences, not confirmed same-fire matches.
- Anomaly alerts describe unusual observation volume, not confirmed outbreaks.
- Critical windows describe observation activity, not causal fire-risk forecasts.
- Missing observations do not prove absence of fire.