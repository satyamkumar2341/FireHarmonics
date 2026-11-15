from pathlib import Path
from datetime import datetime
import re
import shutil
import sys
import py_compile

root = Path.cwd()
app = root / "app.py"
source = app.read_text(encoding="utf-8")

# Safety checks: never patch an unknown or already-patched app.
if "tab_research" in source or "FIREHARMONICS_PROBLEM8_RESEARCH_EXPLORER" in source:
    raise SystemExit("Research Explorer already exists. No changes made.")

tab_pattern = re.compile(
    r"(tab_overview\s*,\s*tab_dora\s*,\s*tab_data\s*,\s*tab_method\s*,\s*tab_sensor\s*,\s*tab_anomaly)\s*=\s*st\.tabs\("
)
matches = list(tab_pattern.finditer(source))
if len(matches) != 1:
    raise SystemExit(f"Expected exactly one six-tab declaration; found {len(matches)}.")

label = '        "Anomaly Detection",'
if source.count(label) != 1:
    raise SystemExit("Could not uniquely identify the Anomaly Detection tab label.")

footer = 'st.caption("FireHarmonics'
footer_pos = source.rfind(footer)
if footer_pos < 0:
    raise SystemExit("Dashboard footer marker not found. No changes made.")

# New tab variable and label.
source = tab_pattern.sub(
    r"\1, tab_research = st.tabs(",
    source,
    count=1,
)
source = source.replace(
    label,
    label + '\n        "Research Explorer",',
    1,
)

research_code = r'''

# FIREHARMONICS_PROBLEM8_RESEARCH_EXPLORER
with tab_research:
    st.subheader("NASA Historical Research Explorer")
    st.caption(
        "Interactive exploration of the verified local project outputs. "
        "The historical archive is not a live satellite feed."
    )

    STAGING = ROOT / "data" / "staging"
    P1 = STAGING / "problem1_nasa_20261115_193025"
    P2 = P1 / "problem2_activity_calendar"
    P5 = STAGING / "problem5_nasa_hls_l30_inventory_20261115_200405"
    P6 = STAGING / "problem6_historical_anomaly_20261115_202004"
    P7 = STAGING / "problem7_critical_burning_windows_20261115"

    @st.cache_data(show_spinner="Loading project research data...")
    def _fh_read_csv(path_string):
        return pd.read_csv(path_string, low_memory=False)

    def _fh_optional_csv(path):
        if path is None or not Path(path).exists():
            return pd.DataFrame()
        try:
            return _fh_read_csv(str(path))
        except Exception as exc:
            st.warning(f"Could not load {Path(path).name}: {exc}")
            return pd.DataFrame()

    def _fh_first_match(pattern):
        found = sorted(P1.glob(pattern))
        return found[0] if found else None

    observations_path = P1 / "processed" / "harmonized_observations.csv"
    observations = _fh_optional_csv(observations_path)

    if observations.empty:
        st.error("Canonical harmonized observation dataset is missing or empty.")
    else:
        required = {"acq_date", "platform", "sensor", "latitude", "longitude"}
        missing = required.difference(observations.columns)
        if missing:
            st.error(f"Required observation columns missing: {sorted(missing)}")
        else:
            observations = observations.copy()
            observations["acq_date"] = observations["acq_date"].astype(str)

            st.markdown("#### Observation filters")
            f1, f2, f3 = st.columns(3)

            platforms = sorted(observations["platform"].dropna().astype(str).unique())
            sensors = sorted(observations["sensor"].dropna().astype(str).unique())

            selected_platforms = f1.multiselect(
                "Satellite platforms",
                platforms,
                default=platforms,
                key="p8_platforms",
            )
            selected_sensors = f2.multiselect(
                "Sensors",
                sensors,
                default=sensors,
                key="p8_sensors",
            )

            valid_dates = pd.to_datetime(
                observations["acq_date"], errors="coerce"
            ).dropna()
            min_date = valid_dates.min().date()
            max_date = valid_dates.max().date()

            date_selection = f3.date_input(
                "Acquisition date range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="p8_date_range",
            )

            filtered = observations[
                observations["platform"].astype(str).isin(selected_platforms)
                & observations["sensor"].astype(str).isin(selected_sensors)
            ].copy()

            if isinstance(date_selection, (tuple, list)) and len(date_selection) == 2:
                start_date, end_date = date_selection
                filtered_dates = pd.to_datetime(
                    filtered["acq_date"], errors="coerce"
                )
                filtered = filtered[
                    filtered_dates.between(
                        pd.Timestamp(start_date), pd.Timestamp(end_date)
                    )
                ]

            total = len(filtered)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Filtered observations", f"{total:,}")
            m2.metric("Platforms", f"{filtered['platform'].nunique():,}")
            m3.metric("Sensors", f"{filtered['sensor'].nunique():,}")
            m4.metric("Observation dates", f"{filtered['acq_date'].nunique():,}")

            if filtered.empty:
                st.info("No observations match the selected filters.")
            else:
                st.markdown("#### Temporal activity")
                daily = (
                    filtered.groupby("acq_date")
                    .size()
                    .rename("Observations")
                    .reset_index()
                    .sort_values("acq_date")
                )
                fig = px.line(
                    daily,
                    x="acq_date",
                    y="Observations",
                    title="Daily satellite observation volume",
                    labels={"acq_date": "Acquisition date"},
                )
                st.plotly_chart(fig, use_container_width=True)

                left, right = st.columns(2)
                with left:
                    platform_counts = (
                        filtered["platform"].value_counts()
                        .rename_axis("Platform")
                        .reset_index(name="Observations")
                    )
                    fig = px.bar(
                        platform_counts,
                        x="Platform",
                        y="Observations",
                        color="Platform",
                        title="Observations by platform",
                        text_auto=True,
                    )
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                with right:
                    sensor_counts = (
                        filtered["sensor"].value_counts()
                        .rename_axis("Sensor")
                        .reset_index(name="Observations")
                    )
                    fig = px.pie(
                        sensor_counts,
                        names="Sensor",
                        values="Observations",
                        title="Sensor observation share",
                        hole=0.45,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                if "frp_mw" in filtered.columns:
                    frp = filtered.copy()
                    frp["frp_mw"] = pd.to_numeric(frp["frp_mw"], errors="coerce")
                    frp = frp.dropna(subset=["frp_mw"])
                    if not frp.empty:
                        frp_summary = (
                            frp.groupby("sensor")["frp_mw"]
                            .agg(["count", "median", "mean"])
                            .reset_index()
                        )
                        st.markdown("#### Fire Radiative Power (FRP) observations")
                        st.dataframe(
                            frp_summary.rename(columns={
                                "sensor": "Sensor",
                                "count": "Observation count",
                                "median": "Median FRP (MW)",
                                "mean": "Mean FRP (MW)",
                            }),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.caption(
                            "FRP summaries are descriptive and are not sensor calibration "
                            "or direct measures of total fire energy."
                        )

                st.download_button(
                    "Download filtered observations",
                    filtered.to_csv(index=False).encode("utf-8"),
                    file_name="fireharmonics_filtered_observations.csv",
                    mime="text/csv",
                    key="p8_download_observations",
                )

    st.divider()
    st.markdown("#### DORA candidate relationships")
    dora_path = _fh_first_match("problem3_dora_*/dora_candidate_pairs.csv")
    dora = _fh_optional_csv(dora_path)

    if dora.empty:
        st.info("DORA candidate-pair output is unavailable.")
    else:
        st.caption(
            "These are spatial-temporal candidate correspondences, not confirmed "
            "matches of the same physical fire."
        )
        d1, d2, d3 = st.columns(3)
        d1.metric("Candidate pairs", f"{len(dora):,}")
        if "distance_km" in dora.columns:
            distance = pd.to_numeric(dora["distance_km"], errors="coerce").dropna()
            d2.metric("Median distance", f"{distance.median():.3f} km" if not distance.empty else "N/A")
            d3.metric("95th percentile", f"{distance.quantile(.95):.3f} km" if not distance.empty else "N/A")

            fig = px.histogram(
                dora,
                x="distance_km",
                nbins=45,
                title="Spatial separation of DORA candidate pairs",
                labels={"distance_km": "Distance (km)"},
            )
            st.plotly_chart(fig, use_container_width=True)

        display_cols = [
            c for c in [
                "date", "modis_platform", "viirs_platform",
                "distance_km", "time_gap_minutes",
                "modis_frp_mw", "viirs_frp_mw",
            ] if c in dora.columns
        ]
        if display_cols:
            st.dataframe(dora[display_cols].head(1000), use_container_width=True, hide_index=True)
        st.download_button(
            "Download DORA candidate pairs",
            dora.to_csv(index=False).encode("utf-8"),
            file_name="fireharmonics_dora_candidate_pairs.csv",
            mime="text/csv",
            key="p8_download_dora",
        )

    st.divider()
    st.markdown("#### Cross-platform comparison")
    comparison_path = _fh_first_match(
        "problem4_sensor_comparability_*/sensor_one_to_one_baseline.csv"
    )
    comparison = _fh_optional_csv(comparison_path)

    if comparison.empty:
        st.info("Sensor comparability output is unavailable.")
    else:
        st.dataframe(comparison, use_container_width=True, hide_index=True)
        if {"platform", "median_frp_ratio"}.issubset(comparison.columns):
            fig = px.bar(
                comparison,
                x="platform",
                y="median_frp_ratio",
                title="Median VIIRS-to-MODIS FRP ratio in one-to-one candidate pairs",
                labels={
                    "platform": "VIIRS platform",
                    "median_frp_ratio": "Median FRP ratio",
                },
            )
            st.plotly_chart(fig, use_container_width=True)
        st.warning(
            "Exploratory comparison only: confidence schemes differ across sensors, "
            "candidate pairs are not ground truth, and FRP ratios are not calibration "
            "bias estimates."
        )

    st.divider()
    st.markdown("#### Historical observation-volume anomalies")
    alerts = _fh_optional_csv(P6 / "anomaly_alerts.csv")
    anomaly_audit = {}
    audit_path = P6 / "anomaly_summary.json"
    if audit_path.exists():
        try:
            anomaly_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if alerts.empty:
        st.info("Historical anomaly alerts are unavailable.")
    else:
        severity_counts = (
            alerts["severity"].value_counts().to_dict()
            if "severity" in alerts.columns else {}
        )
        a, b, c = st.columns(3)
        a.metric("Alert records", f"{len(alerts):,}")
        b.metric("High", f"{severity_counts.get('high', 0):,}")
        c.metric("Medium", f"{severity_counts.get('medium', 0):,}")

        if "severity" in alerts.columns:
            sev = alerts["severity"].value_counts().rename_axis("Severity").reset_index(name="Alerts")
            fig = px.bar(sev, x="Severity", y="Alerts", title="Anomaly alert severity")
            st.plotly_chart(fig, use_container_width=True)

        if "platform" in alerts.columns:
            alert_platforms = ["All"] + sorted(alerts["platform"].dropna().astype(str).unique())
            chosen_alert_platform = st.selectbox(
                "Anomaly platform filter",
                alert_platforms,
                key="p8_anomaly_platform",
            )
            alert_view = alerts.copy()
            if chosen_alert_platform != "All":
                alert_view = alert_view[
                    alert_view["platform"].astype(str) == chosen_alert_platform
                ]
            st.dataframe(alert_view.head(1000), use_container_width=True, hide_index=True)
            st.download_button(
                "Download anomaly alerts",
                alert_view.to_csv(index=False).encode("utf-8"),
                file_name="fireharmonics_anomaly_alerts.csv",
                mime="text/csv",
                key="p8_download_alerts",
            )

        st.caption(
            "Alerts identify unusual satellite observation volume relative to a "
            "platform/grid historical baseline. They are not confirmed fire outbreaks."
        )

    st.divider()
    st.markdown("#### Critical observation-activity windows")
    critical = _fh_optional_csv(P7 / "critical_burning_windows.csv")
    critical_months = _fh_optional_csv(P7 / "critical_months.csv")

    if critical.empty:
        st.info("Critical-window analysis is unavailable.")
    else:
        st.dataframe(critical, use_container_width=True, hide_index=True)
        st.warning(
            "These are recurring high satellite-observation activity windows, "
            "not independently verified fire seasons or causal fire-risk forecasts."
        )

    if not critical_months.empty:
        st.markdown("##### Monthly activity profile")
        if {"month_name", "mean_observations_per_active_day"}.issubset(critical_months.columns):
            month_view = critical_months.sort_values("month")
            fig = px.bar(
                month_view,
                x="month_name",
                y="mean_observations_per_active_day",
                title="Mean observations per active day by calendar month",
                labels={
                    "month_name": "Month",
                    "mean_observations_per_active_day": "Mean observations / active day",
                },
            )
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(critical_months, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### NASA HLS Landsat corroboration inventory")
    hls = _fh_optional_csv(P5 / "hls_l30_scene_inventory.csv")

    if hls.empty:
        st.info("HLS L30 scene inventory is unavailable.")
    else:
        h1, h2, h3 = st.columns(3)
        h1.metric("Scene records", f"{len(hls):,}")
        h2.metric(
            "Candidate observations covered",
            f"{hls['observation_uid'].nunique():,}" if "observation_uid" in hls.columns else "N/A",
        )
        h3.metric(
            "Unique scenes",
            f"{hls['scene_id'].nunique():,}" if "scene_id" in hls.columns else "N/A",
        )

        if "eo_cloud_cover_percent" in hls.columns:
            hls["eo_cloud_cover_percent"] = pd.to_numeric(
                hls["eo_cloud_cover_percent"], errors="coerce"
            )
            hls_cloud = hls.dropna(subset=["eo_cloud_cover_percent"])
            if not hls_cloud.empty:
                fig = px.histogram(
                    hls_cloud,
                    x="eo_cloud_cover_percent",
                    nbins=20,
                    title="HLS scene cloud-cover metadata",
                    labels={"eo_cloud_cover_percent": "Cloud cover (%)"},
                )
                st.plotly_chart(fig, use_container_width=True)

        hls_cols = [
            c for c in [
                "observation_uid", "scene_id", "scene_datetime_utc",
                "absolute_offset_hours", "eo_cloud_cover_percent",
                "collection", "asset_keys",
            ] if c in hls.columns
        ]
        st.dataframe(hls[hls_cols].head(1000), use_container_width=True, hide_index=True)
        st.download_button(
            "Download HLS scene inventory",
            hls.to_csv(index=False).encode("utf-8"),
            file_name="fireharmonics_hls_l30_scene_inventory.csv",
            mime="text/csv",
            key="p8_download_hls",
        )
        st.warning(
            "This is a scene-availability and metadata inventory only. HLS L30 is "
            "surface-reflectance imagery, not a thermal active-fire product. Pixel-level "
            "QA and visual corroboration have not been completed."
        )

    st.divider()
    st.markdown("#### Data provenance and interpretation")
    st.write(
        "Primary observation source: the locally archived NASA FIRMS standard-pixel "
        "MODIS and VIIRS observations integrated in the project staging dataset."
    )
    st.write(
        "Analysis outputs are local, reproducible project artifacts. Observation rows "
        "are not equivalent to unique fire events; sensor coverage, overpass timing, "
        "confidence definitions, and missing observations affect interpretation."
    )
    st.caption(
        "NASA data use does not imply NASA review, partnership, endorsement, or validation "
        "of FireHarmonics."
    )

'''

# Recalculate footer position AFTER all earlier source modifications.
footer_pos = source.rfind(footer)
if footer_pos < 0:
    raise SystemExit("Footer marker disappeared after tab modifications. No app changes made.")

source = source[:footer_pos] + research_code + "\n" + source[footer_pos:]

# Compile in memory first, then make a timestamped backup and write.
compile(source, str(app), "exec")
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = app.with_name(f"app_before_problem8_{stamp}.py")
shutil.copy2(app, backup)
app.write_text(source, encoding="utf-8")

# Verify written file.
py_compile.compile(str(app), doraise=True)
print("PATCH_OK")
print("Backup:", backup.relative_to(root))
print("Updated:", app.relative_to(root))
