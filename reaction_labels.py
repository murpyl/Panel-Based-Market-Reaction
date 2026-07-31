import argparse
import os
import sys

import numpy as np
import pandas as pd

BUCKET_MINUTES = 30
MIN_BASELINE_N = 30            # buckets with fewer baseline samples than this are flagged unreliable, not dropped
ABNORMAL_PERCENTILE = 90       # flag if raw_volatility exceeds this percentile of the ticker/bucket baseline
ABNORMAL_Z_THRESHOLD = 2.0     # kept only as a secondary diagnostic column, not the primary flag anymore
MIN_BARS_FOR_INCLUSION = 8     # bars_found > 7 -> included with caveat; <= 7 -> excluded as insufficient
WINDOW_BARS = 15
WINDOW_MINUTES = 14

BAR_COLS = {
    "ts_utc": "timestamp_utc",
    "ts_et": "timestamp_et",
    "open": "open",
    "close": "close",
    "session": "session",
}


def load_bars(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in BAR_COLS.values() if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}. Found: {list(df.columns)}")
    df[BAR_COLS["ts_utc"]] = pd.to_datetime(df[BAR_COLS["ts_utc"]], format="ISO8601", utc=True)
    df[BAR_COLS["ts_et"]] = pd.to_datetime(df[BAR_COLS["ts_et"]], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
    df["trading_date_et"] = df[BAR_COLS["ts_et"]].dt.date
    return df.sort_values(BAR_COLS["ts_utc"]).reset_index(drop=True)


def bars_in_range(bars: pd.DataFrame, start_time, end_time) -> pd.DataFrame:
    """O(log n) via searchsorted instead of a full-array boolean mask -- bars must be
    sorted ascending by timestamp (guaranteed by load_bars)."""
    ts = bars[BAR_COLS["ts_utc"]]
    lo = ts.searchsorted(start_time, side="left")
    hi = ts.searchsorted(end_time, side="right")
    return bars.iloc[lo:hi]


def last_index_at_or_before(bars: pd.DataFrame, t) -> int:
    """O(log n) index of the last bar with timestamp <= t, or -1 if none."""
    ts = bars[BAR_COLS["ts_utc"]]
    idx = ts.searchsorted(t, side="right") - 1
    return int(idx) if idx >= 0 else -1


def realized_volatility(window_bars: pd.DataFrame) -> float:
    closes = window_bars[BAR_COLS["close"]].values
    if len(closes) < 2:
        return np.nan
    log_returns = np.diff(np.log(closes))
    return float(np.std(log_returns))


def window_return(reference_open: float, window_bars: pd.DataFrame) -> float:
    if reference_open is None or pd.isna(reference_open) or len(window_bars) == 0:
        return np.nan
    last_close = window_bars[BAR_COLS["close"]].iloc[-1]
    return float(last_close / reference_open - 1)


def build_daily_open_times(bars: pd.DataFrame) -> dict:
    """Precompute {trading_date_et: first regular-session bar's UTC timestamp}, once per ticker,
    instead of rescanning the full table on every window lookup (this was the main O(n^2) culprit)."""
    regular = bars[bars[BAR_COLS["session"]] == "regular"]
    return regular.groupby("trading_date_et")[BAR_COLS["ts_utc"]].min().to_dict()


def time_bucket(window_start_time, daily_open_times: dict, et_tz="America/New_York") -> int:
    """30-min bucket index since that trading day's regular-session open. None if unresolvable."""
    et_time = window_start_time.tz_convert(et_tz)
    trading_date = et_time.date()
    open_time = daily_open_times.get(trading_date)
    if open_time is None:
        return None
    minutes_since_open = (window_start_time - open_time).total_seconds() / 60
    if minutes_since_open < 0:
        return None
    return int(minutes_since_open // BUCKET_MINUTES)


def build_baseline(ticker_bars: pd.DataFrame, post_windows: list, daily_open_times: dict) -> dict:
    """
    post_windows: list of (window_start_time, window_end_time_bound) tuples for
    this ticker's actual posts, used to exclude contaminated candidate windows.
    Returns {bucket_idx: {"mean":..., "std":..., "n":...}}

    Performance note: candidate windows are located via positional slicing (bars are
    sorted, session-filtered up front, so a window is just contiguous rows i..j) rather
    than a per-candidate boolean mask over the full array -- the latter is what caused
    CRM to hang (O(n^2): ~87k regular bars x 87k-row scan each = billions of comparisons).
    """
    regular = ticker_bars[ticker_bars[BAR_COLS["session"]] == "regular"].reset_index(drop=True)
    ts = regular[BAR_COLS["ts_utc"]]
    n = len(regular)

    # Sort post windows by start time so contamination checks can short-circuit quickly.
    sorted_windows = sorted(post_windows)

    bucket_vols = {}
    for i in range(n):
        t_start = ts.iloc[i]
        t_end = t_start + pd.Timedelta(minutes=WINDOW_MINUTES)

        j = int(ts.searchsorted(t_end, side="right")) - 1  # last position with ts <= t_end
        if j < i:
            continue
        window = regular.iloc[i:j + 1]
        if len(window) != WINDOW_BARS:
            continue  # only complete, gap-free windows count toward the baseline
        # (bars are pre-filtered to session=='regular', so a same-day-contiguous window
        # of the right length can't have bled past session close -- no extra check needed)

        contaminated = any((t_start <= pw_end) and (t_end >= pw_start) for pw_start, pw_end in sorted_windows)
        if contaminated:
            continue

        bucket = time_bucket(t_start, daily_open_times)
        if bucket is None:
            continue

        vol = realized_volatility(window)
        if np.isnan(vol):
            continue

        bucket_vols.setdefault(bucket, []).append(vol)

    baseline = {}
    for bucket, vols in bucket_vols.items():
        arr = np.array(vols)
        baseline[bucket] = {
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "n": len(arr),
            "p_threshold": float(np.percentile(arr, ABNORMAL_PERCENTILE)),
            "vols": arr,  # kept for exact percentile-rank lookup per post; not written to CSV directly
        }
    return baseline


def process_ticker(ticker: str, join_rows: pd.DataFrame, ticker_bars: pd.DataFrame, spy_bars: pd.DataFrame) -> pd.DataFrame:
    print(f"Processing {ticker}: {len(join_rows)} posts ...", file=sys.stderr)

    post_windows = [
        (row.window_start_time, row.window_end_time_bound)
        for row in join_rows.itertuples()
        if pd.notna(row.window_start_time) and pd.notna(row.window_end_time_bound)
    ]
    daily_open_times = build_daily_open_times(ticker_bars)
    baseline = build_baseline(ticker_bars, post_windows, daily_open_times)
    print(f"  baseline buckets: {len(baseline)}, "
          f"buckets with n<{MIN_BASELINE_N}: {sum(1 for b in baseline.values() if b['n'] < MIN_BASELINE_N)}",
          file=sys.stderr)

    out_rows = []
    for row in join_rows.itertuples():
        bars_found = getattr(row, "bars_found", None)
        if bars_found is None or pd.isna(bars_found):
            window_quality = "no_coverage"
        elif bars_found >= WINDOW_BARS:
            window_quality = "complete"
        elif bars_found > MIN_BARS_FOR_INCLUSION - 1:  # bars_found > 7
            window_quality = "partial"
        else:
            window_quality = "insufficient"

        result = {
            "post_id": row.post_id,
            "ticker": ticker,
            "excluded_flag": getattr(row, "excluded_flag", False),
            "excluded_reason": getattr(row, "excluded_reason", None),
            "bars_found": bars_found,
            "window_quality": window_quality,
            "confirmatory_eligible": (window_quality in ("complete", "partial")) and not getattr(row, "excluded_flag", False),
            "market_adjusted_return": np.nan,
            "raw_volatility": np.nan,
            "time_bucket": None,
            "baseline_mean": np.nan,
            "baseline_std": np.nan,
            "baseline_n": None,
            "baseline_p_threshold": np.nan,
            "vol_zscore": np.nan,
            "vol_percentile_rank": np.nan,
            "abnormal_volatility_flag": False,
        }

        w_start, w_end = row.window_start_time, row.window_end_time_bound
        ref_open = getattr(row, "reference_bar_open", None)

        if pd.isna(w_start) or pd.isna(w_end):
            out_rows.append(result)
            continue

        ticker_window = bars_in_range(ticker_bars, w_start, w_end)
        spy_window = bars_in_range(spy_bars, w_start, w_end)

        ticker_ret = window_return(ref_open, ticker_window)

        # SPY reference: last SPY bar at/before the ticker's reference bar time (O(log n) lookup)
        spy_ref_open = None
        if pd.notna(row.reference_bar_time):
            spy_ref_idx = last_index_at_or_before(spy_bars, row.reference_bar_time)
            if spy_ref_idx >= 0:
                spy_ref_open = spy_bars[BAR_COLS["open"]].iloc[spy_ref_idx]
        spy_ret = window_return(spy_ref_open, spy_window)

        if not (np.isnan(ticker_ret) or np.isnan(spy_ret)):
            result["market_adjusted_return"] = ticker_ret - spy_ret

        vol = realized_volatility(ticker_window)
        result["raw_volatility"] = vol

        bucket = time_bucket(w_start, daily_open_times)
        result["time_bucket"] = bucket
        if bucket is not None and bucket in baseline and not np.isnan(vol):
            b = baseline[bucket]
            result["baseline_mean"] = b["mean"]
            result["baseline_std"] = b["std"]
            result["baseline_n"] = b["n"]
            result["baseline_p_threshold"] = b["p_threshold"]
            result["vol_percentile_rank"] = float((b["vols"] <= vol).mean() * 100)
            result["abnormal_volatility_flag"] = vol > b["p_threshold"]
            if b["std"] > 0:
                result["vol_zscore"] = (vol - b["mean"]) / b["std"]  # diagnostic only, not the primary flag

        out_rows.append(result)

    return pd.DataFrame(out_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--join-csv", required=True, help="Combined join output across all tickers (must have a 'ticker' column)")
    parser.add_argument("--bars-dir", required=True, help="Directory with <TICKER>.csv bar files")
    parser.add_argument("--spy-bars", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    join_df = pd.read_csv(args.join_csv)
    required = ["post_id", "ticker", "window_start_time", "window_end_time_bound", "reference_bar_time", "reference_bar_open"]
    missing = [c for c in required if c not in join_df.columns]
    if missing:
        raise ValueError(f"{args.join_csv}: missing columns {missing}. Found: {list(join_df.columns)}")
    for col in ["window_start_time", "window_end_time_bound", "reference_bar_time"]:
        join_df[col] = pd.to_datetime(join_df[col], utc=True, errors="coerce")

    spy_bars = load_bars(args.spy_bars)

    all_results = []
    for ticker, group in join_df.groupby("ticker"):
        bars_path = os.path.join(args.bars_dir, f"{ticker}.csv")
        if not os.path.exists(bars_path):
            print(f"WARNING: no bar file found at {bars_path}, skipping {ticker} ({len(group)} posts)", file=sys.stderr)
            continue
        ticker_bars = load_bars(bars_path)
        all_results.append(process_ticker(ticker, group, ticker_bars, spy_bars))

    out = pd.concat(all_results, ignore_index=True)
    out.to_csv(args.output, index=False)
    print(f"\nWrote {args.output}", file=sys.stderr)

    n_abnormal = out["abnormal_volatility_flag"].sum()
    n_excluded = out["excluded_flag"].sum()
    n_thin_baseline = ((out["baseline_n"].notna()) & (out["baseline_n"] < MIN_BASELINE_N)).sum()
    n_confirmatory_eligible = out["confirmatory_eligible"].sum()
    print("\n=== Summary (sanity-check before trusting) ===")
    print(f"Total rows: {len(out)}")
    print(f"Confound-excluded: {n_excluded}")
    print(f"Window quality breakdown:\n{out['window_quality'].value_counts().to_string()}")
    print(f"Confirmatory-eligible (window ok AND not confound-excluded): {n_confirmatory_eligible}")
    print(f"Abnormal-volatility flagged (p{ABNORMAL_PERCENTILE} threshold): {n_abnormal} ({100*n_abnormal/len(out):.1f}%)")
    z_based = (out["vol_zscore"] > ABNORMAL_Z_THRESHOLD).sum()
    print(f"  (for comparison, z>{ABNORMAL_Z_THRESHOLD} would have flagged: {z_based} ({100*z_based/len(out):.1f}%))")
    print(f"Rows resting on a thin baseline (n<{MIN_BASELINE_N}): {n_thin_baseline}  <- treat these flags cautiously")
    print(f"\nmarket_adjusted_return: min={out['market_adjusted_return'].min():.4f}, "
          f"median={out['market_adjusted_return'].median():.4f}, max={out['market_adjusted_return'].max():.4f}")


if __name__ == "__main__":
    main()