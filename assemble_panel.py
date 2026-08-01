import argparse
import sys

import pandas as pd

TIER_MAP_4 = {
    "CRM": "confirmatory",
    "BOX": "confirmatory",
    "QCOM": "confirmatory",
    "HOOD": "confirmatory",
    "MSFT": "null_baseline",
    "SHOP": "exploratory_only",
}
TIER_MAP_5 = {**TIER_MAP_4, "SHOP": "confirmatory"}

FOUR_ACCOUNT_WINDOW = (pd.Timestamp("2025-06-24", tz="UTC"), pd.Timestamp("2026-07-17", tz="UTC"))
FIVE_ACCOUNT_WINDOW = (pd.Timestamp("2025-12-17", tz="UTC"), pd.Timestamp("2026-07-17", tz="UTC"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", required=True, help="Output of compute_reaction_labels.py")
    parser.add_argument("--deviation", required=True, help="Output of compute_deviation_feature.py")
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-shop", action="store_true",
                         help="5-account scenario: adds SHOP to confirmatory, re-imposes the tighter "
                              "shared window (2025-12-17 to 2026-07-17) on ALL confirmatory accounts")
    args = parser.parse_args()

    labels = pd.read_csv(args.labels)
    labels["post_id"] = labels["post_id"].astype(str)
    required_labels = ["post_id", "ticker", "excluded_flag", "window_quality", "market_adjusted_return", "abnormal_volatility_flag"]
    missing = [c for c in required_labels if c not in labels.columns]
    if missing:
        raise ValueError(f"{args.labels}: missing columns {missing}. Found: {list(labels.columns)}")

    deviation = pd.read_csv(args.deviation)
    deviation["post_id"] = deviation["post_id"].astype(str)
    required_dev = ["post_id", "author_id", "created_at_utc", "deviation_score", "insufficient_history"]
    missing_dev = [c for c in required_dev if c not in deviation.columns]
    if missing_dev:
        raise ValueError(f"{args.deviation}: missing columns {missing_dev}. Found: {list(deviation.columns)}")
    deviation["created_at_utc"] = pd.to_datetime(deviation["created_at_utc"], utc=True)

    panel = labels.merge(deviation, on="post_id", how="outer", indicator=True)

    only_labels = (panel["_merge"] == "left_only").sum()
    only_deviation = (panel["_merge"] == "right_only").sum()
    if only_labels or only_deviation:
        print(f"WARNING: {only_labels} posts in labels but not deviation features, "
              f"{only_deviation} posts in deviation features but not labels. "
              f"Check these aren't silently dropped from analysis -- likely a post_id mismatch "
              f"(e.g. dtype/format difference) rather than genuinely missing data.", file=sys.stderr)
    panel = panel.drop(columns="_merge")

    tier_map = TIER_MAP_5 if args.include_shop else TIER_MAP_4
    window_start, window_end = FIVE_ACCOUNT_WINDOW if args.include_shop else FOUR_ACCOUNT_WINDOW
    print(f"Mode: {'5-account (SHOP included)' if args.include_shop else '4-account (default)'}, "
          f"shared confirmatory window: {window_start.date()} to {window_end.date()}", file=sys.stderr)

    panel["tier"] = panel["ticker"].map(tier_map)
    unmapped = panel[panel["tier"].isna()]["ticker"].unique()
    if len(unmapped):
        raise ValueError(f"Ticker(s) not in tier_map: {unmapped}. Add them before proceeding "
                          f"-- silently treating an unmapped ticker as excluded would be worse than failing loudly.")

    panel["in_shared_window"] = panel["created_at_utc"].between(window_start, window_end)

    panel["final_confirmatory_eligible"] = (
        (panel["tier"] == "confirmatory")
        & (panel["excluded_flag"] != True)  # noqa: E712
        & (panel["window_quality"].isin(["complete", "partial"]))
        & (panel["insufficient_history"] != True)  # noqa: E712
        & (panel["in_shared_window"])
    )

    panel.to_csv(args.output, index=False)
    print(f"Wrote {args.output}", file=sys.stderr)

    print("\n=== Tier breakdown ===")
    print(panel["tier"].value_counts().to_string())

    print("\n=== Confirmatory-eligibility funnel (tier == 'confirmatory' only) ===")
    conf = panel[panel["tier"] == "confirmatory"]
    print(f"Total confirmatory-tier rows (before window filter): {len(conf)}")
    print(f"  minus outside shared window [{window_start.date()}, {window_end.date()}]: {(~conf['in_shared_window']).sum()}")
    print(f"  minus confound-excluded:           {(conf['excluded_flag'] == True).sum()}")
    print(f"  minus bad window_quality:          {(~conf['window_quality'].isin(['complete', 'partial'])).sum()}")
    print(f"  minus insufficient_history:        {(conf['insufficient_history'] == True).sum()}")
    print(f"Final confirmatory-eligible rows:    {conf['final_confirmatory_eligible'].sum()}")

    print("\n=== Per-account confirmatory-eligible counts (check for a lopsided panel) ===")
    print(conf[conf["final_confirmatory_eligible"]].groupby("author_id").size().to_string())


if __name__ == "__main__":
    main()