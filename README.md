# Meet in the Middle

A multi-agent system that helps geographically distant people find a
meeting point where the *effort* is roughly fair for everyone — not just
the point that's geographically halfway. Built as an 8-week, hands-on
agentic-AI learning project. See `PRODUCT_BRIEF.md` for the full problem
statement and current scope.

**Status:** Week 2 of 8 complete (multi-party intake & state). This
README will get a full rewrite with architecture diagram and live demo
link in Week 7 — for now it's just enough to run the thing.

## Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

Create a trip and have each person submit independently:
```bash
python3 intake.py create <expected_parties>       # prints a trip id
python3 intake.py submit <trip_id>                 # interactive, one person
python3 intake.py status <trip_id>                  # who's submitted so far
python3 intake.py lock <trip_id>                    # finalize early (irreversible)
```

Once a trip is complete (everyone's submitted, or it was locked), rank
candidate meeting cities by fairness of effort:
```bash
python3 midpoint_agent.py --trip <trip_id>
```

Or skip intake entirely and try it with raw city names:
```bash
python3 midpoint_agent.py "Vienna, Austria" "London, England"
```

## Notable design decisions
- **Locking is irreversible.** Once a trip is complete, no one — not even
  a non-responder — can submit and reshuffle a result other people
  already saw. A new participant means a new trip.
- **PII minimization.** Only nationality (the visa-relevant fact) is
  stored, never a passport number — enforced both structurally (no such
  column exists) and by scrubbing free-text fields as a backstop.
- **Ground vs. flight is a disclosed heuristic**, not real routing data —
  see the module docstring in `ground_travel.py` for exactly what it does
  and doesn't cover.

## Tests
```bash
pytest -v
```

## Project plan
The full 8-week curriculum, task checklist, and progress notes live in
the build tracker (shared separately) rather than in this repo.
