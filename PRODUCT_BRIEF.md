# Meet in the Middle — Product Brief

## Problem
People who live far apart — friends, family, a distributed team — want to
meet somewhere in between, but "somewhere in between" usually gets decided
by whoever's most annoying about it, or by picking the geographic midpoint
on a map, which is rarely the *fair* midpoint. A 6-hour flight for one
person and a 45-minute train for another isn't fair just because the pin
lands equidistant. This project builds an agentic system that proposes
meeting points balanced on effort, not raw geography — and is honest about
the limits of that math instead of hiding them.

## Users
- A friend group or family spread across countries, planning a reunion.
- A distributed team choosing an offsite or kickoff city.
- MVP target: 2–6 parties per trip.

## How it works today (through Week 2)
1. **Intake** (`intake.py`) — each person submits independently, whenever
   they get to it: origin city, date flexibility, budget ceiling,
   nationality, hard constraints, and a travel-mode preference (would you
   rather fly, or take the slower-but-simpler ground option when one
   exists?).
2. **State** (`db.py`, SQLite) — a trip is keyed by a short id and tracks
   submissions against an expected party count. It auto-completes once
   everyone's in, or the organizer can lock it early if someone's gone
   quiet. Locking is irreversible on purpose: once a trip is complete, no
   late submission can reshuffle a result other people already saw.
3. **Fairness** (`midpoint_agent.py`) — ranks a fixed list of candidate
   cities by *fairness of effort*: how close everyone's door-to-door time
   is to each other, not just how low the average is. Effort is mode-aware
   (`ground_travel.py`): it considers flying vs. a coarse ground-travel
   estimate, gated by a small disclosed ruleset (islands, closed borders,
   a couple of fixed-link exceptions like the Channel Tunnel) rather than
   pretending to be real routing data.
4. **Guardrail** (`guardrails.py`) — nationality is the only visa-relevant
   field ever stored; there is no passport-number column, and free-text
   fields are scrubbed for anything that looks like a passport/ID number
   before it touches disk.

## What's deliberately not built yet
- Real flight/lodging prices (Week 3 — Duffel/StayingAPI).
- A real visa/border data source (Week 4 spike — the current border logic
  in `ground_travel.py` is a small, disclosed, non-exhaustive ruleset, not
  a verified data source).
- Sourced/ranged/confidence-scored estimates and an eval suite (Week 5).
- Re-ranking after people react to a proposal (Week 6).
- A live public demo and full README/architecture writeup (Week 7).

## Core product promise
Every estimate this system shows is either the real thing or clearly
labeled as a heuristic — never a confident-sounding number invented to
fill a gap. That's true for pricing (Week 5) and it's already true for the
ground-vs-flight travel-time math today.
