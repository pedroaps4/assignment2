"""Thin client for the World Bank Indicators API (v2).

Docs: https://datahelpdesk.worldbank.org/knowledgebase/topics/125589

This module only knows about HTTP and pandas. It never touches Streamlit, so it
can be tested on its own. Every failure path raises ``WorldBankError`` with a
message that is safe to show to a user, which lets the app display one clear
sentence instead of a stack trace.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://api.worldbank.org/v2"

# The API defaults to 50 results per page, which silently truncates everything.
# We ask for large pages and still follow the page counter in the metadata.
PER_PAGE = 20_000
TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 3

# Aggregates such as "World", "Euro area" or "Low income" are returned by the
# /country endpoint alongside real economies. They all carry this region id.
AGGREGATE_REGION_ID = "NA"


class WorldBankError(RuntimeError):
    """The API was unreachable, rejected the request, or returned nothing usable."""


def _request(url: str, params: dict[str, Any]) -> Any:
    """GET one page, retrying transient failures. Returns parsed JSON."""
    problem = "the reason is unknown"

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            problem = f"the request timed out after {TIMEOUT_SECONDS} seconds"
        except requests.exceptions.ConnectionError:
            problem = "the connection failed (no internet, or the service is down)"
        except requests.exceptions.RequestException as exc:
            problem = f"the request failed ({type(exc).__name__})"
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    problem = "the response was not valid JSON"
            else:
                problem = f"the API replied with HTTP {response.status_code}"

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(1.5 * (attempt + 1))  # simple backoff

    raise WorldBankError(f"Could not reach the World Bank API: {problem}.")


def _unwrap(payload: Any) -> tuple[dict, list]:
    """Split a World Bank response into (metadata, records).

    A successful response is ``[metadata, [records...]]``. When a query is valid
    but matches nothing, the second element is ``None``. An invalid query comes
    back as ``[{"message": [...]}]``.
    """
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        messages = payload[0].get("message")
        if messages:
            detail = messages[0].get("value", "no detail given")
            raise WorldBankError(f"The World Bank API rejected the request: {detail}")

        if len(payload) >= 2:
            records = payload[1]
            return payload[0], (records if isinstance(records, list) else [])

    raise WorldBankError("The World Bank API returned a response in an unexpected shape.")


def _get_all(path: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Fetch every page of an endpoint and return the concatenated records."""
    url = f"{BASE_URL}/{path}"
    base_params = {"format": "json", "per_page": PER_PAGE, **(params or {})}

    records: list[dict] = []
    page = 1

    while True:
        metadata, chunk = _unwrap(_request(url, {**base_params, "page": page}))
        records.extend(item for item in chunk if isinstance(item, dict))

        try:
            total_pages = int(metadata.get("pages") or 1)
        except (TypeError, ValueError):
            total_pages = 1

        if page >= total_pages or not chunk:
            break
        page += 1

    return records


def fetch_countries() -> pd.DataFrame:
    """Return one row per real economy, with its region and income group.

    Columns: iso3, country, region, income_level.
    """
    records = _get_all("country")

    rows = []
    for item in records:
        region = item.get("region") or {}
        if region.get("id") == AGGREGATE_REGION_ID:
            continue  # drop "World", "OECD members", income groups, etc.

        iso3 = (item.get("id") or "").strip()
        name = (item.get("name") or "").strip()
        if not iso3 or not name:
            continue

        rows.append(
            {
                "iso3": iso3,
                "country": name,
                "region": (region.get("value") or "Unknown").strip(),
                "income_level": ((item.get("incomeLevel") or {}).get("value") or "Unknown").strip(),
            }
        )

    countries = pd.DataFrame(rows, columns=["iso3", "country", "region", "income_level"])
    if countries.empty:
        raise WorldBankError("The World Bank API returned no countries.")

    return countries.sort_values("country", ignore_index=True)


def fetch_indicator(indicator_code: str, start_year: int, end_year: int) -> pd.DataFrame:
    """Return the long-format series for one indicator, for all economies.

    Columns: iso3, year, value. Rows with no observation are dropped, so a
    country-year that the World Bank has never measured simply does not appear.
    """
    records = _get_all(
        f"country/all/indicator/{indicator_code}",
        {"date": f"{start_year}:{end_year}"},
    )

    rows = []
    for item in records:
        if item.get("value") is None:
            continue

        year = str(item.get("date") or "")
        if not year.isdigit():
            continue  # quarterly/monthly rows exist for some series; skip them

        iso3 = (item.get("countryiso3code") or "").strip()
        if not iso3:
            continue

        rows.append({"iso3": iso3, "year": int(year), "value": item["value"]})

    series = pd.DataFrame(rows, columns=["iso3", "year", "value"])
    if series.empty:
        raise WorldBankError(
            f"The World Bank API returned no data for indicator {indicator_code} "
            f"between {start_year} and {end_year}."
        )

    series["value"] = pd.to_numeric(series["value"], errors="coerce")
    return series.dropna(subset=["value"]).reset_index(drop=True)
