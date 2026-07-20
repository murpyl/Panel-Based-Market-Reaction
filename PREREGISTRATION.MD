# Pre-Registration — Track A Panel Test
**DATE COMMITTED:** 2026-07-20 (Week 1)
**Status:** Committed *before any modeling or result-viewing*

## Panel
7 accounts with one primary ticker each:

| Account | Ticker |
|---|---|
| Elon Musk | TSLA |
| Satya Nadella | MSFT |
| Marc Benioff | CRM |
| Aaron Levie | BOX |
| Cristiano Amon | QCOM |
| Vlad Tenev | HOOD |
| Tobias Lutke | SHOP |

**Expected-null group (pre-committed, not fit to data):** Musk, Nadella are both extremely high-profile, presumed heavily arbitraged, expected near-zero effect.
**Plausible-signal group:** Benioff, Levie, Amon, Tenev, Lutke.

**Stated limitation:** 
- This panel is not sector-diversified, as all 7 accounts are tech-sector CEOs. Leave-one-account-out folds are not fully independent, and a sector-wide news event can move multiple tickers at once regardless of any individual post. Results are interpreted with this in mind, not treated as fully independent tests.
- Attached media can confound tweets - text content may be a simple caption, whereas the main content or message is instead a link or a video. 

## Test design
- **Confirmatory test:** the 5-account plausible-signal group only.
- **Horizon:** N = 15 minutes post-timestamp, single horizon, no other horizons tested in the confirmatory test.
- **Correction:** Bonferroni across the 5 accounts.
- **Musk and Nadella:** reported separately, always, as an expected-null comparison — not pooled into the corrected test.

## Target
Abnormal volatility/volume within 15 minutes, market-adjusted against SPY, time-of-day-adjusted against each ticker's typical volatility in the same 15-minute-of-day window.

## Claim being tested
"Deviation from an author's historical rhetoric (embedding distance from rolling centroid) predicts abnormal market reaction."
**Not** being claimed: that the post itself causes the reaction. It is recognized that co-occurring news is a plausible alternative explanation and is not fully ruled out at this scope.

## Validation
Leave-one-account-out cross-validation. Forward paper-trading log starts as soon as a provisional model exists and will be logged immutably and timestamped.
