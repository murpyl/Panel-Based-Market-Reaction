"""
build_confound_calendar.py

Generates confound_calendar.csv covering Jan 1 2024 - Jul 17 2026 for the
6-account panel (MSFT, CRM, BOX, QCOM, HOOD, SHOP).

Schema:
    date            - ISO date (YYYY-MM-DD) of the event
    event_type      - fomc | jobs_report | cpi | earnings | election
    ticker          - specific ticker, or ALL for panel-wide events
    timing          - AMC | BMO | intraday_2pm_et | all_day
    exclusion_start - ISO datetime with correct ET offset for that date
    exclusion_end   - ISO datetime with correct ET offset for that date
    confidence      - confirmed | estimated | PLACEHOLDER
    source_note     - where this came from / what still needs verification

Rules encoded here (per prior decisions):
    - FOMC: exclusion = 2:00pm ET decision day through end of that trading day
            (same-day-only)
    - jobs_report / cpi: exclusion = release day only, 8:30am ET through
            market close (same-day-only)
    - earnings AMC: exclusion = release day 4:00pm ET through end of NEXT
            trading day (longer window than macro releases, per earlier
            decision). NEXT_TRADING_DAY is left as a marker for your
            pipeline's trading-calendar logic to resolve (weekends/holidays).
    - earnings BMO: exclusion = release day, market open through close
    - election: single flagged date, same-day-only -- flagged as a judgment
            call worth reviewing, not a rule mechanically inherited from
            elsewhere
"""

import csv
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

def et_dt(d_str, hour, minute):
    """Build a timezone-aware ET datetime and return its correct ISO string
    (offset resolved automatically for that specific date, DST-aware)."""
    y, m, day = (int(x) for x in d_str.split("-"))
    dt = datetime(y, m, day, hour, minute, tzinfo=ET)
    return dt.isoformat()

rows = []

def add(d, event_type, ticker, timing, excl_start, excl_end, confidence, note):
    rows.append({
        "date": d,
        "event_type": event_type,
        "ticker": ticker,
        "timing": timing,
        "exclusion_start": excl_start,
        "exclusion_end": excl_end,
        "confidence": confidence,
        "source_note": note,
    })

# ---------------------------------------------------------------------------
# FOMC meetings -- confirmed dates. Decision announced 2:00pm ET on the
# second day of each two-day meeting.
# ---------------------------------------------------------------------------
fomc_decision_dates = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]

for d in fomc_decision_dates:
    add(
        d, "fomc", "ALL", "intraday_2pm_et",
        et_dt(d, 14, 0), et_dt(d, 16, 0),
        "confirmed",
        "Sourced from federalreserve.gov meeting calendar / Fed press releases. "
        "Same-day-only exclusion. "
    )
print("FOMC")
# ---------------------------------------------------------------------------
# Jobs report -- first Friday of each month, with known exceptions flagged.
# ---------------------------------------------------------------------------
def first_friday(year, month):
    d = date(year, month, 1)
    offset = (4 - d.weekday()) % 7  # Friday = weekday 4
    return d + timedelta(days=offset)

flagged_months = {
    (2024, 3): ("The 8th", "2024-03-08"),
    (2025, 1): ("New Year's Day holiday-adjacent -- 2025-01-10", "2025-01-10"),
    (2025, 7): ("July 4th holiday-adjacent", "2025-07-03"),
    (2025, 11): ("2025 government shutdown delayed BLS releases", "2025-11-20"),
    (2025, 12): ("Likely affected by shutdown backlog/rescheduling", "2025-12-16"),
    (2026, 1): ("New Year's Day holiday-adjacent -- verify exact date against bls.gov", "2026-01-09"),
    (2026, 2): ("Likely affected by shutdown backlog/rescheduling", "2026-02-11"),
    (2026, 5): ("The 8th", "2026-05-08"),
    (2026, 7): ("July 4th holiday-adjacent", "2026-07-02"),
}

y, m = 2024, 1
while (y, m) <= (2026, 7):
    if y == 2025 and m == 10:
        m+=1
        continue
    d = first_friday(y, m)
    d_str = d.isoformat()
    confidence = "confirmed"
    note = "Generated via first-Friday-of-month rule. "
    if (y, m) in flagged_months:
        note, d = flagged_months[(y, m)]
        d_str = d
    add(
        d_str, "jobs_report", "ALL", "all_day",
        et_dt(d_str, 8, 30), et_dt(d_str, 16, 0),
        confidence, note
    )
    m += 1
    if m > 12:
        m = 1
        y += 1
print("Jobs report")
# ---------------------------------------------------------------------------
# CPI -- not generated, no reliable fixed-weekday rule. Placeholder rows
# per month; pull real dates from bls.gov/cpi archived news releases.
# ---------------------------------------------------------------------------
y, m = 2024, 1
cpi_dates = ["2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12",
             "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
             "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11",
             "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-24", "gov shutdown", "2025-12-18",
             "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10",
             ]
for d in cpi_dates:
    s = ""
    if d == "2025-12-18":
        s = " October 2025 Government Shutdown delayed BLS release, this date accounts from Sept 2025 to Nov 2025"
    if d != "gov shutdown":
        add(
            d, "cpi", "ALL", "all_day",
            et_dt(d, 8, 30), et_dt(d, 16, 0),
            "confirmed",
            "Sourced from bls.gov/cpi archived news releases. Same-day-only exclusion." + s
        )
print("CPI")
# ---------------------------------------------------------------------------
# Election
# ---------------------------------------------------------------------------
add(
    "2024-11-05", "election", "ALL", "all_day",
    et_dt("2024-11-05", 9, 30), et_dt("2024-11-05", 16, 0),
    "confirmed",
    "2024 US presidential election day. Same-day-only exclusion applied -- "
    "this was a judgment call (reconsider a longer post-election tail if desired), "
    "over including multiple days in the exclusion"
)

print("Election")

# ---------------------------------------------------------------------------
# Earnings -- confirmed/estimated near-term dates, plus explicit placeholder
# blocks marking the full historical pull as still outstanding.
# ---------------------------------------------------------------------------



confirmed_earnings = [
    ("2024-01-30", "MSFT", "AMC", "confirmed"),
    ("2024-04-25", "MSFT", "AMC", "confirmed"),
    ("2024-07-30", "MSFT", "AMC", "confirmed"),
    ("2024-10-30", "MSFT", "AMC", "confirmed"),
    ("2025-01-29", "MSFT", "AMC", "confirmed"),
    ("2025-04-30", "MSFT", "AMC", "confirmed"),
    ("2025-07-30", "MSFT", "AMC", "confirmed"),
    ("2025-10-29", "MSFT", "AMC", "confirmed"),
    ("2026-01-28", "MSFT", "AMC", "confirmed"),
    ("2026-04-29", "MSFT", "AMC", "confirmed"),
    ("2026-07-29", "MSFT", "AMC", "confirmed"),
    ("2024-01-31", "QCOM", "AMC", "confirmed"),
    ("2024-05-01", "QCOM", "AMC", "confirmed"),
    ("2024-07-31", "QCOM", "AMC", "confirmed"),
    ("2024-11-06", "QCOM", "AMC", "confirmed"),
    ("2025-02-05", "QCOM", "AMC", "confirmed"),
    ("2025-04-30", "QCOM", "AMC", "confirmed"),
    ("2025-07-30", "QCOM", "AMC", "confirmed"),
    ("2025-11-05", "QCOM", "AMC", "confirmed"),
    ("2026-02-04", "QCOM", "AMC", "confirmed"),
    ("2026-04-29", "QCOM", "AMC", "confirmed"),
    ("2026-07-29", "QCOM", "AMC", "estimated"),
    ("2024-02-13", "HOOD", "AMC", "confirmed"),
    ("2024-05-08", "HOOD", "AMC", "confirmed"),
    ("2024-08-07", "HOOD", "AMC", "confirmed"),
    ("2024-10-30", "HOOD", "AMC", "confirmed"),
    ("2025-02-12", "HOOD", "AMC", "confirmed"),
    ("2025-04-30", "HOOD", "AMC", "confirmed"),
    ("2025-07-30", "HOOD", "AMC", "confirmed"),
    ("2025-11-05", "HOOD", "AMC", "confirmed"),
    ("2026-02-10", "HOOD", "AMC", "confirmed"),
    ("2026-04-28", "HOOD", "AMC", "confirmed"),
    ("2026-07-29", "HOOD", "AMC", "confirmed"),
    ("2024-02-13", "SHOP", "BMO", "confirmed"),
    ("2024-05-08", "SHOP", "BMO", "confirmed"),
    ("2024-08-07", "SHOP", "BMO", "confirmed"),
    ("2024-11-12", "SHOP", "BMO", "confirmed"),
    ("2025-02-11", "SHOP", "BMO", "confirmed"),
    ("2025-05-08", "SHOP", "BMO", "confirmed"),
    ("2025-08-06", "SHOP", "BMO", "confirmed"),
    ("2025-11-04", "SHOP", "BMO", "confirmed"),
    ("2026-02-11", "SHOP", "BMO", "confirmed"),
    ("2026-05-05", "SHOP", "BMO", "confirmed"),
    ("2026-08-05", "SHOP", "BMO", "confirmed"),
    ("2024-03-05", "BOX", "AMC", "confirmed"),
    ("2024-05-28", "BOX", "AMC", "confirmed"),
    ("2024-08-27", "BOX", "AMC", "confirmed"),
    ("2024-12-03", "BOX", "AMC", "confirmed"),
    ("2025-03-04", "BOX", "AMC", "confirmed"),
    ("2025-05-27", "BOX", "AMC", "confirmed"),
    ("2025-08-26", "BOX", "AMC", "confirmed"),
    ("2025-12-02", "BOX", "AMC", "confirmed"),
    ("2026-03-03", "BOX", "AMC", "confirmed"),
    ("2026-05-26", "BOX", "AMC", "confirmed"),
    ("2026-08-25", "BOX", "AMC", "estimated"),
    ("2024-02-28", "CRM", "AMC", "confirmed"),
    ("2024-05-29", "CRM", "AMC", "confirmed"),
    ("2024-08-28", "CRM", "AMC", "confirmed"),
    ("2024-12-03", "CRM", "AMC", "confirmed"),
    ("2025-02-26", "CRM", "AMC", "confirmed"),
    ("2025-05-28", "CRM", "AMC", "confirmed"),
    ("2025-09-03", "CRM", "AMC", "confirmed"),
    ("2025-12-03", "CRM", "AMC", "confirmed"),
    ("2026-02-25", "CRM", "AMC", "confirmed"),
    ("2026-05-27", "CRM", "AMC", "confirmed"),
    ("2026-09-02", "CRM", "AMC", "confirmed"),
]

for d, ticker, timing, confidence in confirmed_earnings:
    if timing == "AMC":
        excl_start = et_dt(d, 16, 0)
        excl_end = "NEXT_TRADING_DAY_CLOSE"  # resolve with a trading calendar
    else:  # BMO
        excl_start = et_dt(d, 9, 30)
        excl_end = et_dt(d, 16, 0)
    add(d, "earnings", ticker, timing, excl_start, excl_end, confidence,
        "Confirmed via Alphaquery")

# for ticker in ["MSFT", "CRM", "BOX", "QCOM", "HOOD", "SHOP"]:
#     add(
#         "2024-01-01_to_2026-07-17", "earnings", ticker, "PLACEHOLDER",
#         "PLACEHOLDER", "PLACEHOLDER", "PLACEHOLDER",
#         f"Full historical earnings-date history for {ticker} not yet pulled. "
#         "~10 quarters expected. Replace this row with one row per actual "
#         "historical release date, using et_dt() for correct DST-aware offsets."
#     )

# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
fieldnames = ["date", "event_type", "ticker", "timing", "exclusion_start",
              "exclusion_end", "confidence", "source_note"]

with open("confound_calendar.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in sorted(rows, key=lambda r: (r["event_type"], str(r["date"]))):
        writer.writerow(r)

print(f"Wrote {len(rows)} rows to confound_calendar.csv")
confirmed_n = sum(1 for r in rows if r["confidence"] == "confirmed")
estimated_n = sum(1 for r in rows if r["confidence"] == "estimated")
placeholder_n = sum(1 for r in rows if r["confidence"] == "PLACEHOLDER")
print(f"  confirmed:   {confirmed_n}")
print(f"  estimated:   {estimated_n}")
print(f"  PLACEHOLDER: {placeholder_n}  <-- must be resolved before use")