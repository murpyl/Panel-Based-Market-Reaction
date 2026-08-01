import argparse
import sys

import pandas as pd

WINDOW_BARS = 60
WINDOW_MINUTES = 59  # 0-14 Inclusive

BAR_COLS = {
    "ts_utc": "timestamp_utc",
    "ts_et": "timestamp_et",
    "open": "open",
    "session": "session",
}

def load_inputs(posts_path, bars_path, confound_path, ticker):
    posts = pd.read_csv(posts_path, dtype={"id": str, "author_id": str})
    posts["created_at_utc"] = pd.to_datetime(posts["created_at_utc"], utc=True)

    bars = pd.read_csv(bars_path)
    bars[BAR_COLS["ts_utc"]] = pd.to_datetime(bars[BAR_COLS["ts_utc"]], utc=True)
    bars = bars.sort_values(BAR_COLS["ts_utc"]).reset_index(drop=True)

    confound = pd.read_csv(confound_path)
   
    confound["exclusion_start"] = pd.to_datetime(confound["exclusion_start"], utc=True)
    confound["exclusion_end"] = pd.to_datetime(confound["exclusion_end"], utc=True)
    
    confound = confound[(confound["ticker"] == ticker) | (confound["ticker"] == "ALL")].reset_index(drop=True)

    return posts, bars, confound


def find_covering_bar_idx(bars: pd.DataFrame, t0) -> int:
    """Index of the last bar with open <= t0 (the bar 'covering' this timestamp)."""
    ts_col = bars[BAR_COLS["ts_utc"]]
    idx = ts_col.searchsorted(t0, side="right") - 1
    return int(idx) if idx >= 0 else -1


def find_first_bar_at_or_after_idx(bars: pd.DataFrame, t0) -> int:
    ts_col = bars[BAR_COLS["ts_utc"]]
    idx = ts_col.searchsorted(t0, side="left")
    return int(idx) if idx < len(bars) else -1


def collect_window(bars: pd.DataFrame, start_idx: int):
    """From start_idx, collect up to WINDOW_BARS bars, bounded by WINDOW_MINUTES elapsed."""
    if start_idx < 0:
        return [], None, None
    ts_col = bars[BAR_COLS["ts_utc"]]
    window_start_time = ts_col.iloc[start_idx]
    window_end_time = window_start_time + pd.Timedelta(minutes=WINDOW_MINUTES)

    rows = []
    i = start_idx
    while i < len(bars) and len(rows) < WINDOW_BARS:
        t = ts_col.iloc[i]
        if t > window_end_time:
            break
        rows.append(i)
        i += 1
    return rows, window_start_time, window_end_time


def find_next_regular_open_idx(bars: pd.DataFrame, t0) -> int:
    ts_col = bars[BAR_COLS["ts_utc"]]
    session_col = bars[BAR_COLS["session"]]
    start = find_first_bar_at_or_after_idx(bars, t0)
    if start < 0:
        return -1
    mask = (session_col.iloc[start:] == "regular")
    candidates = mask[mask].index
    return int(candidates[0]) if len(candidates) else -1


def find_last_regular_bar_before_idx(bars: pd.DataFrame, t0) -> int:
    ts_col = bars[BAR_COLS["ts_utc"]]
    session_col = bars[BAR_COLS["session"]]
    covering = find_covering_bar_idx(bars, t0)
    for i in range(covering, -1, -1):
        if session_col.iloc[i] == "regular":
            return i
    return -1


def check_confound_overlap(confound: pd.DataFrame, window_start, window_end):
    if window_start is None or window_end is None:
        return False, None
    overlap = confound[
        (confound["exclusion_start"] <= window_end) & (confound["exclusion_end"] >= window_start)
    ]
    if len(overlap) == 0:
        return False, None
    reasons = "; ".join(
        f"{r.event_type}({r.ticker}, {r.exclusion_start}->{r.exclusion_end})"
        for r in overlap.itertuples()
    )
    return True, reasons


def process_post(post_row, bars: pd.DataFrame, confound: pd.DataFrame):
    t0 = post_row["created_at_utc"]

    covering_idx = find_covering_bar_idx(bars, t0)
    session_at_post = bars[BAR_COLS["session"]].iloc[covering_idx] if covering_idx >= 0 else "unknown_no_bar_coverage"

    result = {
        "post_id": post_row["id"],
        "post_time_utc": t0,
        "session_at_post": session_at_post,
        "off_hours": session_at_post != "regular",
        "gap_hours": None,
        "reference_bar_time": None,
        "reference_bar_open": None,
        "window_start_time": None,
        "window_end_time_bound": None,
        "bars_found": 0,
        "bars_expected": WINDOW_BARS,
        "last_bar_time_actual": None,
        "minutes_elapsed_actual": None,
        "excluded_flag": False,
        "excluded_reason": None,
    }

    if session_at_post == "regular":
        result["reference_bar_time"] = bars[BAR_COLS["ts_utc"]].iloc[covering_idx]
        result["reference_bar_open"] = bars[BAR_COLS["open"]].iloc[covering_idx]

        start_idx = find_first_bar_at_or_after_idx(bars, t0)
        rows, w_start, w_end = collect_window(bars, start_idx)

    elif session_at_post == "unknown_no_bar_coverage":
        # No bar covers this timestamp at all (total gap). Can't safely resolve
        # a reference or window -- flag rather than guess.
        rows, w_start, w_end = [], None, None

    else:
        # off-hours: pre_market, after_hours, or closed (overnight/weekend/holiday)
        last_reg_idx = find_last_regular_bar_before_idx(bars, t0)
        if last_reg_idx >= 0:
            result["reference_bar_time"] = bars[BAR_COLS["ts_utc"]].iloc[last_reg_idx]
            result["reference_bar_open"] = bars[BAR_COLS["open"]].iloc[last_reg_idx]

        next_open_idx = find_next_regular_open_idx(bars, t0)
        if next_open_idx >= 0:
            next_open_time = bars[BAR_COLS["ts_utc"]].iloc[next_open_idx]
            result["gap_hours"] = round((next_open_time - t0).total_seconds() / 3600, 2)
            rows, w_start, w_end = collect_window(bars, next_open_idx)
        else:
            rows, w_start, w_end = [], None, None

    result["window_start_time"] = w_start
    result["window_end_time_bound"] = w_end
    result["bars_found"] = len(rows)
    if rows:
        last_idx = rows[-1]
        result["last_bar_time_actual"] = bars[BAR_COLS["ts_utc"]].iloc[last_idx]
        result["minutes_elapsed_actual"] = round(
            (result["last_bar_time_actual"] - (w_start if session_at_post == "regular" else result["reference_bar_time"] if result["reference_bar_time"] is not None else w_start)).total_seconds() / 60, 2
        ) if w_start is not None else None

    excl_check_start = w_start if w_start is not None else t0
    excl_check_end = w_end if w_end is not None else t0
    result["excluded_flag"], result["excluded_reason"] = check_confound_overlap(
        confound, excl_check_start, excl_check_end
    )

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--posts", required=True)
    parser.add_argument("--bars", required=True)
    parser.add_argument("--confound", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ticker", required = True)
    args = parser.parse_args()

    posts, bars, confound = load_inputs(args.posts, args.bars, args.confound, args.ticker)
    print(f"Loaded {len(posts)} posts, {len(bars)} bars, {len(confound)} relevant confound rows.", file=sys.stderr)

    results = [process_post(row, bars, confound) for _, row in posts.iterrows()]
    out = pd.DataFrame(results)
    out.to_csv(args.output, index=False)
    print(f"Wrote {args.output}", file=sys.stderr)

    # --- Hand-verification aids: print to console rather than bury in the CSV ---
    n_regular = (out["session_at_post"] == "regular").sum()
    n_offhours = out["off_hours"].sum()
    n_no_coverage = (out["session_at_post"] == "unknown_no_bar_coverage").sum()
    n_excluded = out["excluded_flag"].sum()
    n_short_window = (out["bars_found"] < WINDOW_BARS).sum()

    print("\n=== Join summary (sanity-check these numbers by hand) ===")
    print(f"Regular-session posts:     {n_regular}")
    print(f"Off-hours posts:           {n_offhours}")
    print(f"No bar coverage at all:    {n_no_coverage}  <- investigate any of these individually")
    print(f"Confound-excluded posts:   {n_excluded}")
    print(f"Windows with <{WINDOW_BARS} bars:     {n_short_window}")
          
    if n_regular:
        reg = out[out["session_at_post"] == "regular"]["minutes_elapsed_actual"].dropna()
        print(f"\nRegular-session minutes_elapsed_actual: min={reg.min()}, median={reg.median()}, max={reg.max()}")
        print("  -> should cluster near 14 (last bar of a full 15-bar window). A consistent")
        print("     offset (e.g. everything ~240 or ~300 minutes off) would indicate a timezone bug.")

    if n_offhours:
        gaps = out[out["off_hours"]]["gap_hours"].dropna()
        print(f"\nOff-hours gap_hours distribution: min={gaps.min()}, median={gaps.median()}, max={gaps.max()}")
        print("  -> should show a rough bimodal split: short gaps (weeknight, ~12-18h) vs")
        print("     long gaps (Friday/holiday, ~60-90h). Inspect the CSV's gap_hours column")
        print("     directly rather than trusting this one-line summary.")


if __name__ == "__main__":
    main()