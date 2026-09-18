"""Does education break the poverty cycle?

An interactive Streamlit app built on live data from the World Bank
Indicators API (v2). See README.md for the story and the deployment notes.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis import build_cross_section, fit_trend
from worldbank import BASE_URL, WorldBankError, fetch_countries, fetch_indicator

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

FIRST_YEAR = 1990
LAST_YEAR = dt.date.today().year
POPULATION_CODE = "SP.POP.TOTL"
CACHE_TTL = 60 * 60 * 6  # six hours: these series are updated a few times a year

EDUCATION_INDICATORS = {
    "SE.SEC.CMPT.LO.ZS": {
        "name": "Lower secondary completion rate",
        "unit": "% of relevant age group",
        "note": (
            "Share of young people reaching the last grade of lower secondary school, "
            "which is roughly the end of compulsory education in most countries."
        ),
    },
    "SE.PRM.CMPT.ZS": {
        "name": "Primary completion rate",
        "unit": "% of relevant age group",
        "note": (
            "Share of children reaching the last grade of primary school. It can exceed "
            "100% because pupils older than the official age are still counted."
        ),
    },
    "SE.ADT.LITR.ZS": {
        "name": "Adult literacy rate",
        "unit": "% of people aged 15 and above",
        "note": (
            "Share of adults who can read and write a short simple statement. It is "
            "collected mostly through censuses, so it moves slowly and is updated rarely."
        ),
    },
}

OUTCOME_INDICATORS = {
    "SI.POV.DDAY": {
        "name": "Extreme poverty rate",
        "unit": "% living on less than $3.00 a day (2021 PPP)",
        "note": (
            "Poverty headcount ratio from the World Bank Poverty and Inequality Platform, "
            "based on national household surveys."
        ),
        "log_default": False,
        "direction": "lower is better",
    },
    "NY.GDP.PCAP.CD": {
        "name": "GDP per capita",
        "unit": "current US$",
        "note": (
            "Total economic output divided by population. A proxy for average income, "
            "but it says nothing about how that income is shared."
        ),
        "log_default": True,
        "direction": "higher is better",
    },
}

REGION_COLORS = {
    "East Asia & Pacific": "#4C78A8",
    "Europe & Central Asia": "#54A24B",
    "Latin America & Caribbean": "#F58518",
    "Middle East, North Africa, Afghanistan & Pakistan": "#B279A2",
    "North America": "#72B7B2",
    "South Asia": "#E45756",
    "Sub-Saharan Africa": "#D3A625",
}
FALLBACK_COLOR = "#9C9C9C"

st.set_page_config(
    page_title="Does education break the poverty cycle?",
    page_icon="🎓",
    layout="wide",
)


# --------------------------------------------------------------------------- #
# Cached data loading
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_countries() -> pd.DataFrame:
    return fetch_countries()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_indicator(code: str) -> pd.DataFrame:
    return fetch_indicator(code, FIRST_YEAR, LAST_YEAR)


def stop_with_api_error(error: Exception) -> None:
    """Show one clear message when the API is unavailable, then halt the app."""
    st.error(
        "**The live data could not be loaded right now.**\n\n"
        f"{error}\n\n"
        "The World Bank API is a free public service and is occasionally slow or "
        "temporarily unavailable. Nothing is broken on your side — wait a moment "
        "and press the button below."
    )
    if st.button("Try again", type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Endpoint: `{BASE_URL}` · last checked at {dt.datetime.now():%H:%M:%S}")
    st.stop()


# --------------------------------------------------------------------------- #
# Sidebar controls
# --------------------------------------------------------------------------- #

st.sidebar.title("Controls")
st.sidebar.caption("Every chart below reacts to these choices.")

education_code = st.sidebar.selectbox(
    "Education indicator",
    options=list(EDUCATION_INDICATORS),
    format_func=lambda code: EDUCATION_INDICATORS[code]["name"],
    help="The schooling measure plotted on the horizontal axis.",
    key="education_code",
)

outcome_code = st.sidebar.selectbox(
    "Poverty / income indicator",
    options=list(OUTCOME_INDICATORS),
    format_func=lambda code: OUTCOME_INDICATORS[code]["name"],
    help="The outcome plotted on the vertical axis.",
    key="outcome_code",
)

year_start, year_end = st.sidebar.slider(
    "Use the most recent observation between",
    min_value=FIRST_YEAR,
    max_value=LAST_YEAR,
    value=(2010, LAST_YEAR),
    help=(
        "Poverty and literacy are measured by surveys, not every year. "
        "A country enters the chart if it has at least one observation in this window."
    ),
    key="year_window",
)

education_meta = EDUCATION_INDICATORS[education_code]
outcome_meta = OUTCOME_INDICATORS[outcome_code]

# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #

with st.spinner("Loading live data from the World Bank API…"):
    try:
        countries = load_countries()
        education_series = load_indicator(education_code)
        outcome_series = load_indicator(outcome_code)
        population_series = load_indicator(POPULATION_CODE)
    except WorldBankError as error:
        stop_with_api_error(error)
    except Exception as error:  # noqa: BLE001 - last resort, keep the UI friendly
        stop_with_api_error(error)

all_regions = sorted(countries["region"].unique())
selected_regions = st.sidebar.multiselect(
    "Regions to include",
    options=all_regions,
    default=all_regions,
    help="Uncheck a region to see whether the pattern holds without it.",
    key="regions",
)

show_trend = st.sidebar.checkbox("Show trend line", value=True, key="show_trend")

log_allowed = outcome_code == "NY.GDP.PCAP.CD"
log_scale = (
    st.sidebar.checkbox(
        "Log scale on the vertical axis",
        value=outcome_meta["log_default"],
        key="log_scale",
    )
    if log_allowed
    else False
)

st.sidebar.divider()
if st.sidebar.button("Refresh data from the API"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption(
    "Source: World Bank Indicators API (v2). Data is cached for six hours so the app "
    "stays fast and polite to a free public service."
)

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

st.title("Does education break the poverty cycle?")
st.markdown(
    "**Who this is for:** education and finance ministries deciding where the next "
    "euro of public spending should go — and the parents and students who live with "
    "that decision. Schooling is expensive and slow to pay off, so it competes badly "
    "against cash transfers and infrastructure in a budget meeting. This app asks "
    "whether the data justifies protecting it."
)

st.markdown(
    f"**The question:** across countries, does a higher *{education_meta['name'].lower()}* "
    f"go together with a lower *{outcome_meta['name'].lower()}*?"
)

tab_compare, tab_country, tab_data = st.tabs(
    ["Compare countries", "One country over time", "Data & limitations"]
)

# --------------------------------------------------------------------------- #
# Tab 1 — cross-country scatter
# --------------------------------------------------------------------------- #

with tab_compare:
    cross_section = build_cross_section(
        education_series,
        outcome_series,
        population_series,
        countries,
        year_start,
        year_end,
    )
    plot_df = cross_section[cross_section["region"].isin(selected_regions)].copy()

    dropped_nonpositive = 0
    if log_scale:
        dropped_nonpositive = int((plot_df["outcome"] <= 0).sum())
        plot_df = plot_df[plot_df["outcome"] > 0]

    if plot_df.empty:
        st.warning(
            "No country has both indicators available for the window and regions you "
            "picked. Widen the year range in the sidebar, or add regions back."
        )
    else:
        y_values = np.log10(plot_df["outcome"]) if log_scale else plot_df["outcome"]

        figure = go.Figure()
        size_reference = 2.0 * plot_df["population"].max() / (45.0**2)

        for region in sorted(plot_df["region"].unique()):
            subset = plot_df[plot_df["region"] == region]
            figure.add_trace(
                go.Scatter(
                    x=subset["education"],
                    y=subset["outcome"],
                    mode="markers",
                    name=region,
                    marker=dict(
                        size=subset["population"],
                        sizemode="area",
                        sizeref=size_reference,
                        sizemin=5,
                        color=REGION_COLORS.get(region, FALLBACK_COLOR),
                        opacity=0.78,
                        line=dict(width=0.8, color="white"),
                    ),
                    # Built as a DataFrame rather than np.column_stack: stacking a
                    # string column with numbers would cast everything to text and
                    # break the numeric formatting in the tooltip.
                    customdata=subset.assign(population_m=subset["population"] / 1e6)[
                        ["country", "education_year", "outcome_year", "population_m"]
                    ].to_numpy(),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        f"{education_meta['name']}: %{{x:.1f}}% (%{{customdata[1]}})<br>"
                        f"{outcome_meta['name']}: %{{y:,.1f}} (%{{customdata[2]}})<br>"
                        "Population: %{customdata[3]:,.1f}M<extra></extra>"
                    ),
                )
            )

        correlation = None
        if show_trend and len(plot_df) > 2:
            line_x, line_y, correlation = fit_trend(
                plot_df["education"].to_numpy(dtype=float),
                np.asarray(y_values, dtype=float),
            )
            figure.add_trace(
                go.Scatter(
                    x=line_x,
                    y=10**line_y if log_scale else line_y,
                    mode="lines",
                    name="Trend",
                    line=dict(color="#333333", width=2, dash="dash"),
                    hoverinfo="skip",
                )
            )

        figure.update_layout(
            height=560,
            margin=dict(l=10, r=10, t=50, b=10),
            title=(
                f"{outcome_meta['name']} vs {education_meta['name'].lower()} — "
                f"latest observation between {year_start} and {year_end}"
            ),
            xaxis_title=f"{education_meta['name']} ({education_meta['unit']})",
            yaxis_title=f"{outcome_meta['name']} ({outcome_meta['unit']})",
            legend=dict(orientation="h", yanchor="bottom", y=-0.28, x=0),
            plot_bgcolor="white",
        )
        figure.update_xaxes(gridcolor="#EDEDED", zeroline=False)
        figure.update_yaxes(
            gridcolor="#EDEDED", zeroline=False, type="log" if log_scale else "linear"
        )

        st.plotly_chart(figure, width="stretch")
        st.caption("Each bubble is one country. Bubble size is population; colour is World Bank region.")

        # ---------------- What the chart shows ---------------- #
        left, right = st.columns([3, 2])

        with left:
            st.subheader("What this shows")
            if correlation is not None:
                strength = (
                    "strong" if abs(correlation) >= 0.6
                    else "moderate" if abs(correlation) >= 0.35
                    else "weak"
                )
                direction = "negative" if correlation < 0 else "positive"
                scale_note = " (on a log scale)" if log_scale else ""
                st.markdown(
                    f"Across the **{len(plot_df)} countries** with data in this window, the "
                    f"relationship is **{strength} and {direction}**: r = **{correlation:.2f}**{scale_note}. "
                    f"Countries where more young people finish school tend to sit "
                    f"{'lower' if correlation < 0 else 'higher'} on {outcome_meta['name'].lower()}."
                )
            else:
                st.markdown(f"**{len(plot_df)} countries** have data in this window.")

            st.markdown(
                "Switch the education indicator in the sidebar and watch the cloud change "
                "shape. Primary completion is close to universal almost everywhere, so it "
                "barely separates rich countries from poor ones. **Lower secondary** "
                "completion still varies a lot — and that is where the gap opens up."
            )

        with right:
            st.subheader("The gap, in one number")
            quartile_df = plot_df.copy()
            try:
                quartile_df["group"] = pd.qcut(
                    quartile_df["education"],
                    4,
                    labels=["Lowest 25%", "Lower-middle", "Upper-middle", "Highest 25%"],
                    duplicates="drop",
                )
                summary = (
                    quartile_df.groupby("group", observed=True)["outcome"].median().reset_index()
                )
                bars = go.Figure(
                    go.Bar(
                        x=summary["group"].astype(str),
                        y=summary["outcome"],
                        marker_color=["#E45756", "#F58518", "#7BA7CC", "#4C78A8"][: len(summary)],
                        hovertemplate="%{x}<br>Median: %{y:,.1f}<extra></extra>",
                    )
                )
                bars.update_layout(
                    height=300,
                    margin=dict(l=10, r=10, t=30, b=10),
                    title=f"Median {outcome_meta['name'].lower()}",
                    xaxis_title=f"Countries grouped by {education_meta['name'].lower()}",
                    yaxis_title=outcome_meta["unit"],
                    plot_bgcolor="white",
                    showlegend=False,
                )
                bars.update_yaxes(gridcolor="#EDEDED")
                st.plotly_chart(bars, width="stretch")
            except ValueError:
                st.info("Not enough countries in this selection to split into four groups.")

        st.info(
            "**One limitation to keep in mind.** Poverty and literacy are measured by "
            "household surveys and censuses that run every few years, not annually. The "
            "chart therefore compares each country's *latest available* figure, so one "
            "bubble may be from 2011 and its neighbour from 2023 — hover to see the year "
            "behind each point. And a correlation across countries is not proof of cause: "
            "richer countries can afford better schools just as easily as better schools "
            "can make a country richer."
        )

        if dropped_nonpositive:
            st.caption(
                f"{dropped_nonpositive} country/countries with a value of zero or less were "
                "hidden because a log scale cannot display them."
            )

# --------------------------------------------------------------------------- #
# Tab 2 — one country over time
# --------------------------------------------------------------------------- #

with tab_country:
    st.subheader("How did a single country move?")

    available = countries[
        countries["iso3"].isin(set(education_series["iso3"]) & set(outcome_series["iso3"]))
    ]

    if available.empty:
        st.warning("No country has both of these indicators. Try a different combination.")
    else:
        names = available["country"].tolist()
        default_index = names.index("Viet Nam") if "Viet Nam" in names else 0

        picker_left, picker_right = st.columns(2)
        with picker_left:
            main_country = st.selectbox("Country", names, index=default_index, key="main_country")
        with picker_right:
            comparison = st.selectbox(
                "Compare with (optional)",
                ["None"] + [n for n in names if n != main_country],
                key="comparison_country",
            )

        def series_for(country_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
            iso3 = available.loc[available["country"] == country_name, "iso3"].iloc[0]
            edu = education_series[education_series["iso3"] == iso3].sort_values("year")
            out = outcome_series[outcome_series["iso3"] == iso3].sort_values("year")
            return edu, out

        main_edu, main_out = series_for(main_country)

        if main_edu.empty and main_out.empty:
            st.warning(
                f"The World Bank has no observations for {main_country} on these two "
                f"indicators since {FIRST_YEAR}. Pick another country."
            )
        else:
            timeline = make_subplots(specs=[[{"secondary_y": True}]])

            timeline.add_trace(
                go.Scatter(
                    x=main_edu["year"],
                    y=main_edu["value"],
                    name=f"{main_country} — {education_meta['name'].lower()}",
                    mode="lines+markers",
                    line=dict(color="#4C78A8", width=3),
                ),
                secondary_y=False,
            )
            timeline.add_trace(
                go.Scatter(
                    x=main_out["year"],
                    y=main_out["value"],
                    name=f"{main_country} — {outcome_meta['name'].lower()}",
                    mode="lines+markers",
                    line=dict(color="#E45756", width=3),
                ),
                secondary_y=True,
            )

            if comparison != "None":
                other_edu, other_out = series_for(comparison)
                timeline.add_trace(
                    go.Scatter(
                        x=other_edu["year"],
                        y=other_edu["value"],
                        name=f"{comparison} — {education_meta['name'].lower()}",
                        mode="lines",
                        line=dict(color="#4C78A8", width=2, dash="dot"),
                    ),
                    secondary_y=False,
                )
                timeline.add_trace(
                    go.Scatter(
                        x=other_out["year"],
                        y=other_out["value"],
                        name=f"{comparison} — {outcome_meta['name'].lower()}",
                        mode="lines",
                        line=dict(color="#E45756", width=2, dash="dot"),
                    ),
                    secondary_y=True,
                )

            timeline.update_layout(
                height=500,
                margin=dict(l=10, r=10, t=50, b=10),
                title=f"{main_country}: schooling and {outcome_meta['name'].lower()} since {FIRST_YEAR}",
                plot_bgcolor="white",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0),
            )
            timeline.update_xaxes(title_text="Year", gridcolor="#EDEDED")
            timeline.update_yaxes(
                title_text=f"{education_meta['name']} (%)",
                secondary_y=False,
                gridcolor="#EDEDED",
            )
            timeline.update_yaxes(
                title_text=f"{outcome_meta['name']} ({outcome_meta['unit']})",
                secondary_y=True,
                showgrid=False,
            )

            st.plotly_chart(timeline, width="stretch")

            st.markdown(
                "The blue line is schooling (left axis), the red line is the outcome "
                f"(right axis, {outcome_meta['direction']}). Where the lines move in "
                "opposite directions, the country was educating more people while poverty "
                "was falling. Gaps in the red line are years with no survey, which is the "
                "same data limitation seen in the first tab."
            )

            metric_left, metric_right = st.columns(2)
            if not main_edu.empty:
                first, last = main_edu.iloc[0], main_edu.iloc[-1]
                metric_left.metric(
                    f"{education_meta['name']} ({int(last['year'])})",
                    f"{last['value']:.1f}%",
                    f"{last['value'] - first['value']:+.1f} pts since {int(first['year'])}",
                )
            if not main_out.empty:
                first, last = main_out.iloc[0], main_out.iloc[-1]
                suffix = "%" if outcome_code == "SI.POV.DDAY" else ""
                metric_right.metric(
                    f"{outcome_meta['name']} ({int(last['year'])})",
                    f"{last['value']:,.1f}{suffix}",
                    f"{last['value'] - first['value']:+,.1f} since {int(first['year'])}",
                    delta_color="inverse" if outcome_code == "SI.POV.DDAY" else "normal",
                )

# --------------------------------------------------------------------------- #
# Tab 3 — data and limitations
# --------------------------------------------------------------------------- #

with tab_data:
    st.subheader("The table behind the chart")

    table = build_cross_section(
        education_series, outcome_series, population_series, countries, year_start, year_end
    )
    table = table[table["region"].isin(selected_regions)]

    display = table[
        ["country", "region", "income_level", "education", "education_year", "outcome", "outcome_year"]
    ].rename(
        columns={
            "country": "Country",
            "region": "Region",
            "income_level": "Income group",
            "education": education_meta["name"],
            "education_year": "Year (education)",
            "outcome": outcome_meta["name"],
            "outcome_year": "Year (outcome)",
        }
    )

    st.dataframe(display, width="stretch", hide_index=True)
    st.download_button(
        "Download this table as CSV",
        data=display.to_csv(index=False).encode("utf-8"),
        file_name="education_poverty.csv",
        mime="text/csv",
    )

    st.subheader("Limitations")
    st.markdown(
        f"""
- **Uneven timing.** Survey-based indicators are not annual. The comparison uses each
  country's latest value inside {year_start}–{year_end}, so points can be a decade apart.
- **Missing countries.** Several economies run no recent poverty survey at all and simply
  never appear. That absence is not random: fragile and conflict-affected states are the
  most likely to be missing, which probably makes the picture look better than it is.
- **Completion rates are gross ratios.** They count pupils of any age reaching the final
  grade, so a value above 100% is possible and does not mean everyone finished on time.
- **Correlation is not causation.** Wealth pays for schools and schools build wealth. This
  app can show that the two travel together; it cannot say which one moves first.
- **One number per country.** National averages hide the gap between rich and poor regions
  inside a country, which is exactly where the poverty cycle is most visible.

*{education_meta['note']}*

*{outcome_meta['note']}*
        """
    )

    st.subheader("Source")
    st.markdown(
        "All figures are fetched live from the "
        "[World Bank Indicators API (v2)](https://datahelpdesk.worldbank.org/knowledgebase/topics/125589). "
        "No API key is required and no data is stored with this app.\n\n"
        f"Indicator codes in use: `{education_code}`, `{outcome_code}`, `{POPULATION_CODE}`."
    )
