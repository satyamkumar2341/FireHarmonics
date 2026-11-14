from pathlib import Path
import json

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

tab_overview, tab_dora, tab_data, tab_method, tab_sensor = st.tabs(
    [
        "Overview",
        "DORA analysis",
        "Data explorer",
        "Methodology & limitations",
        "Sensor Explorer",
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
            st.warning(
                "MODIS Terra has only 10 observations in the complete "
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

st.divider()
st.caption("FireHarmonics • Exploratory research prototype • Interpret all candidate relationships with the stated limitations.")
