# Panel-Based Market Reaction Prediction from Public Figure Posts

**Status:** In development (pre-registration complete / pipeline build in progress)
**Type:** Personal research project — not a product, not investment advice, no signals or predictions shared with anyone other than the author.

---

## What this is

This project tests whether short-window abnormal market activity (volatility/volume, market-adjusted) following a public post from a market-relevant public figure can be predicted from how much that post *deviates from the author's own historical rhetoric* rather than from generic sentiment analysis.

Instead of studying a single high-profile account against a single stock (a heavily arbitraged, statistically weak setup), this project uses a small panel of accounts  a mix of very high-profile figures (expected to show little to no signal, used as a sanity-check baseline) and mid-tier figures such as company executives, financial officials, and public investors (where a real effect is more plausible, since these accounts are less thoroughly arbitraged).

## Why this design

- **Panel** A single time series is easy to overfit and easy for critics to dismiss as one lucky/unlucky pattern. A panel enables leave-one-account-out cross-validation and a real out-of-sample test.
- **Deviation-from-self-baseline** "How unusual is this, for this specific person" is a more defensible signal than "is this post positive or negative" — and it has real precedent: similar deviation-based methods are used in academic finance/economics research on institutional communication (e.g., measuring how much a Federal Reserve speech departs from prior messaging). This project applies the same idea to informal, unscripted public posts instead of scripted institutional text — that's the actual point of novelty here, not the underlying mechanism.
- **Forward-run validation** Backtests are always vulnerable to leakage and hindsight bias. This project logs every prediction, timestamped, *before* the outcome is known, and validates against that live log — this is the strongest evidence the project produces, and it's designed to keep accumulating for as long as the project runs.
- **Market-adjusted target** The prediction target is abnormal movement net of overall market movement, not raw price change — a ticker moving because the whole market moved isn't a meaningful "event."

## What this is *not*

- Not a trading system, and not used to trade real money.
- Not a signal or advice service — nothing produced here is shared with or sent to anyone other than the author. This avoids the liability and unlicensed-advice concerns that come with distributing predictive market content to other people.
- Not claiming that a post *causes* a market reaction. The tested hypothesis is that deviation-from-baseline is a predictive feature — a plausible alternative explanation is that both the unusual post and the market reaction are downstream of some shared real-world event (e.g., a surprise announcement covered simultaneously by news outlets). This project does not fully disentangle that and says so explicitly in its results, rather than overclaiming.
- Not a large-scale or exhaustive study. The panel is intentionally small (8–12 accounts), chosen with explicit, stated reasoning rather than an exhaustive or random sample — a limitation, not a hidden assumption.

## Methodology, briefly

1. **Data:** Public posts (via X API) from a fixed panel of accounts; 1-minute price/volume bars (via Alpaca's free tier) for each account's mapped ticker(s).
2. **Feature:** Embedding distance between a new post and that author's rolling historical centroid of past posts.
3. **Target:** Abnormal volatility/volume within a 15-minute window of a post, adjusted for overall market movement. (15 minutes was chosen deliberately — short enough to be meaningful, long enough that realistic data-pipeline latency, ~30–45 seconds worst case, only consumes a small fraction of the window, unlike a 5-minute window where the same latency would be a much larger share.)
4. **Validation:** Leave-one-account-out cross-validation, plus a single pre-registered statistical test (account subset, horizon, and correction method fixed and committed *before* any modeling — see `PREREGISTRATION.md`) to avoid quietly cherry-picking a favorable result after the fact.
5. **Forward log:** Every prediction is logged with a timestamp before its outcome is known, and re-scored later — the raw logged predictions are never edited retroactively.

## Known limitations (stated up front, not discovered later)

- **Free-tier price data (Alpaca/IEX) does not cover the full consolidated market tape**, particularly for volume. The primary target is defined on price/volatility (which tracks the broader market more closely even on a single venue) rather than volume, specifically to reduce exposure to this gap; volume-based results are treated as lower-confidence and secondary.
- **Small panel size** (8–12 accounts) means limited statistical power and a panel chosen by researcher judgment about plausible signal, not a random or exhaustive sample.
- **No control for news co-occurrence** in the base version of this project (an optional stretch feature using GDELT may be added if time allows) — so results should be read as "deviation-from-baseline correlates with abnormal activity," not "the post caused the reaction."
- **Time-of-day seasonality** in market volatility (elevated near open/close) is explicitly adjusted for in the abnormal-event threshold to avoid spuriously flagging ordinary open/close activity.
- **Sample period is regime-dependent.** Results reflect market conditions during the specific historical window tested and are not assumed to generalize to all market regimes.

## Expected outcome

Realistically: a weak or null result for the high-profile baseline accounts, and possibly a modest, likely-fragile signal for one or two mid-tier accounts. That outcome would be consistent with prior research on related questions (e.g., studies finding no significant relationship between CEO/official social posts and future stock prices at longer horizons). A correctly validated null or weak-positive result is treated here as a legitimate, reportable finding — not a failed project.

## Repository contents

- `PREREGISTRATION.md` — the pre-committed panel, horizon, and test design, timestamped before any modeling began.
- `pipeline/` — data ingestion, feature computation, and event-detection code.
- `forward_log/` — timestamped, append-only log of live predictions and (once resolved) outcomes.
- `dashboard/` — simple personal dashboard for reviewing forward-run predictions vs. outcomes.
- `results/` — writeup of backtest results, honestly reported including null/weak findings.

## Disclaimer

This project is for personal research and educational purposes only. It does not constitute financial advice, and no output from this project is provided to, or intended for use by, anyone other than the author.
