"""
intake.py — Week 2: multi-party intake CLI.

Each person submits independently, whenever they get to it — no live
session, no waiting on each other. The trip auto-completes once
`expected_parties` submissions are in; the organizer can also lock it
early if someone's gone quiet (see db.lock_trip for why that's
one-way). Run with no arguments for usage.

Input validation lives here, at the CLI layer, not in db.add_submission:
- origin_city is checked against the real geocoder (tools.geocode_city)
  before it's ever stored. A miss (e.g. "Londom") is rejected and
  re-prompted. An AMBIGUOUS match requires explicit confirmation before
  it's accepted — a real run surfaced "London, en" silently resolving to
  "London, Svalbard, Norge" (a real place Nominatim also calls London),
  which is exactly the failure mode a printed warning alone doesn't
  reliably catch. The confirmation prompt shows the alternatives too, so
  there's enough context to actually judge the match. Declining
  re-prompts with a hint to add more detail. Once accepted, the stored
  value is the resolved, fully-qualified place name — not the raw typed
  text — so the same ambiguity can't silently resurface when
  midpoint_agent.py re-geocodes it later.
- budget_ceiling_usd is rejected (and re-prompted) if it's non-numeric or
  not a positive number; blank stays allowed, since "not sure yet" is a
  legitimate answer.
- nationality is checked against a curated country-name list
  (countries.py) — same disclosed, hand-maintained-list pattern already
  used for ground_travel.py's border rules, not a real reference data
  source. Blank stays allowed.
date_flexibility and hard_constraints stay free-text; there's no
structural check that makes sense for them beyond the existing
passport-pattern scrub in db.add_submission.
"""

import sys

from countries import normalize_country
from db import TripError, add_submission, create_trip, get_submissions, lock_trip, trip_status_summary
from tools import geocode_city

USAGE = """\
Usage:
  python3 intake.py create <expected_parties>
      Start a new trip for N people. Prints the trip id — share it with
      everyone who needs to submit.

  python3 intake.py submit <trip_id>
      Interactively submit (or update, before the trip completes) one
      person's info: name, origin city, date flexibility, budget
      ceiling, nationality, hard constraints. Origin city and
      nationality are both validated before they're accepted; an
      ambiguous city match requires your explicit confirmation.

  python3 intake.py status <trip_id>
      Show who has submitted so far and whether the trip is complete.

  python3 intake.py lock <trip_id>
      Finalize the trip now, even if not everyone has submitted yet.
      Irreversible — no further submissions will be accepted after.
"""


def _prompt(label: str, required: bool = True) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value
        print(f"  ({label} is required)")


def _classify_city_input(city: str) -> tuple[str, str]:
    """Pure function, no I/O of its own beyond the geocode call: given a
    raw city string, classify what the geocoder makes of it. Returns
    (status, message): for 'ok', message is the resolved display name;
    for 'error', the geocoder's error text; for 'ambiguous', the top
    match plus its alternatives, so there's enough context to judge
    whether it's right — the clean canonical name to store is re-derived
    separately (see _resolve_origin_city) rather than parsed back out of
    this display string. Kept separate from the input()-driven prompt
    loop below so this logic is unit-testable without stubbing stdin."""
    geo = geocode_city(city)
    if "error" in geo:
        return "error", geo["error"]
    if geo.get("ambiguous"):
        alts = ", ".join(a["display_name"] for a in geo.get("alternatives", []))
        message = geo["display_name"] + (f" (also matches: {alts})" if alts else "")
        return "ambiguous", message
    return "ok", geo.get("display_name", city)


def _accepts_ambiguous_match(response: str) -> bool:
    """Pure function: interpret a yes/no confirmation. Only an explicit
    'y'/'yes' counts as acceptance — anything else, including blank, is
    'no'. Accepting a low-confidence match by default is exactly how
    'London, en' silently became a submission for Svalbard, Norway."""
    return response.strip().lower() in ("y", "yes")


def _resolve_origin_city() -> str:
    """Keep prompting until the city geocodes to something confirmed.
    A clean ('ok') match is accepted automatically but echoed back so
    it's visible what was matched. An ambiguous match is shown — top
    match plus alternatives — and must be explicitly confirmed;
    declining re-prompts with a hint to add more detail rather than
    silently guessing. Returns the resolved, fully-qualified place name,
    not the raw input, so the same ambiguity can't resurface later when
    midpoint_agent.py re-geocodes the stored value."""
    while True:
        city = _prompt("Origin city (e.g. 'Lisbon, Portugal')")
        status, message = _classify_city_input(city)
        if status == "error":
            print(f"  Couldn't find '{city}': {message}")
            print("  Check the spelling, or add a country for clarity, e.g. 'Springfield, Illinois'.")
            continue
        if status == "ambiguous":
            print(f"  '{city}' is ambiguous — {message}")
            response = input("  Is the first one the right city? [y/N]: ")
            if not _accepts_ambiguous_match(response):
                print(
                    "  Try again with more detail — a country or region usually resolves it, "
                    "e.g. 'London, England' or 'London, UK'."
                )
                continue
            # Re-derive the clean canonical name for storage. geocode_city is
            # disk-cached, so this is a cache hit, not a second network call.
            geo = geocode_city(city)
            return geo["display_name"]
        print(f"  -> matched: {message}")
        return message


def _classify_budget_input(raw: str) -> tuple[str, float | None, str]:
    """Pure function: classify a raw budget string. Returns
    (status, value, message). status 'ok' means value is either a
    positive float or None (blank/unsure, which is a legitimate answer);
    status 'invalid' means value is None and message explains why, so
    the caller can re-prompt instead of silently losing the input."""
    if not raw:
        return "ok", None, ""
    try:
        value = float(raw)
    except ValueError:
        return "invalid", None, f"'{raw}' doesn't look like a number — try digits only, e.g. 1200"
    if value <= 0:
        return "invalid", None, "Budget ceiling must be a positive number."
    return "ok", value, ""


def _prompt_budget() -> float | None:
    while True:
        raw = _prompt("Budget ceiling in USD (numbers only, blank if unsure)", required=False)
        status, value, message = _classify_budget_input(raw)
        if status == "invalid":
            print(f"  {message}")
            continue
        return value


def _classify_nationality_input(raw: str) -> tuple[str, str]:
    """Pure function: classify a non-blank raw nationality string
    against countries.normalize_country. Returns (status, result) where
    status 'ok' means result is the canonical country name, and 'error'
    means result is a message explaining the rejection. Blank input is
    handled by the caller (_prompt_nationality), not here — an empty
    string has no canonical form to classify."""
    canonical = normalize_country(raw)
    if canonical is None:
        return "error", (
            f"'{raw}' doesn't match a recognized country name. "
            "Use the country's common English name, e.g. 'Portugal', 'United States', 'Japan'."
        )
    return "ok", canonical


def _prompt_nationality() -> str:
    while True:
        raw = _prompt(
            "Nationality — country only, e.g. 'Portugal' (never enter a passport number)",
            required=False,
        )
        if not raw:
            return ""
        status, result = _classify_nationality_input(raw)
        if status == "error":
            print(f"  {result}")
            continue
        return result


def cmd_create(expected_parties_str: str) -> None:
    try:
        expected_parties = int(expected_parties_str)
    except ValueError:
        print("expected_parties must be a whole number, e.g. 3")
        sys.exit(1)

    try:
        trip_id = create_trip(expected_parties)
    except TripError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Trip created: {trip_id}")
    print(f"Waiting on {expected_parties} submissions.")
    print(f"Share this with each person: python3 intake.py submit {trip_id}")


def cmd_submit(trip_id: str) -> None:
    print(f"Submitting for trip {trip_id}. Your name and origin city are required;")
    print("everything else can be left blank if you're not sure yet.\n")

    name = _prompt("Your name")
    origin_city = _resolve_origin_city()
    date_flexibility = _prompt(
        "Date flexibility (e.g. 'flexible in June' or 'only July 10-17')", required=False
    )
    budget_ceiling_usd = _prompt_budget()
    nationality = _prompt_nationality()
    hard_constraints = _prompt(
        "Hard constraints (e.g. 'no red-eyes', 'wheelchair accessible')", required=False
    )
    travel_preference = _prompt(
        "Travel mode preference — 'ground' if you'd rather take a slower train/drive than "
        "deal with flight logistics, 'speed' if you just want the fastest option regardless "
        "of hassle, or leave blank for no preference",
        required=False,
    )

    try:
        result = add_submission(
            trip_id,
            person_name=name,
            origin_city=origin_city,
            date_flexibility=date_flexibility,
            budget_ceiling_usd=budget_ceiling_usd,
            nationality=nationality,
            hard_constraints=hard_constraints,
            travel_preference=travel_preference,
        )
    except TripError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    if result["redacted"]:
        print(
            "\n[guardrail] Something in your free-text answers looked like a passport/ID "
            "number and was redacted before saving. Only your nationality (country) is "
            "stored for visa purposes — never a passport number."
        )

    print(f"\nSubmitted. {trip_status_summary(trip_id)}")
    if result["status"] == "complete":
        print(f"\nTrip complete! Run: python3 midpoint_agent.py --trip {trip_id}")


def cmd_status(trip_id: str) -> None:
    try:
        print(trip_status_summary(trip_id))
    except TripError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_lock(trip_id: str) -> None:
    submissions = get_submissions(trip_id)
    names = ", ".join(s["person_name"] for s in submissions) or "(none)"
    print(f"This will lock trip {trip_id} with exactly these {len(submissions)} people: {names}")
    print("No one else will be able to submit after this — if someone new wants in, they'd")
    print("need a new trip. This cannot be undone.")
    confirm = input("Type 'lock' to confirm: ").strip()
    if confirm != "lock":
        print("Cancelled — nothing changed.")
        return

    try:
        lock_trip(trip_id)
    except TripError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Trip {trip_id} is now locked and complete.")
    print(f"Run: python3 midpoint_agent.py --trip {trip_id}")


COMMANDS = {"create": cmd_create, "submit": cmd_submit, "status": cmd_status, "lock": cmd_lock}


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in COMMANDS:
        print(USAGE)
        sys.exit(0 if len(sys.argv) < 2 else 1)

    COMMANDS[sys.argv[1]](sys.argv[2])
