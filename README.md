# Does education break the poverty cycle?

An interactive Streamlit app built on live data from the **World Bank Indicators API (v2)**.

**Live app:** https://assignment2-vp4gefmdh3bxen7kxjd7nq.streamlit.app/
**Repository:** https://github.com/pedroaps4/assignment2

---

## Target audience

Education and finance ministries in low- and middle-income countries, plus the
parents and students affected by their decisions.

Why it matters to them: schooling is expensive, and the return arrives a decade
after the spending does. In a budget meeting it therefore competes badly against
cash transfers, roads and energy subsidies, which show results inside one
electoral cycle. This app asks whether the data justifies defending the
education line anyway — and, more usefully, **which part** of the education
system is worth defending first.

## The question

Across countries, does more schooling go together with less poverty — and does
it matter *which* stage of schooling we look at?

## The story

Open the app with **primary completion rate** selected and the cloud of points
is squashed against the right-hand edge: almost every country now gets almost
every child to the end of primary school. Primary completion barely separates
rich countries from poor ones any more, so it is a weak guide for a minister
deciding where the next euro goes.

Switch to **lower secondary completion rate** and the cloud stretches out. That
is where countries still differ enormously, and it is where the relationship
with poverty is strongest. The bar chart beside the scatter puts a number on it:
the median poverty rate in the bottom quarter of countries by lower-secondary
completion versus the top quarter.

The honest caveat is built into the app rather than hidden: this is a
correlation across countries, not proof of cause. Rich countries can afford
better schools just as easily as better schools can make a country richer.

## What the app does

| Requirement | Where it is met |
|---|---|
| Data from a free API | World Bank Indicators API (v2), no key required |
| At least one visualization | Cross-country scatter, plus a quartile bar chart and a time series |
| At least one interactive control | Six controls — see below |
| Explanation of the visualization | "What this shows" panel under the scatter, updated live |
| Note on a data limitation | Blue callout under the chart, full list in the *Data & limitations* tab |
| Clear message if the API fails | Friendly error and a "Try again" button instead of a stack trace |

### Interactive controls

1. **Education indicator** — lower secondary completion, primary completion, or adult literacy
2. **Poverty / income indicator** — extreme poverty rate or GDP per capita
3. **Year window** — which years count as "the latest available observation"
4. **Regions** — include or exclude any World Bank region
5. **Trend line** on/off, and **log scale** for GDP per capita
6. **Country picker** (plus an optional comparison country) on the time-series tab

### Indicators used

| Code | Indicator |
|---|---|
| `SE.SEC.CMPT.LO.ZS` | Lower secondary completion rate (% of relevant age group) |
| `SE.PRM.CMPT.ZS` | Primary completion rate (% of relevant age group) |
| `SE.ADT.LITR.ZS` | Adult literacy rate (% of people aged 15+) |
| `SI.POV.DDAY` | Poverty headcount ratio at $3.00/day, 2021 PPP (% of population) |
| `NY.GDP.PCAP.CD` | GDP per capita (current US$) |
| `SP.POP.TOTL` | Population (used for bubble size) |

## Limitations of the data

- **Uneven timing.** Poverty and literacy come from household surveys and
  censuses that run every few years, not annually. The scatter therefore uses
  each country's *latest available* value inside the chosen window, so one
  bubble may be from 2011 and its neighbour from 2023. Hover over a point to see
  the year behind each number.
- **Missing countries.** Some economies run no recent poverty survey at all and
  never appear. That absence is not random — fragile and conflict-affected
  states are the most likely to be missing, which probably flatters the picture.
- **Completion rates are gross ratios.** They count pupils of any age reaching
  the final grade, so values above 100% are possible and do not mean everyone
  finished on time.
- **Correlation is not causation.**
- **National averages hide internal gaps**, which is exactly where the poverty
  cycle is most visible.

## How it is built

```
app.py         Streamlit UI: controls, charts, narrative
analysis.py    Pure pandas/numpy shaping (latest-value logic, trend fitting)
worldbank.py   API client: pagination, retries, and human-readable errors
test_app.py    18 offline tests against a faked API
```

The API client follows the page counter in the response metadata (the API
returns only 50 rows per page by default, which silently truncates results),
filters out aggregates such as *World* and *Euro area*, retries transient
failures three times with a backoff, and converts every failure into a
`WorldBankError` carrying a sentence that is safe to show a user. Responses are
cached for six hours with `st.cache_data`, which keeps the app fast and avoids
hammering a free public service.

## Run it locally

```bash
git clone <your-repo-url>
cd <your-repo-folder>
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Run the tests

```bash
pip install -r requirements-dev.txt
python -m pytest test_app.py -q
```

The tests need no internet: they fake the World Bank API, including the failure
modes (HTTP 500, timeout, connection error, malformed JSON, rejected indicator
code) and the awkward data cases (nulls, aggregates, sparse surveys).

## Deploy

Push to GitHub, then go to [share.streamlit.io](https://share.streamlit.io),
connect the repository and set the main file to `app.py`. No secrets or
environment variables are needed.

**No API keys or passwords are used anywhere in this project.** The World Bank
Indicators API is open and unauthenticated.

## AI tools used

> Edit this section so it matches what your group actually did — the marks are
> for being specific and honest, not for using less.

- **Claude (Anthropic)** — helped structure the app, write the World Bank API
  client and the test suite, and draft this README. We verified the indicator
  codes ourselves against the World Bank documentation, chose the question and
  the target audience, reviewed all generated code, and ran the app and tests
  before handing in.
- **GitHub Copilot / ChatGPT / others** — _add or delete as appropriate._

## Data source

World Bank Indicators API (v2) —
<https://datahelpdesk.worldbank.org/knowledgebase/topics/125589>
Data is licensed CC BY 4.0 by the World Bank.
