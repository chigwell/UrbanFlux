"""
nemotron.py
───────────
Urban planning assistant powered by Nvidia Nemotron via fal.ai.

Takes a user planning goal (e.g. "10% more buildings in the highlighted area")
and the JSON response from the UrbanFlux /impact endpoint, and returns a
structured planning recommendation.

Optionally enriches the prompt with live borough data from the
/borough-data-test endpoint (latest rows by theme).

Usage
─────
Direct (hardcoded example data):
    python nemotron.py

From another module:
    from nemotron import get_planning_recommendation
    result = get_planning_recommendation(impact_response, user_goal)
    print(result["recommendation"])

Environment
───────────
Requires FAL_KEY in environment or .env file.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

import fal_client
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOROUGH_DATA_URL = "https://api.urbanflux.london/borough-data-test"

# Themes we trust enough to include in the Nemotron prompt.
# Safety and health are excluded due to data quality issues (garbled dates,
# misclassified rows).
TRUSTED_THEMES = {"housing", "transport", "planning_land", "socioeconomic", "environment"}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are UrbanFlux, an AI urban planning assistant for London.

You are given real data about a selected area: its approximate population, size, borough, and a set of impact metrics calculated from Census 2021, TfL, and London Datastore sources. Where available, you are also given the latest real data rows for that borough by theme.

When the user describes a planning goal — such as increasing housing density, reducing traffic, improving green space, or improving air quality — you must:

1. Acknowledge the goal clearly and concisely.
2. Identify which of the provided impact metrics and borough data rows are most relevant to that goal.
3. Recommend specific, actionable replanning parameters (road width, speed limit, cycle lanes, green space percentage) that would help achieve it.
4. Quantify the expected impact where possible, referencing the real data provided.
5. Flag any trade-offs or constraints (e.g. increasing building density may reduce green space).

Always ground your response in the data provided. Do not invent statistics. If the data does not cover something, say so plainly.

Be concise, professional, and direct. You are speaking to an urban planner or city official, not a general audience. Avoid hedging language. Respond in plain English, no markdown."""


# ---------------------------------------------------------------------------
# Borough data fetcher
# ---------------------------------------------------------------------------

def _fetch_borough_data(lat: float, lon: float) -> dict | None:
    params = urllib.parse.urlencode({"lat": lat, "lon": lon})
    url = f"{BOROUGH_DATA_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "UrbanFlux/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  Borough data error: {e}")
        return None


def _format_latest_rows(latest_rows: list[dict]) -> str:
    """Format latest_rows_by_theme into a readable prompt block."""
    lines = []
    for row in latest_rows:
        theme = row.get("theme", "")
        if theme not in TRUSTED_THEMES:
            continue
        preview = row.get("source_row_preview", "").strip()
        date_start = row.get("date_start") or ""
        date_end = row.get("date_end") or ""
        date_str = f"{date_start} – {date_end}".strip(" –")
        if preview:
            lines.append(f"  [{theme}] {date_str}: {preview}")
    return "\n".join(lines) if lines else "  (none available)"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _format_metrics(metrics: list[dict]) -> str:
    lines = []
    for m in metrics:
        lines.append(
            f"  - {m['improved_metric']}: {m['improved_value']} "
            f"(delta: {m['delta']})"
        )
    return "\n".join(lines)


def _build_prompt(impact: dict, user_goal: str, borough_data: dict | None) -> str:
    borough = (
        impact.get("note", "")
        .replace("Grounded in real ", "")
        .replace(" data via London Datastore", "")
    )
    population = impact.get("approximate_population", 0)
    area_km2 = impact.get("area_km2", 0)
    metrics = impact.get("metrics", [])

    prompt = f"""Area data:
- Borough: {borough}
- Population: {population:,}
- Area: {area_km2} km²

Impact metrics (from LSOA intersection + London Datastore):
{_format_metrics(metrics)}
"""

    if borough_data:
        latest_rows = borough_data.get("latest_rows_by_theme", [])
        prompt += f"""
Latest real borough data rows (selected trusted themes):
{_format_latest_rows(latest_rows)}
"""

    prompt += f"\nUser goal: {user_goal}"
    return prompt


# ---------------------------------------------------------------------------
# Queue update handler
# ---------------------------------------------------------------------------

def _on_queue_update(update: object) -> None:
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"  [fal] {log['message']}")


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def get_planning_recommendation(
    impact_response: dict,
    user_goal: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """
    Call Nemotron with the impact data and user goal.

    Parameters
    ----------
    impact_response:
        The JSON response body from POST /impact.
    user_goal:
        Free-text planning goal from the user.
    lat, lon:
        Optional centroid coordinates of the selected polygon.
        If provided, live borough data is fetched and included in the prompt.

    Returns
    -------
    dict with keys:
        recommendation  str   Nemotron's planning recommendation
        user_goal       str   Echo of the input goal
        borough         str   Borough name
        borough_data    dict  Raw borough data fetched (or None)
        timestamp       str   ISO timestamp of the call
    """
    borough_data = None
    if lat is not None and lon is not None:
        print(f"Fetching live borough data for ({lat}, {lon})...")
        borough_data = _fetch_borough_data(lat, lon)
        if borough_data:
            print(f"  Borough: {borough_data.get('borough', {}).get('name', 'unknown')}")
        else:
            print("  Borough data unavailable — proceeding without it.")

    prompt = _build_prompt(impact_response, user_goal, borough_data)

    print("\nCalling Nemotron...\n")
    result = fal_client.subscribe(
        "openrouter/router",
        arguments={
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "system_prompt": SYSTEM_PROMPT,
            "prompt": prompt,
        },
        with_logs=True,
        on_queue_update=_on_queue_update,
    )

    recommendation = (
        result.get("output")
        or result.get("text")
        or result.get("choices", [{}])[0].get("message", {}).get("content")
        or str(result)
    )

    borough = (
        impact_response.get("note", "")
        .replace("Grounded in real ", "")
        .replace(" data via London Datastore", "")
    )

    return {
        "recommendation": recommendation,
        "user_goal": user_goal,
        "borough": borough,
        "borough_data": borough_data,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Example / smoke test
# ---------------------------------------------------------------------------

EXAMPLE_IMPACT_RESPONSE = {
    "approximate_population": 2139,
    "area_km2": 0.895,
    "note": "Grounded in real Westminster data via London Datastore",
    "metrics": [
        {
            "improved_metric": "Cycling mode share",
            "improved_value": "+3.2 percentage points",
            "delta": "+3.2pp vs baseline",
            "source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
        },
        {
            "improved_metric": "Road NOₓ emissions",
            "improved_value": "-12%",
            "delta": "-12% vs current speed limit",
            "source": "https://data.london.gov.uk/dataset/london-atmospheric-emissions-inventory--laei--2019",
        },
        {
            "improved_metric": "PM2.5 exposure",
            "improved_value": "16.51 µg/m³",
            "delta": "-1.44 µg/m³ (from real borough data (17.95 µg/m³))",
            "source": "https://data.london.gov.uk/dataset/pm2-5-map-and-exposure-data",
        },
        {
            "improved_metric": "Summer peak temperature",
            "improved_value": "-0.75 °C",
            "delta": "-0.75 °C vs no green space change",
            "source": "https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/climate-change/urban-greening",
        },
        {
            "improved_metric": "Mental health prevalence",
            "improved_value": "176.1 per 1,000 residents",
            "delta": "-10% (real Westminster rate)",
            "source": "https://data.london.gov.uk/dataset/prevalence-common-mental-health-problems-borough",
        },
        {
            "improved_metric": "Premature deaths prevented (active travel)",
            "improved_value": "2.0 lives/year",
            "delta": "+2.0 vs baseline",
            "source": "https://www.euro.who.int/en/health-topics/environment-and-health/Transport-and-health/activities/quantifying-health-impacts-of-transport/heat-tool",
        },
        {
            "improved_metric": "Estimated population affected",
            "improved_value": "2,139",
            "delta": "N/A",
            "source": "https://www.nomisweb.co.uk/output/census/2021/census2021-ts001.zip",
        },
    ],
}

# Centroid of the Canary Wharf test polygon
EXAMPLE_LAT = 51.503
EXAMPLE_LON = -0.015

EXAMPLE_GOAL = "We want 10% more residential buildings in the highlighted area."


if __name__ == "__main__":
    now = datetime.now()
    print(f"UrbanFlux Nemotron  —  {now.strftime('%A, %B %d, %Y')} {now.strftime('%H:%M:%S')}\n")

    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        print("ERROR: FAL_KEY not set in environment or .env file.")
        raise SystemExit(1)
    print("FAL_KEY: set ✓\n")
    print(f"Goal: {EXAMPLE_GOAL}\n")

    output = get_planning_recommendation(
        EXAMPLE_IMPACT_RESPONSE,
        EXAMPLE_GOAL,
        lat=EXAMPLE_LAT,
        lon=EXAMPLE_LON,
    )

    print("\n" + "─" * 60)
    print("RECOMMENDATION")
    print("─" * 60)
    print(output["recommendation"])
    print("─" * 60)
    print(f"Borough: {output['borough']}")
    print(f"Timestamp: {output['timestamp']}")