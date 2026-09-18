"""Data shaping that sits between the API client and the charts.

Kept free of Streamlit so it can be tested on its own (see test_app.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def latest_in_window(series: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Keep the most recent observation per country inside [start, end].

    Survey-based indicators are not annual, so asking for "the 2023 value" would
    throw away most countries. Asking for "the newest value since 2010" keeps
    them, at the cost of comparing slightly different years.
    """
    window = series[series["year"].between(start, end)]
    if window.empty:
        return window.copy()
    return window.sort_values("year").groupby("iso3", as_index=False).tail(1)


def build_cross_section(
    education: pd.DataFrame,
    outcome: pd.DataFrame,
    population: pd.DataFrame,
    countries: pd.DataFrame,
    start: int,
    end: int,
) -> pd.DataFrame:
    """One row per country: latest education value against latest outcome value.

    The inner joins are deliberate: a country only enters the comparison if it
    has both indicators in the window, and if it is a real economy rather than
    an aggregate.
    """
    edu = latest_in_window(education, start, end).rename(
        columns={"value": "education", "year": "education_year"}
    )
    out = latest_in_window(outcome, start, end).rename(
        columns={"value": "outcome", "year": "outcome_year"}
    )
    pop = latest_in_window(population, start, end).rename(columns={"value": "population"})

    if edu.empty or out.empty:
        return pd.DataFrame(
            columns=[
                "iso3", "education", "education_year", "outcome", "outcome_year",
                "population", "country", "region", "income_level",
            ]
        )

    merged = (
        edu.merge(out, on="iso3", how="inner")
        .merge(pop[["iso3", "population"]], on="iso3", how="left")
        .merge(countries, on="iso3", how="inner")
    )

    if merged.empty:
        return merged

    # A missing population only affects bubble size, so fall back to the median
    # rather than dropping an otherwise valid country.
    median_population = merged["population"].median()
    merged["population"] = merged["population"].fillna(
        median_population if pd.notna(median_population) else 1.0
    )

    return merged.sort_values("country", ignore_index=True)


def fit_trend(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Least-squares line through the points, plus the Pearson correlation."""
    slope, intercept = np.polyfit(x, y, 1)
    line_x = np.linspace(x.min(), x.max(), 100)
    return line_x, slope * line_x + intercept, float(np.corrcoef(x, y)[0, 1])
