from pathlib import Path
from datetime import datetime
import shutil

path = Path("app.py")
source = path.read_text(encoding="utf-8")

# Safety: don't apply twice.
if "with tab_anomaly:" in source:
    raise SystemExit("Anomaly tab already exists. No changes made.")

# 1. Add Counter import.
old = "import json\n"
new = "import json\nfrom collections import Counter\n"
assert source.count(old) == 1
source = source.replace(old, new, 1)

# 2. Add anomaly data loading.
old = 'sensor_threshold_bootstrap = load_csv("sensor_threshold_bootstrap.csv")\n'
new = old + '''
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
'''
assert source.count(old) == 1
source = source.replace(old, new, 1)

# 3. Add sixth tab.
old = 'tab_overview, tab_dora, tab_data, tab_method, tab_sensor = st.tabs('
new = 'tab_overview, tab_dora, tab_data, tab_method, tab_sensor, tab_anomaly = st.tabs('
assert source.count(old) == 1
source = source.replace(old, new, 1)

old = '''        "Methodology & limitations",
        "Sensor Explorer",
'''
new = '''        "Methodology & limitations",
        "Sensor Explorer",
        "Anomaly Detection",
'''
assert source.count(old) == 1
source = source.replace(old, new, 1)

# 4. Anomaly tab implementation.
tab_code = r'''

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
'''

footer = '''
st.divider()
st.caption("FireHarmonics'''
assert source.count(footer) == 1
source = source.replace(footer, tab_code + "\n" + footer, 1)

# Backup only after all insertion checks have passed.
backup = Path("app.py.backup_anomaly_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(path, backup)
path.write_text(source, encoding="utf-8")

print("Anomaly dashboard integration applied.")
print("Backup:", backup)
print("Updated:", path)
