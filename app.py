from pathlib import Path
import json
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st
import folium
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "processed"

st.set_page_config(
    page_title="FireHarmonics | Satellite Fire Observation Analysis",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1500px;}
.hero {padding: 1.4rem 1.6rem; border: 1px solid rgba(128,128,128,.25);
       border-radius: 16px; background: linear-gradient(115deg, rgba(220,80,35,.16), rgba(230,150,45,.06));}
.hero h1 {margin: 0; font-size: 2.25rem;}
.hero p {margin: .45rem 0 0 0; opacity: .82;}
.small-note {font-size: .85rem; opacity: .75;}
.metric-label {font-size: .85rem; opacity: .75;}
</style>
""", unsafe_allow_html=True)


def load_csv(name):
    path = DATA / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        st.warning(f"Could not read {name}: {exc}")
        return pd.DataFrame()


def load_summary():
    path = DATA / "dora_run_summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


obs = load_csv("harmonized_observations.csv")
pairs = load_csv("dora_candidate_pairs.csv")
spatial = load_csv("dora_spatial_candidates_5km.csv")
status = load_csv("dora_observation_status.csv")
sensitivity = load_csv("dora_threshold_sensitivity.csv")
summary = load_summary()
ranked_pairs = load_csv("dora_ranked_candidates.csv")
sensor_raw_summary = load_csv("sensor_raw_platform_summary.csv")
sensor_confidence_counts = load_csv("sensor_native_confidence_counts.csv")
sensor_one_to_one = load_csv("sensor_one_to_one_baseline.csv")
sensor_date_bootstrap = load_csv("sensor_date_cluster_bootstrap.csv")
sensor_threshold_bootstrap = load_csv("sensor_threshold_bootstrap.csv")

ANOMALY_DIR = DATA / "anomaly_20230301_20230531"

def load_anomaly_csv(name):
    file_path = ANOMALY_DIR / name
    if not file_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(file_path)
    except Exception as exc:
        st.warning(f"Could not read anomaly output {name}: {exc}")
        return pd.DataFrame()

anomaly_activity = load_anomaly_csv("daily_grid_activity.csv")
anomaly_alerts = load_anomaly_csv("anomaly_alerts.csv")

anomaly_summary_path = ANOMALY_DIR / "anomaly_summary.json"
try:
    anomaly_summary = json.loads(anomaly_summary_path.read_text(encoding="utf-8"))
except Exception:
    anomaly_summary = {}

ambiguity_summary_path = DATA / "dora_ambiguity_summary.json"
ambiguity_summary = (
    json.loads(ambiguity_summary_path.read_text(encoding="utf-8"))
    if ambiguity_summary_path.exists()
    else {}
)
st.markdown("""
<div class="hero">
  <h1>🔥 FireHarmonics</h1>
  <p>Cross-sensor satellite fire-observation harmonization and exploratory relationship analysis</p>
</div>
""", unsafe_allow_html=True)

st.caption("Research prototype • NASA FIRMS-derived observations • Local dataset snapshot")

if obs.empty:
    st.error("The harmonized dataset was not found or contains no rows.")
    st.markdown(f"Expected file: `{DATA / 'harmonized_observations.csv'}`")
    st.info("Generate the harmonized dataset first, then refresh this page.")
    st.stop()

# Normalize commonly used fields without modifying source files.
for col in ["latitude", "longitude", "frp_mw"]:
    if col in obs.columns:
        obs[col] = pd.to_numeric(obs[col], errors="coerce")
for col in ["sensor", "platform", "daynight"]:
    if col in obs.columns:
        obs[col] = obs[col].astype(str)
if "acq_date" in obs.columns:
    obs["acq_date"] = obs["acq_date"].astype(str)

with st.sidebar:
    st.header("Explore observations")
    st.caption("Filters apply to the observation overview and map.")
    filtered = obs.copy()

    if "sensor" in filtered.columns:
        sensors = sorted(filtered["sensor"].dropna().unique().tolist())
        chosen_sensors = st.multiselect("Sensor", sensors, default=sensors)
        filtered = filtered[filtered["sensor"].isin(chosen_sensors)]

    if "platform" in filtered.columns:
        platforms = sorted(filtered["platform"].dropna().unique().tolist())
        chosen_platforms = st.multiselect("Platform", platforms, default=platforms)
        filtered = filtered[filtered["platform"].isin(chosen_platforms)]

    if "daynight" in filtered.columns:
        phases = sorted(filtered["daynight"].dropna().unique().tolist())
        chosen_phases = st.multiselect("Day / night flag", phases, default=phases)
        filtered = filtered[filtered["daynight"].isin(chosen_phases)]

    if "acq_date" in filtered.columns and not filtered.empty:
        dates = sorted(filtered["acq_date"].dropna().unique().tolist())
        if dates:
            date_range = st.select_slider(
                "Acquisition date range",
                options=dates,
                value=(dates[0], dates[-1]) if len(dates) > 1 else (dates[0], dates[0]),
            )
            filtered = filtered[
                filtered["acq_date"].between(date_range[0], date_range[1])
            ]

    st.divider()
    st.caption("This dashboard reads local project outputs. It does not imply a live satellite feed.")

total = len(filtered)
unique_platforms = filtered["platform"].nunique() if "platform" in filtered.columns else 0
date_count = filtered["acq_date"].nunique() if "acq_date" in filtered.columns else 0
sensor_count = filtered["sensor"].nunique() if "sensor" in filtered.columns else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Observations in view", f"{total:,}")
m2.metric("Sensors", sensor_count)
m3.metric("Platforms", unique_platforms)
m4.metric("Acquisition dates", date_count)

tab_overview, tab_dora, tab_data, tab_method, tab_sensor, tab_anomaly, tab_research = st.tabs(
    [
        "Overview",
        "DORA analysis",
        "Data explorer",
        "Methodology & limitations",
        "Sensor Explorer",
        "Anomaly Detection",
        "Research Explorer",
    ]
)

with tab_overview:
    st.subheader("Observation overview")
    left, right = st.columns(2)

    with left:
        if "sensor" in filtered.columns and not filtered.empty:
            counts = filtered["sensor"].value_counts().rename_axis("Sensor").reset_index(name="Observations")
            fig = px.bar(counts, x="Sensor", y="Observations", color="Sensor",
                         title="Observations by sensor", text_auto=True)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sensor field unavailable.")

    with right:
        if "platform" in filtered.columns and not filtered.empty:
            counts = filtered["platform"].value_counts().rename_axis("Platform").reset_index(name="Observations")
            fig = px.bar(counts, x="Platform", y="Observations", color="Platform",
                         title="Observations by platform", text_auto=True)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Platform field unavailable.")

    left, right = st.columns(2)
    with left:
        if {"acq_date", "sensor"}.issubset(filtered.columns) and not filtered.empty:
            daily = filtered.groupby(["acq_date", "sensor"]).size().reset_index(name="Observations")
            fig = px.line(daily, x="acq_date", y="Observations", color="sensor",
                          markers=True, title="Daily observation counts")
            fig.update_xaxes(title="Acquisition date")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Date or sensor field unavailable.")

    with right:
        if "daynight" in filtered.columns and not filtered.empty:
            phase = filtered["daynight"].value_counts().rename_axis("Flag").reset_index(name="Observations")
            fig = px.pie(phase, names="Flag", values="Observations",
                         title="Day / night flag distribution", hole=.45)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Day/night field unavailable.")

    st.subheader("Geographic observation map")
    if {"latitude", "longitude"}.issubset(filtered.columns):
        points = filtered.dropna(subset=["latitude", "longitude"])
        if not points.empty:
            center = [float(points["latitude"].median()), float(points["longitude"].median())]
            fmap = folium.Map(location=center, zoom_start=6, control_scale=True)
            # Limit rendered markers to keep browser performance reasonable.
            display_points = points.head(2500)
            for _, row in display_points.iterrows():
                sensor = str(row.get("sensor", "Unknown"))
                platform = str(row.get("platform", ""))
                date = str(row.get("acq_date", ""))
                popup = f"{sensor} | {platform}<br>{date}"
                folium.CircleMarker(
                    location=[float(row["latitude"]), float(row["longitude"])],
                    radius=3, color="#e45b32", fill=True, fill_opacity=.65,
                    popup=folium.Popup(popup, max_width=260),
                ).add_to(fmap)
            st_folium(fmap, use_container_width=True, height=520, returned_objects=[])
            st.caption(f"Showing {len(display_points):,} plotted observations out of {len(points):,} filtered rows.")
        else:
            st.info("No valid coordinates available for the selected filters.")
    else:
        st.info("Latitude/longitude fields are unavailable.")

with tab_dora:
    st.subheader("DORA — Detection Observation Relationship Analysis")
    st.write("Exploratory candidate relationships between Aqua MODIS and VIIRS observations.")
    if summary:
        a, b, c, d = st.columns(4)
        a.metric("Aqua MODIS observations", f"{summary.get('modis_aqua_observations', 0):,}")
        b.metric("VIIRS observations", f"{summary.get('viirs_observations', 0):,}")
        c.metric("Spatial candidates ≤ 5 km", f"{summary.get('spatial_candidates_within_5km', 0):,}")
        d.metric("Baseline candidate pairs", f"{summary.get('baseline_candidate_pairs', 0):,}")
        st.caption(
            f"Baseline: {summary.get('baseline_radius_km', '—')} km radius · "
            f"{summary.get('baseline_time_window_minutes', '—')} minute time window"
        )
    else:
        st.warning("DORA summary JSON not found. Showing available DORA tables, if present.")

    st.warning(
        "Candidate relationships are not confirmed fire-event matches. "
        "'Unmatched under criteria' means no candidate was found under the selected rules; "
        "it does not establish a sensor miss."
    )

    # Candidate ambiguity analysis
    st.markdown("---")
    st.subheader("Candidate Ambiguity Analysis")
    st.caption(
        "Shows how candidate relationships overlap between observations. "
        "Ranks are investigation priorities, not match probabilities."
    )

    if ambiguity_summary:
        a, b, c, d = st.columns(4)

        a.metric(
            "MODIS with multiple candidates",
            f"{ambiguity_summary.get('modis_multiple_candidate_observations', 0):,}"
        )
        b.metric(
            "VIIRS with multiple candidates",
            f"{ambiguity_summary.get('viirs_multiple_candidate_observations', 0):,}"
        )

        distribution = ambiguity_summary.get(
            "ambiguity_pair_distribution", {}
        )

        c.metric(
            "Unique on both sides",
            f"{distribution.get('unique_on_both_sides', 0):,}"
        )
        d.metric(
            "Ambiguous on both sides",
            f"{distribution.get('ambiguous_on_both_sides', 0):,}"
        )

        if distribution:
            ambiguity_df = pd.DataFrame(
                list(distribution.items()),
                columns=["Relationship category", "Candidate pairs"]
            )

            fig = px.bar(
                ambiguity_df,
                x="Relationship category",
                y="Candidate pairs",
                color="Relationship category",
                title="Candidate-pair ambiguity distribution"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.info(
            "A unique relationship means only one candidate exists on both "
            "sides under the current matching criteria. It is not a confirmed "
            "fire-event match."
        )
    else:
        st.info("DORA ambiguity summary is not available.")

    if not ranked_pairs.empty:
        st.markdown("**Ranked candidate relationships**")

        display_columns = [
            col for col in [
                "modis_id",
                "viirs_id",
                "distance_km",
                "time_gap_minutes",
                "modis_candidate_count",
                "viirs_candidate_count",
                "ambiguity_type",
                "rank_for_modis",
                "rank_for_viirs"
            ]
            if col in ranked_pairs.columns
        ]

        st.dataframe(
            ranked_pairs[display_columns].head(20),
            use_container_width=True,
            height=400
        )

        st.download_button(
            "Download ranked candidate relationships CSV",
            ranked_pairs.to_csv(index=False).encode("utf-8"),
            file_name="dora_ranked_candidates.csv",
            mime="text/csv",
        )
    else:
        st.info("Ranked candidate relationships file is unavailable.")

    if not sensitivity.empty:

        st.markdown("**Threshold sensitivity**")
        required = {"radius_km", "time_window_minutes", "candidate_pairs"}
        if required.issubset(sensitivity.columns):
            pivot = sensitivity.pivot(
                index="radius_km", columns="time_window_minutes", values="candidate_pairs"
            ).sort_index()
            st.dataframe(pivot, use_container_width=True)
            chart_data = sensitivity.copy()
            chart_data["Threshold"] = chart_data["time_window_minutes"].astype(str) + " min"
            fig = px.line(chart_data, x="radius_km", y="candidate_pairs",
                          color="Threshold", markers=True,
                          title="Candidate-pair count by spatial and temporal threshold")
            fig.update_xaxes(title="Spatial radius (km)")
            fig.update_yaxes(title="Candidate relationships")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.dataframe(sensitivity, use_container_width=True)
    else:
        st.info("DORA threshold sensitivity output not found.")

    if not status.empty:
        st.markdown("**Observation candidate status**")
        if {"sensor", "candidate_status"}.issubset(status.columns):
            status_counts = status.groupby(["sensor", "candidate_status"]).size().reset_index(name="Observations")
            fig = px.bar(status_counts, x="sensor", y="Observations",
                         color="candidate_status", barmode="stack",
                         title="Candidate status by sensor")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(status.head(500), use_container_width=True)
    else:
        st.info("DORA observation-status output not found.")

    if not pairs.empty:
        st.markdown("**Baseline candidate pairs**")
        st.dataframe(pairs, use_container_width=True, height=350)
        st.download_button(
            "Download baseline candidate pairs CSV",
            pairs.to_csv(index=False).encode("utf-8"),
            file_name="dora_candidate_pairs.csv",
            mime="text/csv",
        )
    else:
        st.info("No baseline candidate-pair file found or it contains no rows.")

    if not spatial.empty:
        st.download_button(
            "Download 5 km spatial candidate table",
            spatial.to_csv(index=False).encode("utf-8"),
            file_name="dora_spatial_candidates_5km.csv",
            mime="text/csv",
        )

with tab_data:
    st.subheader("Filtered observation data")
    st.caption("The table reflects the filters selected in the sidebar.")
    st.dataframe(filtered, use_container_width=True, height=480)
    st.download_button(
        "Download filtered observations CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="fireharmonics_filtered_observations.csv",
        mime="text/csv",
    )

with tab_method:
    st.subheader("How to interpret FireHarmonics")
    st.markdown("""
**Purpose**

FireHarmonics explores how thermal-anomaly observations from different satellite
sensors can be compared while accounting for differences in sensor, platform,
acquisition time, location and day/night flag.

**DORA matching logic**

- Primary reference: Aqua MODIS observations.
- Comparison observations: VIIRS platforms present in the harmonized dataset.
- Spatial candidate search: BallTree with haversine distance, up to 5 km.
- Candidate eligibility: same acquisition date and same day/night flag.
- Baseline relationship filter: within 2 km and 240 minutes.
- Sensitivity analysis: 1, 2 and 5 km crossed with 60, 120 and 240 minutes.

**Important limitations**

- A candidate pair is a possible relationship for investigation, not a verified common fire event.
- An observation marked unmatched is unmatched only under the implemented criteria; it is not proof of a sensor miss.
- The primary Aqua reference dataset may not provide adequate nighttime coverage. Nighttime agreement must not be inferred where reference coverage is insufficient.
- The current DORA implementation requires the same acquisition date, so observations crossing UTC date boundaries are not paired.
- Results depend on the selected region, time period, data availability and thresholds.
- The dashboard displays local processed files. It does not automatically refresh from NASA FIRMS.
- Fire radiative power and confidence fields are sensor-reported values and should not be treated as directly interchangeable without additional calibration.

**Data provenance**

The project uses NASA FIRMS observations. This prototype is an independent research/analysis project and is not an official NASA product or endorsement.
""")
    st.markdown("**Files loaded**")
    file_rows = []
    for filename in [
        "harmonized_observations.csv",
        "dora_run_summary.json",
        "dora_candidate_pairs.csv",
        "dora_spatial_candidates_5km.csv",
        "dora_observation_status.csv",
        "dora_threshold_sensitivity.csv",
    ]:
        path = DATA / filename
        file_rows.append({"File": filename, "Present": path.exists(),
                          "Size (bytes)": path.stat().st_size if path.exists() else 0})
    st.dataframe(pd.DataFrame(file_rows), use_container_width=True)



with tab_sensor:
    st.subheader("Individual satellite platform exploration")
    st.caption(
        "Explore the actual harmonized NASA FIRMS-derived observations "
        "independently for each satellite platform."
    )

    platform_options = sorted(obs["platform"].dropna().unique().tolist())

    if not platform_options:
        st.warning("No satellite platform values are available.")
    else:
        selected_platform = st.selectbox(
            "Select satellite platform",
            platform_options,
            format_func=lambda value: {
                "Aqua": "MODIS Aqua",
                "Terra": "MODIS Terra",
                "NOAA-20": "VIIRS NOAA-20",
                "NOAA-21": "VIIRS NOAA-21",
            }.get(value, value),
            key="sensor_explorer_platform",
        )

        platform_df = obs[
            obs["platform"] == selected_platform
        ].copy()

        platform_df["_date"] = pd.to_datetime(
            platform_df["acq_date"], errors="coerce"
        ).dt.date

        valid_dates = sorted(platform_df["_date"].dropna().unique().tolist())

        if valid_dates:
            date_range = st.select_slider(
                "Acquisition date range",
                options=valid_dates,
                value=(valid_dates[0], valid_dates[-1]),
                key="sensor_explorer_dates",
            )
            platform_df = platform_df[
                platform_df["_date"].between(date_range[0], date_range[1])
            ]

        if "daynight" in platform_df.columns:
            available_phases = sorted(
                platform_df["daynight"].dropna().unique().tolist()
            )
            selected_phases = st.multiselect(
                "Day / night",
                available_phases,
                default=available_phases,
                key="sensor_explorer_daynight",
            )
            platform_df = platform_df[
                platform_df["daynight"].isin(selected_phases)
            ]

        sensor_name = (
            str(platform_df["sensor"].iloc[0])
            if not platform_df.empty and "sensor" in platform_df.columns
            else str(platform_df["sensor"].iloc[0])
            if not platform_df.empty
            else "Unknown"
        )

        total_platform = len(platform_df)
        valid_locations = (
            platform_df.dropna(subset=["latitude", "longitude"])
            if {"latitude", "longitude"}.issubset(platform_df.columns)
            else pd.DataFrame()
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Platform", selected_platform)
        k2.metric("Observations in view", f"{total_platform:,}")
        k3.metric("Valid locations", f"{len(valid_locations):,}")
        k4.metric(
            "Acquisition dates",
            platform_df["acq_date"].nunique()
            if "acq_date" in platform_df.columns else 0,
        )

        if selected_platform == "Terra":
            terra_count = int((obs["platform"] == "Terra").sum())
            st.warning(
                f"MODIS Terra has {terra_count:,} observations in the complete "
                "current dataset. Treat its coverage and comparisons as limited."
            )

        if platform_df.empty:
            st.info("No observations match the selected platform filters.")
        else:
            st.markdown("### Platform activity")

            left, right = st.columns(2)

            with left:
                if "acq_date" in platform_df.columns:
                    daily = (
                        platform_df.groupby("acq_date")
                        .size()
                        .reset_index(name="Observations")
                    )
                    fig = px.line(
                        daily,
                        x="acq_date",
                        y="Observations",
                        markers=True,
                        title="Daily observations",
                    )
                    fig.update_xaxes(title="Acquisition date")
                    st.plotly_chart(fig, use_container_width=True)

            with right:
                if "daynight" in platform_df.columns:
                    phase_counts = (
                        platform_df["daynight"]
                        .value_counts()
                        .rename_axis("Day/night flag")
                        .reset_index(name="Observations")
                    )
                    fig = px.bar(
                        phase_counts,
                        x="Day/night flag",
                        y="Observations",
                        title="Day / night distribution",
                        text_auto=True,
                    )
                    st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Geographic distribution")

            if not valid_locations.empty:
                map_points = valid_locations.head(3000)
                center = [
                    float(map_points["latitude"].median()),
                    float(map_points["longitude"].median()),
                ]
                fmap = folium.Map(
                    location=center,
                    zoom_start=6,
                    control_scale=True,
                )

                for _, row in map_points.iterrows():
                    popup = (
                        f"ID: {row.get('observation_id', 'Unknown')}<br>"
                        f"Platform: {selected_platform}<br>"
                        f"Date: {row.get('acq_date', 'Unknown')}<br>"
                        f"UTC: {row.get('observation_datetime_utc', 'Unknown')}"
                    )
                    folium.CircleMarker(
                        location=[
                            float(row["latitude"]),
                            float(row["longitude"]),
                        ],
                        radius=3,
                        color="#e45b32" if sensor_name == "MODIS" else "#2477b3",
                        fill=True,
                        fill_opacity=0.65,
                        popup=folium.Popup(popup, max_width=300),
                    ).add_to(fmap)

                st_folium(
                    fmap,
                    use_container_width=True,
                    height=500,
                    returned_objects=[],
                    key="sensor_explorer_map",
                )
                st.caption(
                    f"Displaying {len(map_points):,} map markers from "
                    f"{len(valid_locations):,} observations in the selected view. "
                    "Markers represent satellite detections, not confirmed fire events."
                )
            else:
                st.info("No valid geographic coordinates are available.")

            st.markdown("### Observation inspector")

            observation_ids = sorted(
                platform_df["observation_id"].dropna().astype(str).unique().tolist()
            )

            if observation_ids:
                selected_id = st.selectbox(
                    "Choose an observation ID",
                    observation_ids,
                    key="sensor_explorer_observation_id",
                )

                record = platform_df[
                    platform_df["observation_id"].astype(str) == selected_id
                ].iloc[0]

                detail_columns = [
                    "observation_id",
                    "sensor",
                    "platform",
                    "instrument",
                    "acq_date",
                    "acq_time_utc",
                    "observation_datetime_utc",
                    "latitude",
                    "longitude",
                    "confidence_native",
                    "confidence_scheme",
                    "frp_mw",
                    "brightness_native_kelvin",
                    "brightness_band",
                    "daynight",
                    "scan",
                    "track",
                    "source_file",
                ]

                details = {
                    column: record[column]
                    for column in detail_columns
                    if column in platform_df.columns
                }

                details_df = pd.DataFrame(
                    list(details.items()),
                    columns=["Field", "Recorded value"],
                )
                details_df["Field"] = details_df["Field"].astype(str)
                details_df["Recorded value"] = details_df["Recorded value"].map(
                    lambda value: str(value) if pd.notna(value) else "?"
                )

                st.dataframe(
                    details_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.caption(
                    "Confidence and brightness are displayed in their native "
                    "sensor context. They are not normalized or directly "
                    "interchangeable across instruments."
                )

            st.markdown("### Platform comparison context")

            comparison = (
                obs.groupby(["sensor", "platform"])
                .size()
                .reset_index(name="Observations")
            )

            fig = px.bar(
                comparison,
                x="platform",
                y="Observations",
                color="sensor",
                barmode="group",
                text_auto=True,
                title="Observation counts across all available platforms",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Native confidence categories")

            if {"confidence_native", "confidence_scheme"}.issubset(platform_df.columns):
                confidence_counts = (
                    platform_df.groupby(
                        ["confidence_scheme", "confidence_native"],
                        dropna=False,
                    )
                    .size()
                    .reset_index(name="Observations")
                )
                st.dataframe(
                    confidence_counts,
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("### Cross-sensor FRP comparability (exploratory)")

            if sensor_raw_summary.empty or sensor_one_to_one.empty:
                st.info(
                    "Sensor comparability outputs are not available in the production "
                    "dataset yet. Run the validated comparability analysis to populate "
                    "this section."
                )
            else:
                st.caption(
                    "FRP values are compared across candidate satellite-observation "
                    "associations. These are not verified same-fire matches, ground "
                    "truth, sensor calibration factors, or accuracy estimates."
                )

                st.markdown("#### Raw platform-level observations")
                st.dataframe(
                    sensor_raw_summary,
                    use_container_width=True,
                    hide_index=True,
                )

                if {"platform", "frp_median_mw", "sensor"}.issubset(
                    sensor_raw_summary.columns
                ):
                    fig = px.bar(
                        sensor_raw_summary,
                        x="platform",
                        y="frp_median_mw",
                        color="sensor",
                        barmode="group",
                        title="Median native FRP by platform",
                        labels={
                            "platform": "Platform",
                            "frp_median_mw": "Median FRP (MW)",
                            "sensor": "Sensor family",
                        },
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### One-to-one candidate comparison")
                if not sensor_date_bootstrap.empty:
                    baseline_view = sensor_one_to_one.merge(
                        sensor_date_bootstrap,
                        on="platform",
                        how="left",
                        suffixes=("", "_bootstrap"),
                    )
                    preferred = [
                        "platform",
                        "candidate_pairs",
                        "one_to_one_pairs",
                        "unique_dates",
                        "median_frp_ratio",
                        "median_daily_ratio",
                        "cluster_bootstrap_95_low",
                        "cluster_bootstrap_95_high",
                        "median_distance_km",
                        "median_time_gap_min",
                    ]
                    baseline_view = baseline_view[
                        [c for c in preferred if c in baseline_view.columns]
                    ]
                    st.dataframe(
                        baseline_view,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.dataframe(
                        sensor_one_to_one,
                        use_container_width=True,
                        hide_index=True,
                    )

                st.markdown("#### Matching-threshold robustness")
                if not sensor_threshold_bootstrap.empty:
                    st.dataframe(
                        sensor_threshold_bootstrap,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Threshold sensitivity output is not available.")

                st.markdown("#### Native confidence distributions")
                if not sensor_confidence_counts.empty:
                    st.dataframe(
                        sensor_confidence_counts,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Native confidence output is not available.")

                st.warning(
                    "Interpretation: FRP ratios below 1 describe lower VIIRS FRP "
                    "within the selected candidate associations. They do not by "
                    "themselves establish sensor bias or justify a calibration "
                    "correction. Confidence categories remain sensor-native and "
                    "must not be treated as interchangeable."
                )

            st.download_button(
                "Download selected platform observations CSV",
                platform_df.drop(columns=["_date"], errors="ignore")
                .to_csv(index=False)
                .encode("utf-8"),
                file_name=f"fireharmonics_{selected_platform.lower().replace('-', '_')}_observations.csv",
                mime="text/csv",
                key="sensor_explorer_download",
            )

            st.info(
                "These are NASA FIRMS-derived active fire detections from the "
                "local harmonized snapshot. Near-real-time detections are "
                "preliminary and are not independently confirmed fire events."
            )


with tab_anomaly:
    st.subheader("Historical Fire-Observation Anomaly Detection")
    st.caption(
        "Platform-stratified, 5 km grid-level statistical monitoring. "
        "Alerts indicate unusual satellite observation volume, not confirmed fire outbreaks."
    )

    if anomaly_activity.empty:
        st.warning(
            "Anomaly outputs are unavailable. Run scripts/run_anomaly_detection.py "
            "to generate the activity and alert files."
        )
    else:
        severity_counts = anomaly_summary.get("severity_counts", {})
        total_rows = int(anomaly_summary.get("daily_grid_platform_rows", len(anomaly_activity)))
        alert_rows = int(anomaly_summary.get("alert_rows", len(anomaly_alerts)))
        insufficient = int(severity_counts.get("insufficient_history", 0))
        coverage = (100 * (total_rows - insufficient) / total_rows) if total_rows else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Alert records", f"{alert_rows:,}")
        m2.metric("High alerts", f"{severity_counts.get('high', 0):,}")
        m3.metric("Scored records", f"{total_rows - insufficient:,}")
        m4.metric("Scoring coverage", f"{coverage:.1f}%")

        st.warning(
            f"{insufficient:,} of {total_rows:,} platform-grid records have insufficient "
            "history. These records were not scored. Missing satellite observations "
            "are not interpreted as zero fire activity."
        )

        if not anomaly_alerts.empty:
            alert_view = anomaly_alerts.copy()
            alert_view["date"] = alert_view["date"].astype(str)
            alert_view["platform"] = alert_view["platform"].astype(str)
            alert_view["severity"] = alert_view["severity"].astype(str)

            c1, c2, c3 = st.columns(3)
            platforms_available = sorted(alert_view["platform"].dropna().unique().tolist())
            chosen_platform = c1.selectbox(
                "Platform",
                ["All"] + platforms_available,
                key="anomaly_platform_filter",
            )

            severities_available = ["low", "medium", "high"]
            chosen_severities = c2.multiselect(
                "Alert severity",
                severities_available,
                default=severities_available,
                key="anomaly_severity_filter",
            )

            dates_available = sorted(alert_view["date"].dropna().unique().tolist())
            if len(dates_available) > 1:
                chosen_dates = c3.select_slider(
                    "Alert date range",
                    options=dates_available,
                    value=(dates_available[0], dates_available[-1]),
                    key="anomaly_date_filter",
                )
            elif dates_available:
                chosen_dates = (dates_available[0], dates_available[0])
                c3.caption(f"Only available alert date: {dates_available[0]}")
            else:
                chosen_dates = ("", "")

            selected = alert_view.copy()
            if chosen_platform != "All":
                selected = selected[selected["platform"] == chosen_platform]
            selected = selected[selected["severity"].isin(chosen_severities)]
            if chosen_dates[0]:
                selected = selected[
                    selected["date"].between(chosen_dates[0], chosen_dates[1])
                ]

            st.markdown("#### Selected alert summary")
            counts = Counter(selected["severity"].tolist())
            a, b, c, d = st.columns(4)
            a.metric("Selected alerts", f"{len(selected):,}")
            b.metric("Low", counts.get("low", 0))
            c.metric("Medium", counts.get("medium", 0))
            d.metric("High", counts.get("high", 0))

            if selected.empty:
                st.info("No alerts match the selected filters.")
            else:
                left, right = st.columns(2)

                with left:
                    severity_data = pd.DataFrame(
                        [{"Severity": key, "Alerts": counts.get(key, 0)}
                         for key in ["low", "medium", "high"]]
                    )
                    fig = px.bar(
                        severity_data,
                        x="Severity",
                        y="Alerts",
                        title="Alert severity distribution",
                        text_auto=True,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with right:
                    daily_counts = Counter(selected["date"].tolist())
                    trend_data = pd.DataFrame(
                        [{"Date": key, "Alerts": value}
                         for key, value in sorted(daily_counts.items())]
                    )
                    fig = px.line(
                        trend_data,
                        x="Date",
                        y="Alerts",
                        markers=True,
                        title="Daily anomaly alerts",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### Repeated alert grids")
                repeated = Counter(
                    (str(row["platform"]), str(row["grid_id"]))
                    for _, row in selected.iterrows()
                )
                repeated_rows = []
                for (platform, grid), number_of_days in repeated.most_common(20):
                    subset = selected[
                        (selected["platform"] == platform)
                        & (selected["grid_id"] == grid)
                    ]
                    repeated_rows.append({
                        "Platform": platform,
                        "Grid": grid,
                        "Alert days": number_of_days,
                        "First alert": subset["date"].min(),
                        "Last alert": subset["date"].max(),
                    })
                st.dataframe(
                    pd.DataFrame(repeated_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown("#### Alert observation details")
                display_columns = [
                    col for col in [
                        "date", "platform", "grid_id", "observation_count",
                        "baseline_median", "baseline_mad", "prior_active_days",
                        "robust_score", "severity", "interpretation"
                    ] if col in selected.columns
                ]
                st.dataframe(
                    selected[display_columns].sort_values(
                        ["date", "robust_score"], ascending=[False, False]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download filtered anomaly alerts CSV",
                    selected.to_csv(index=False).encode("utf-8"),
                    file_name="fireharmonics_filtered_anomaly_alerts.csv",
                    mime="text/csv",
                    key="anomaly_alert_download",
                )

        else:
            st.info("No anomaly alerts were generated for this dataset.")

        st.markdown("#### Detection method and limitations")
        st.write(
            f"Grid size: {anomaly_summary.get('grid_km', 'N/A')} km · "
            f"Baseline window: {anomaly_summary.get('baseline_days', 'N/A')} days · "
            f"Minimum prior active days: "
            f"{anomaly_summary.get('min_prior_active_days', 'N/A')}"
        )
        for limitation in anomaly_summary.get("limitations", []):
            st.caption("• " + limitation)

        if not anomaly_activity.empty:
            st.download_button(
                "Download complete daily grid activity CSV",
                anomaly_activity.to_csv(index=False).encode("utf-8"),
                file_name="fireharmonics_daily_grid_activity.csv",
                mime="text/csv",
                key="anomaly_activity_download",
            )


st.divider()


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


st.caption("FireHarmonics • Exploratory research prototype • Interpret all candidate relationships with the stated limitations.")
