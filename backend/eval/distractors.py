"""Seeded generator of hard-negative documents.

A tiny corpus makes every retriever look perfect. Real knowledge bases are full of near-duplicates:
other products' spec sheets, last year's reports, other incidents. These documents share the gold
documents' vocabulary and structure but carry different facts, so a retriever has to match the
*right* entity (LR-200 vs LR-250, INC-2291 vs INC-2217, Q3 FY2025 vs Q3 FY2024) to score.

None of them may contain a gold evidence passage or answer an "unanswerable" question; that is
enforced by `check_no_leaks`.
"""

import random

from eval.common import Question, has_evidence

BIRDS = ["Wren", "Finch", "Robin", "Swift", "Kestrel", "Plover", "Tern", "Lark", "Martin", "Stork",
         "Crane", "Egret", "Ibis", "Osprey", "Merlin", "Pipit", "Linnet", "Dunlin", "Avocet",
         "Bittern", "Curlew", "Shrike"]
CITIES = ["Antwerp", "Hamburg", "Leipzig", "Poznań", "Milan", "Lyon", "Gothenburg", "Aarhus",
          "Bilbao", "Brno", "Graz", "Tilburg", "Dortmund", "Malmö", "Lille", "Porto", "Chicago",
          "Columbus", "Venlo", "Duisburg"]
CAUSES = [
    ("wheel encoder drift after a motor-controller update",
     "Encoder calibration is re-run automatically after every motor-controller update"),
    ("Wi-Fi roaming failures between access points from a different vendor",
     "Roaming thresholds are now configured per site"),
    ("map corruption after a power loss during a map save",
     "Map saves are now atomic, with the previous map kept as a fallback"),
    ("worn charger contacts causing failed docking",
     "Charger contacts are inspected at every quarterly service"),
    ("lidar lens contamination from cardboard dust",
     "A lens-cleaning reminder is raised after 400 operating hours"),
    ("a clock-skew bug in mission scheduling after a daylight-saving change",
     "All scheduling now uses UTC internally"),
    ("lidar firmware mismatch after a partial hardware replacement",
     "Service technicians must now verify lidar firmware after part swaps"),
    ("an overloaded site server delaying mission assignment",
     "Fleet servers now autoscale on queue depth"),
]


def _spec_sheets(rng: random.Random) -> list[tuple[str, str]]:
    docs = []
    used = {200, 400, 600}
    for bird in BIRDS[:16]:
        num = rng.choice([n for n in range(110, 990, 10) if n not in used])
        used.add(num)
        payload = rng.choice([p for p in range(60, 1500, 20) if p not in (180, 1200)])
        speed = rng.choice([1.0, 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.9, 2.0])
        runtime = rng.choice([5, 6, 7, 9, 11, 12])
        full_charge = rng.choice([55, 60, 75, 80, 95, 100, 110])
        ip = rng.choice(["IP44", "IP53", "IP55", "IP66", "IP67"])
        warranty = rng.choice([12, 18, 30, 48])
        tmin = rng.choice([0, 5, -10, -15])
        name = f"LR-{num}"
        docs.append((f"{name.lower()}_spec_sheet.md", f"""# {name} "{bird}" — Autonomous Mobile Robot: Technical Specification

The {name} is a Larkspur autonomous mobile robot for intralogistics transport. It navigates with lidar SLAM and is managed through the Larkspur Fleet API.

## Physical

- Weight (without payload): {rng.randint(70, 400)} kg
- Maximum payload: {payload:,} kg
- Top speed: {speed} m/s
- Ingress protection: {ip}

## Power

- Battery: 48 V lithium iron phosphate (LiFePO4), {rng.choice([1.6, 2.4, 3.2, 4.0, 6.0])} kWh
- Runtime: up to {runtime} hours at a typical 60% duty cycle
- Charging: automatic docking; full charge in {full_charge} minutes

## Environment

Operating temperature is {tmin} °C to +40 °C.

## Warranty

Standard warranty is {warranty} months, extendable with a Larkspur Care service contract.
"""))
    return docs


def _incidents(rng: random.Random) -> list[tuple[str, str]]:
    docs = []
    used = {2291}
    for _ in range(36):
        num = rng.choice([n for n in range(1100, 3400) if n not in used])
        used.add(num)
        city = rng.choice(CITIES)
        bad = f"{rng.randint(3, 5)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
        fixed = f"{bad.rsplit('.', 1)[0]}.{int(bad.rsplit('.', 1)[1]) + rng.randint(1, 3)}"
        if fixed in ("4.2.3", "4.2.1") or bad in ("4.2.3", "4.2.1"):
            bad, fixed = "3.9.2", "3.9.4"
        cause, action = rng.choice(CAUSES)
        units = rng.choice([u for u in range(3, 90) if u != 37])
        model = rng.choice(["LR-200", "LR-400"])
        month = rng.choice(["January", "February", "April", "May", "June", "July", "August",
                            "September", "October", "November"])
        year = rng.choice([2023, 2024, 2025])
        docs.append((f"incident_report_inc_{num}.md", f"""# Post-Incident Review: INC-{num} — {cause.capitalize()}

**Severity:** SEV-{rng.choice([2, 3, 3, 4])}  **Status:** Resolved  **Author:** Fleet Reliability team

## Summary

In {month} {year}, {model} robots at the {city} site experienced repeated protective stops. The cause was {cause}, first seen after firmware {bad} was installed.

## Impact

- {units} {model} units at the {city} site were affected.
- No injuries or property damage occurred.

## Resolution

Firmware {fixed}, containing the fix, was deployed to the {city} site within {rng.randint(2, 9)} days.

## Corrective actions

1. {action}.
2. Monitoring was extended to catch the failure earlier.
"""))
    return docs


def _quarterly(rng: random.Random) -> list[tuple[str, str]]:
    docs = []
    quarters = [(fy, q) for fy in (2023, 2024) for q in (1, 2, 3, 4)] + [(2025, 1)]
    for fy, q in quarters:
        rev = round(rng.uniform(14, 40), 1)
        docs.append((f"q{q}_fy{fy}_business_review.md", f"""# Q{q} FY{fy} Business Review

## Headline numbers

Revenue for the quarter was €{rev} million, up {rng.randint(15, 45)}% year over year. Gross margin was {rng.randint(48, 58)}%. We signed {rng.choice([n for n in range(6, 30) if n != 19])} new customers during the quarter.

## Products

The LR-400 accounted for {rng.choice([n for n in range(5, 25) if n != 29])}% of new robot deployments.

## People

Headcount reached {rng.choice([n for n in range(180, 370)])} employees at the end of the quarter.
"""))
    return docs


def _apis(rng: random.Random) -> list[tuple[str, str]]:
    docs = []
    for name, header in [("Maps", "X-Maps-Key"), ("Billing", "X-Billing-Token"),
                         ("Telemetry Export", "X-Export-Token"), ("Identity", "X-Identity-Key"),
                         ("Service Desk", "X-Desk-Token"), ("Warehouse Sync", "X-Sync-Token")]:
        codes = rng.sample([c for c in range(1000, 9999) if c not in (1001, 2040, 3007, 4031, 5000)],
                           4)
        reasons = rng.sample([
            "the request body failed schema validation", "the referenced site does not exist",
            "the robot is not assigned to this account", "the export window exceeds 31 days",
            "the invoice is already closed", "the map layer is locked by another editor",
            "a waypoint overlaps a restricted zone on a draft map",
        ], 4)
        errors = "\n".join(f"- `E{c}` — {r}." for c, r in zip(codes, reasons, strict=True))
        docs.append((f"{name.lower().replace(' ', '_')}_api_reference.md", f"""# Larkspur {name} API — Reference

## Authentication

Every request must include a key in the `{header}` header.

## Rate limits

Each key may make up to {rng.choice([60, 120, 300, 1000, 1200])} requests per minute.

## Error codes

{errors}
"""))
    return docs


def generate(seed: int = 7) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    return _spec_sheets(rng) + _incidents(rng) + _quarterly(rng) + _apis(rng)


def check_no_leaks(docs: list[tuple[str, str]], questions: list[Question]) -> None:
    for fname, text in docs:
        for q in questions:
            for ev in q.evidence:
                if has_evidence(text, ev):
                    raise ValueError(f"Distractor {fname} contains gold evidence of {q.id}: {ev!r}")
        for forbidden in ("LR-600", "Q2 FY2025", "stock option", "CEO", "contractor"):
            if forbidden.lower() in text.lower():
                raise ValueError(f"Distractor {fname} would answer an unanswerable question")
