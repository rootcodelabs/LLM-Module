"""
Retrieval Evaluation Script — tests semantic search accuracy across 40+ queries.

Usage:
    python eval_search.py
    python eval_search.py --ruuter-url http://localhost:8086
    python eval_search.py --output results.json   # also save detailed JSON results

What it does:
    1. Sends each query to POST /rag-search/api-tools/search
    2. Checks if the top result matches the expected endpoint name
    3. Prints a detailed pass/fail table
    4. Outputs accuracy %, average cosine score, and a list of failures
"""

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import requests

DEFAULT_RUUTER_URL = "http://localhost:8086"
SEARCH_ENDPOINT = "/rag-search/api-tools/search"

# ============================================================================
# Evaluation Dataset
# Format: (query, expected_endpoint_name or None for "no match expected")
# ============================================================================
EVAL_QUERIES = [
    # --- get_national_holidays ---
    ("What are the national holidays in Estonia?", "get_national_holidays"),
    (
        "What are the upcoming national holidays in Estonia this year?",
        "get_national_holidays",
    ),
    ("List all public days off in Estonia this year", "get_national_holidays"),
    ("Show me national holidays for Estonia", "get_national_holidays"),
    ("What are the official Estonian public holidays?", "get_national_holidays"),
    # --- get_school_holidays ---
    ("When are the school holidays in Estonia?", "get_school_holidays"),
    ("What are the school term breaks in Estonia?", "get_school_holidays"),
    ("When does school summer break start in Estonia?", "get_school_holidays"),
    # --- get_current_electricity_price ---
    (
        "What is the current electricity price in Estonia?",
        "get_current_electricity_price",
    ),
    (
        "How much does electricity cost right now in Estonia?",
        "get_current_electricity_price",
    ),
    (
        "Show me the real-time energy market price in Estonia",
        "get_current_electricity_price",
    ),
    (
        "What is the spot price for electricity in Estonia today?",
        "get_current_electricity_price",
    ),
    # --- get_electricity_price_history ---
    (
        "Show me the electricity price history for Estonia over the last month",
        "get_electricity_price_history",
    ),
    (
        "Show me historical electricity prices for Estonia in January 2024",
        "get_electricity_price_history",
    ),
    (
        "Fetch the electricity price history for Estonia for the past 30 days",
        "get_electricity_price_history",
    ),
    # --- get_unemployment_rate ---
    ("What is the unemployment rate in Estonia?", "get_unemployment_rate"),
    ("How many people are unemployed in Estonia this year?", "get_unemployment_rate"),
    ("Show me the latest jobless statistics for Estonia", "get_unemployment_rate"),
    ("What percentage of Estonians are unemployed?", "get_unemployment_rate"),
    # --- get_weather_forecast ---
    ("What is the weather forecast for Tallinn tomorrow?", "get_weather_forecast"),
    ("What is the weather forecast for Tartu next week?", "get_weather_forecast"),
    (
        "What is the weather forecast and temperature for Pärnu this weekend?",
        "get_weather_forecast",
    ),
    ("Show me the 7-day weather forecast for Tallinn", "get_weather_forecast"),
    (
        "What are the weather conditions including wind speed in Narva today?",
        "get_weather_forecast",
    ),
    # --- get_exchange_rates ---
    ("What is the EUR to USD exchange rate today?", "get_exchange_rates"),
    ("Show me the current currency exchange rates", "get_exchange_rates"),
    ("What is the exchange rate from EUR to Swedish krona?", "get_exchange_rates"),
    ("What are the latest forex rates for EUR?", "get_exchange_rates"),
    # --- get_country_information ---
    (
        "Get country information for Estonia including its capital city",
        "get_country_information",
    ),
    (
        "What country information is available for Estonia, including official languages?",
        "get_country_information",
    ),
    ("Fetch country details and facts about Estonia", "get_country_information"),
    ("What is the country profile for Estonia?", "get_country_information"),
    # --- get_ip_geolocation ---
    ("What is the geolocation of IP address 88.196.123.45?", "get_ip_geolocation"),
    (
        "Geolocate this IP address and find which country it belongs to",
        "get_ip_geolocation",
    ),
    ("Find the geolocation of an IP address", "get_ip_geolocation"),
    # --- get_current_time_by_timezone ---
    ("What time is it in Tallinn right now?", "get_current_time_by_timezone"),
    (
        "What is the current time in the Europe/Tallinn timezone?",
        "get_current_time_by_timezone",
    ),
    (
        "What is the current time in Estonia and is it in daylight saving timezone?",
        "get_current_time_by_timezone",
    ),
    # --- get_air_quality ---
    ("What is the air quality in Tallinn today?", "get_air_quality"),
    ("Show me PM2.5 pollution levels in Tallinn", "get_air_quality"),
    ("Is the air quality good in Tartu right now?", "get_air_quality"),
    # --- get_address_geocoding ---
    ("Find the coordinates for Viru 4, Tallinn", "get_address_geocoding"),
    (
        "Get the geocoding coordinates for Kadriorg Park in Tallinn",
        "get_address_geocoding",
    ),
    (
        "What are the GPS coordinates of this address in Estonia?",
        "get_address_geocoding",
    ),
    # --- get_gdp_statistics ---
    ("What is Estonia's GDP this year?", "get_gdp_statistics"),
    ("What is the economic output of Estonia?", "get_gdp_statistics"),
    (
        "Show me the GDP growth rate of Estonia over the past 5 years",
        "get_gdp_statistics",
    ),
    # --- get_population_data ---
    ("What is the total population of Estonia?", "get_population_data"),
    ("What is the total population data for Estonia?", "get_population_data"),
    ("What is the population growth rate of Estonia?", "get_population_data"),
    # --- get_word_definition ---
    ("Get the word definition for ephemeral", "get_word_definition"),
    ("Look up the word definition for resilient", "get_word_definition"),
    ("Fetch the dictionary definition of the word sustainable", "get_word_definition"),
    # --- get_public_transport_stops ---
    ("Where are the bus stops in Tallinn?", "get_public_transport_stops"),
    (
        "Show me public transport stops near Tartu city centre",
        "get_public_transport_stops",
    ),
    # --- get_average_salary_statistics ---
    ("What is the average salary in Estonia?", "get_average_salary_statistics"),
    ("How much do people earn in Estonia on average?", "get_average_salary_statistics"),
    (
        "What is the average monthly wage in the IT sector in Estonia?",
        "get_average_salary_statistics",
    ),
    # --- get_estonian_company_info ---
    (
        "Look up company registration number 10000000 in Estonia",
        "get_estonian_company_info",
    ),
    (
        "Find details about an Estonian company called Tallinn IT OÜ",
        "get_estonian_company_info",
    ),
    (
        "Is this Estonian company still active in the business registry?",
        "get_estonian_company_info",
    ),
    # --- get_reverse_geocoding ---
    (
        "Reverse geocode the coordinates 59.4370, 24.7536 to get the street address",
        "get_reverse_geocoding",
    ),
    ("Convert GPS coordinates to a street address in Tallinn", "get_reverse_geocoding"),
    (
        "Reverse geocoding for latitude 58.3780 longitude 26.7290 in Tartu",
        "get_reverse_geocoding",
    ),
    # --- NEGATIVE queries — should return NO matching results ---
    ("Who is the Prime Minister of Estonia?", None),
    ("What is the best restaurant in Tallinn?", None),
    ("Tell me a random fact about Estonia", None),
    ("What is the meaning of life?", None),
    ("Book me a flight to London", None),
    ("Can you translate this text to Estonian?", None),
    ("What are the visa requirements to visit Estonia?", None),
    ("How do I apply for an Estonian e-Residency?", None),
    ("What is the history of Tallinn Old Town?", None),
    ("Give me a poem about Estonia", None),
]


def search(ruuter_url: str, query: str, top_k: int = 3) -> Optional[dict]:
    """Send a search query and return the parsed response."""
    url = f"{ruuter_url}{SEARCH_ENDPOINT}"
    try:
        response = requests.post(
            url,
            json={"query": query, "top_k": top_k, "environment": "production"},
            timeout=30,
        )
        if response.status_code == 200:
            body = response.json()
            # Handle Ruuter wrapper: body may be {"response": {...}}
            return body.get("response", body)
        return None
    except Exception:
        return None


def evaluate(ruuter_url: str, delay: float = 0.5) -> list:
    """Run all evaluation queries and return results."""
    results = []
    for query, expected in EVAL_QUERIES:
        response = search(ruuter_url, query)

        if response is None:
            results.append(
                {
                    "query": query,
                    "expected": expected,
                    "got": "ERROR",
                    "cosine_score": None,
                    "confidence": None,
                    "pass": False,
                    "error": "Request failed",
                }
            )
            time.sleep(delay)
            continue

        top_results = response.get("results", [])
        top = top_results[0] if top_results else None

        got_name = top["name"] if top else None
        cosine_score = top["cosine_score"] if top else None
        rrf_score = top["rrf_score"] if top else None
        confidence = top["confidence"] if top else None

        # Determine pass/fail
        if expected is None:
            # Negative query: should return no HIGH confidence result
            passed = got_name is None or confidence != "high"
        else:
            passed = got_name == expected

        results.append(
            {
                "query": query,
                "expected": expected,
                "got": got_name,
                "cosine_score": cosine_score,
                "rrf_score": rrf_score,
                "confidence": confidence,
                "pass": passed,
            }
        )

        time.sleep(delay)

    return results


def print_report(results: list) -> None:
    """Print evaluation results table and summary."""
    PASS = "✅"
    FAIL = "❌"
    SKIP = "⚠️ "

    print(f"\n{'=' * 100}")
    print(f"{'RETRIEVAL EVALUATION REPORT':^100}")
    print(f"{'=' * 100}")
    print(
        f"{'#':<4} {'Query':<48} {'Expected':<28} {'Got':<28} {'Cosine':>7} {'RRF':>9}  {'Result'}"
    )
    print(f"{'-' * 100}")

    for i, r in enumerate(results, 1):
        query = r["query"][:46] + ".." if len(r["query"]) > 46 else r["query"]
        expected = (r["expected"] or "(none)")[:26]
        got = (r["got"] or "(none)")[:26]
        cosine = (
            f"{r['cosine_score']:.4f}" if r["cosine_score"] is not None else "  -   "
        )
        rrf = f"{r['rrf_score']:.6f}" if r["rrf_score"] is not None else "    -    "
        verdict = PASS if r["pass"] else FAIL

        # Highlight negative query failures
        if r["expected"] is None and r["got"] is not None and r["confidence"] == "high":
            verdict = FAIL + " FALSE POSITIVE"

        print(
            f"{i:<4} {query:<48} {expected:<28} {got:<28} {cosine:>7} {rrf:>9}  {verdict}"
        )

    # Summary stats
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed

    positives = [r for r in results if r["expected"] is not None]
    negatives = [r for r in results if r["expected"] is None]
    positive_pass = sum(1 for r in positives if r["pass"])
    negative_pass = sum(1 for r in negatives if r["pass"])

    scores = [
        r["cosine_score"]
        for r in results
        if r["cosine_score"] is not None and r["pass"]
    ]
    avg_cosine = sum(scores) / len(scores) if scores else 0.0
    rrf_scores = [
        r["rrf_score"] for r in results if r["rrf_score"] is not None and r["pass"]
    ]
    avg_rrf = sum(rrf_scores) / len(rrf_scores) if rrf_scores else 0.0

    print(f"\n{'=' * 100}")
    print("SUMMARY")
    print(f"{'=' * 100}")
    print(f"  Overall Accuracy:       {passed}/{total}  ({100 * passed / total:.1f}%)")
    print(
        f"  Positive Queries:       {positive_pass}/{len(positives)}  ({100 * positive_pass / len(positives):.1f}%)"
    )
    print(
        f"  Negative Queries:       {negative_pass}/{len(negatives)}  ({100 * negative_pass / len(negatives):.1f}%)"
    )
    print(
        f"  Avg Cosine (correct):   {avg_cosine:.4f}  (threshold: min={0.40}, high={0.60})"
    )
    print(f"  Avg RRF    (correct):   {avg_rrf:.6f}")
    print("\n  Target: >90% overall accuracy, avg cosine >0.55")

    if failed > 0:
        print(f"\n  FAILURES ({failed}):")
        for r in results:
            if not r["pass"]:
                print(f"     '{r['query']}'")
                print(
                    f"       Expected: {r['expected']}  |  Got: {r['got']}  |  Cosine: {r['cosine_score']}  |  RRF: {r['rrf_score']}"
                )

    print(f"{'=' * 100}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate semantic search retrieval accuracy"
    )
    parser.add_argument("--ruuter-url", default=DEFAULT_RUUTER_URL)
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Seconds between requests"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Save results to JSON file"
    )
    args = parser.parse_args()

    print(f"\nStarting evaluation — {len(EVAL_QUERIES)} queries")
    print(f"Target: {args.ruuter_url}{SEARCH_ENDPOINT}\n")

    results = evaluate(args.ruuter_url, args.delay)
    print_report(results)

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Detailed results saved to: {output_path}")


if __name__ == "__main__":
    main()
