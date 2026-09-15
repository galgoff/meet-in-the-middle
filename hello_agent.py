"""
hello_agent.py — Week 0: a minimal, framework-free tool-use loop.

No LangGraph, no agent framework — just the Anthropic API and one tool,
so you can see exactly what "agentic" means mechanically: the ReAct loop
(Reason -> Act -> Observe), before any framework hides it from you.
"""

import os
import json
import requests
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()  # reads .env into environment variables

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-haiku-4-5-20251001"  # cheap + fast — right-sized for a trivial task

# --- the tool's schema: what Claude sees -----------------------------------

TOOLS = [
    {
        "name": "geocode_city",
        "description": "Look up the latitude/longitude of a city by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "A city name, e.g. 'Lisbon'"}
            },
            "required": ["city"],
        },
    }
]

# --- the tool's real implementation: what actually runs --------------------

def geocode_city(city: str) -> dict:
    """Real lookup via OpenStreetMap's free Nominatim API — no key needed."""
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city, "format": "json", "limit": 1},
        headers={"User-Agent": "meet-in-the-middle-learning-project (galgof@gmail.com)"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return {"error": f"No match found for '{city}'"}
    match = results[0]
    return {
        "city": city,
        "lat": float(match["lat"]),
        "lon": float(match["lon"]),
        "display_name": match["display_name"],
    }

# --- the raw ReAct loop ------------------------------------------------------

def run_agent(user_message: str):
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=1024, tools=TOOLS, messages=messages,
        )

        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text":
                    print("\nClaude:", block.text)
            return

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\n[agent] calling {block.name}({block.input})")
                if block.name == "geocode_city":
                    result = geocode_city(**block.input)
                else:
                    result = {"error": f"unknown tool {block.name}"}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        # hand results back to Claude and loop — this is "Observe" feeding
        # into the next "Reason" step
        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run_agent(
        "What are the coordinates of Lisbon and Tel Aviv? "
        "Also tell me roughly how far apart they are in kilometers."
    )
